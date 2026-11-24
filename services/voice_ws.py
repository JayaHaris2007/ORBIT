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
        headers = getattr(ws, "headers", None)
        raw_proto = (
            headers.get("sec-websocket-protocol")
            if hasattr(headers, "get") and type(headers).__name__ != "AsyncMock"
            else None
        )
        proto_header = raw_proto if isinstance(raw_proto, str) else ""
        subproto = "orbit-v1" if any(p.strip() == "orbit-v1" for p in proto_header.split(",")) else None
        if subproto:
            await ws.accept(subprotocol=subproto)
        else:
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
    from services.turn_orchestrator import execute_turn, execute_turn_stream

    user_message = (user_message or "").strip()
    if not user_message:
        raise ValueError("Message cannot be empty.")
    if len(user_message) > _app().MAX_PROMPT_CHARS:
        raise ValueError(f"Message is limited to {_app().MAX_PROMPT_CHARS} characters.")
    target_chat = chat_id or session_id or _app().DEFAULT_CHAT_ID
    _app()._ensure_chat_exists(target_chat)

    if on_token is not None:
        outcome = await execute_turn_stream(
            user_message,
            target_chat,
            channel="agent",
            on_token=on_token,
            on_stream_reset=on_stream_reset,
            on_stream_done=on_stream_done,
            stream_local_tokens=False,
        )
    else:
        outcome = await execute_turn(
            user_message,
            target_chat,
            channel="agent",
        )

    audio_url = await _app().generate_tts_url(outcome.response)
    _app()._cleanup_tts()

    return {
        "type": "agent_response",
        "text": outcome.response,
        "spoken_text": outcome.spoken_response,
        "audio_url": audio_url,
        "reminders": _app()._live_reminders(),
        "history": _app().memory_store.get_messages(target_chat)[-20:],
        "navigate": outcome.navigate,
        "ui_actions": outcome.ui_actions,
    }




