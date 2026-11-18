"""Voice TTS/STT utilities, WebSocket ConnectionManager, and agent turn orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket

def _app():
    import app

    return app


def run_existing_tts(text: str, output_path: str) -> None:
    """Synthesize speech into WAV audio file."""
    try:
        from voice.tts import get_tts_engine, audio_to_wav_bytes
        engine = get_tts_engine()
        engine.load()
        if engine.available:
            audio_array = engine.synthesize(text)
            if audio_array is not None and len(audio_array) > 0:
                wav_bytes = audio_to_wav_bytes(audio_array)
                with open(output_path, "wb") as f:
                    f.write(wav_bytes)
                return
    except Exception as err:
        logging.getLogger("orbit007").warning("TTS warning: %s", err)

    try:
        import wave, struct, math
        sr = 16000
        duration = 0.4
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            frames = bytearray()
            for i in range(int(sr * duration)):
                val = int(2500 * math.sin(2 * math.pi * 130.81 * (i / sr)))
                frames.extend(struct.pack("<h", val))
            wf.writeframes(frames)
    except Exception as wav_err:
        logging.getLogger("orbit007").warning("Fallback WAV warning: %s", wav_err)

def transcribe_pcm_bytes(pcm_bytes: bytes) -> str:
    """Transcribe 16 kHz mono 16-bit PCM bytes."""
    try:
        from voice.stt import get_stt
        stt = get_stt()
        return stt.transcribe(pcm_bytes)
    except Exception as err:
        logging.getLogger("orbit007").warning("STT failed: %s", err)
        return ""

class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(ws)


_tts_lock: asyncio.Lock | None = None


async def generate_tts_url(text: str) -> str | None:
    global _tts_lock
    if not text or not text.strip():
        return None
    from voice.text_clean import summarize_for_speech

    spoken_text = summarize_for_speech(text) or text
    _tts_lock = _tts_lock or asyncio.Lock()
    name = f"reply_{uuid.uuid4().hex[:12]}.wav"
    path = _app().TTS_DIR / name
    try:
        async with _tts_lock:  # TTS engine is not guaranteed thread-safe
            await asyncio.to_thread(_app().run_existing_tts, spoken_text, str(path))
        return f"/tts/{name}" if path.exists() else None
    except Exception:
        logging.getLogger("orbit007").exception("TTS failed")
        return None


def _cleanup_tts(max_age_s: int = 600) -> None:
    cutoff = time.time() - max_age_s
    for f in _app().TTS_DIR.glob("reply_*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass

def _cleanup_temp_audio() -> None:
    _app()._cleanup_tts(max_age_s=600)
    try:
        from voice.config import TMP_DIR
        if TMP_DIR.exists():
            cutoff = time.time() - 600
            for item in TMP_DIR.iterdir():
                if item.name in {".gitignore", ".gitkeep"}:
                    continue
                try:
                    if item.is_file() and item.stat().st_mtime < cutoff:
                        item.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception as exc:
        logging.getLogger("orbit007").warning("Temp audio cleanup error: %s", exc)





async def process_agent_turn(
    user_message: str,
    session_id: str = "default",
    chat_id: str | None = None,
    on_token=None,
    on_stream_reset=None,
    on_stream_done=None,
) -> dict:
    user_message = (user_message or "").strip()
    if not user_message:
        raise ValueError("Message cannot be empty.")
    if len(user_message) > _app().MAX_PROMPT_CHARS:
        raise ValueError(f"Message is limited to {_app().MAX_PROMPT_CHARS} characters.")
    target_chat = chat_id or session_id or _app().DEFAULT_CHAT_ID
    _app()._ensure_chat_exists(target_chat)
    _app().memory_store.add_message(target_chat, "user", user_message)

    # 1. Pending confirmation check
    handled, conf_reply, conf_actions = _app().confirmation_mgr.check_and_handle(target_chat, user_message, _app().agent_deps)
    if handled:
        _app().memory_store.add_message(target_chat, "assistant", conf_reply)
        audio_url = await _app().generate_tts_url(conf_reply)
        _app()._cleanup_tts()
        return {
            "type": "agent_response",
            "text": conf_reply,
            "audio_url": audio_url,
            "reminders": _app()._live_reminders(),
            "history": _app().memory_store.get_messages(target_chat)[-20:],
            "ui_actions": conf_actions,
        }

    # 2. Rules-first command handling
    reply_text: str | None = None
    ui_actions: list[dict[str, Any]] = []
    try:
        cmd_result = await asyncio.to_thread(_app()._handle_local_command, user_message, target_chat)
        if cmd_result:
            reply_text = cmd_result[0]
            _nav, ui_actions = _app()._build_local_command_ui_actions(cmd_result[1])
    except Exception:
        logging.getLogger("orbit007").exception("Local command handling failed for %r", user_message)

    # 3. Route to native tool loop
    if reply_text is None:
        history = _app().memory_store.get_messages(target_chat)[-10:]
        memories = _app()._memories_for_prompt(user_message)
        try:
            if on_token is not None:
                agent_result = await _app().respond_with_tools_stream(
                    user_message,
                    target_chat,
                    history,
                    memories,
                    "agent",
                    on_token=on_token,
                    on_stream_reset=on_stream_reset,
                )
            else:
                agent_result = await asyncio.to_thread(
                    _app().respond_with_tools,
                    user_message,
                    target_chat,
                    history,
                    memories,
                    "agent",
                )
            reply_text = agent_result.reply
            ui_actions = agent_result.ui_actions
        except Exception as exc:
            logging.getLogger("orbit007").warning("Agent turn failed: %s", exc)
            if _app().is_gemini_active():
                reply_text = f"I'm having trouble reaching the Gemini API: {exc}"
            else:
                reply_text = "I'm having trouble connecting to my local language model right now. Please make sure Ollama is running (`ollama serve`)."
        if on_stream_done is not None:
            res = on_stream_done()
            if asyncio.iscoroutine(res):
                await res

    _app().memory_store.add_message(target_chat, "assistant", reply_text)

    # 4. Audio generation: per-reply unique audio file
    audio_url = await _app().generate_tts_url(reply_text)
    _app()._cleanup_tts()

    from voice.text_clean import summarize_for_speech

    return {
        "type": "agent_response",
        "text": reply_text,
        "spoken_text": summarize_for_speech(reply_text),
        "audio_url": audio_url,
        "reminders": _app()._live_reminders(),
        "history": _app().memory_store.get_messages(target_chat)[-20:],
        "ui_actions": ui_actions,
    }




