"""FastAPI router and WebSocket gateway for the voice module."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import secrets
import struct
import time
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, HTTPException, Response, WebSocket, WebSocketDisconnect


def _active_api_token() -> str:
    try:
        import app
        return str(getattr(app, "API_TOKEN", "") or "").strip()
    except Exception:
        return os.environ.get("ORBIT_API_TOKEN", "").strip()


def _safe_header_str(headers: Any, key: str) -> str:
    if not hasattr(headers, "get") or type(headers).__name__ == "AsyncMock":
        return ""
    val = headers.get(key)
    return val.strip() if isinstance(val, str) else ""


def _extract_ws_token(ws: WebSocket) -> str:
    headers = getattr(ws, "headers", None)
    header_tok = _safe_header_str(headers, "x-orbit-token")
    if header_tok:
        return header_tok
    proto_header = _safe_header_str(headers, "sec-websocket-protocol")
    for part in proto_header.split(","):
        item = part.strip()
        if item.startswith("orbit-token."):
            return item[len("orbit-token.") :]
    qp = getattr(ws, "query_params", None)
    if not hasattr(qp, "get") or type(qp).__name__ == "AsyncMock":
        return ""
    tok = qp.get("token", "")
    return tok if isinstance(tok, str) else ""


async def ws_authorized(ws: WebSocket) -> bool:
    token = _active_api_token()
    if not token:
        return True
    ok = secrets.compare_digest(_extract_ws_token(ws), token)
    if not ok:
        await ws.close(code=1008)
    return ok


def _accept_subprotocol(ws: WebSocket) -> str | None:
    proto_header = _safe_header_str(getattr(ws, "headers", None), "sec-websocket-protocol")
    for part in proto_header.split(","):
        if part.strip() == "orbit-v1":
            return "orbit-v1"
    return None


from . import config, text_clean, sentences, session, tts, stt

log = logging.getLogger("spidey.voice.router")

router = APIRouter(prefix="/api/voice", tags=["voice"])
ws_router = APIRouter(tags=["voice"])

# Persistent chat handlers registered by app.py
_CHAT_HANDLER: Callable[[str, str | None], Coroutine[Any, Any, dict[str, Any]]] | None = None
_STREAM_CHAT_HANDLER: Callable[..., Coroutine[Any, Any, dict[str, Any]]] | None = None
_SENTENCE_BOUNDARY_RE = re.compile(r"([.!?]+(?:\s+|$)|\n+)")


def set_chat_handler(
    handler: Callable[[str, str | None], Coroutine[Any, Any, dict[str, Any]]] | None
) -> None:
    """Register the chat pipeline function from app.py."""
    global _CHAT_HANDLER
    _CHAT_HANDLER = handler


def get_chat_handler() -> Callable[[str, str | None], Coroutine[Any, Any, dict[str, Any]]] | None:
    return _CHAT_HANDLER


def set_stream_chat_handler(
    handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]] | None
) -> None:
    """Register the streaming chat pipeline function from app.py."""
    global _STREAM_CHAT_HANDLER
    _STREAM_CHAT_HANDLER = handler


def get_stream_chat_handler() -> Callable[..., Coroutine[Any, Any, dict[str, Any]]] | None:
    return _STREAM_CHAT_HANDLER


_in_memory_speak_enabled: bool = False
_live_enabled_flag: bool = False


def _read_speak_setting() -> bool:
    try:
        from learning import progress, schema
        if not schema.is_initialized():
            import app
            if getattr(app, "DATABASE_PATH", None):
                schema.init(app.DATABASE_PATH)
        val = progress.get_setting("voice_speak_enabled", None)
        if val is not None:
            return val == "1"
        return _in_memory_speak_enabled
    except Exception:
        return _in_memory_speak_enabled


def _write_speak_setting(enabled: bool) -> None:
    global _in_memory_speak_enabled
    _in_memory_speak_enabled = enabled
    try:
        from learning import progress, schema
        if not schema.is_initialized():
            import app
            if getattr(app, "DATABASE_PATH", None):
                schema.init(app.DATABASE_PATH)
        progress.set_setting("voice_speak_enabled", "1" if enabled else "0")
    except Exception:
        pass


@router.get("/settings")
def get_voice_settings() -> dict[str, Any]:
    """Retrieve voice system status and persistent configurations."""
    engine = tts.get_tts_engine()

    safe_error = None
    err = engine.error
    if not err:
        try:
            from runtime.models import REGISTRY
            err = REGISTRY.errors.get("tts")
        except Exception:
            pass
    if err:
        safe_error = str(err).replace("\\", "/").split("/")[-1]

    engine_ready = engine.available
    if not engine_ready:
        try:
            from runtime.models import REGISTRY
            engine_ready = REGISTRY.is_ready("tts")
        except Exception:
            pass

    return {
        "speak_enabled": _read_speak_setting(),
        "live_enabled": _live_enabled_flag,
        "engine_ready": engine_ready,
        "is_loading": getattr(engine, "is_loading", False),
        "available": engine.available or engine_ready,
        "backend": getattr(engine, "backend", "sapi"),
        "voice": getattr(engine, "voice", ""),
        "sample_rate": config.SAMPLE_RATE,
        "load_time": getattr(engine, "load_time", 0.0),
        "device": engine.device,
        "dtype": engine.dtype,
        "error": safe_error,
        "allow_cloud_stt": config.STT_ALLOW_CLOUD,
        "stt_engine": config.STT_ENGINE,
    }


@router.put("/settings")
def update_voice_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Update speak and live mode toggles."""
    global _live_enabled_flag
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object.")

    if "speak_enabled" in payload:
        speak_val = bool(payload["speak_enabled"])
        _write_speak_setting(speak_val)

    if "live_enabled" in payload:
        _live_enabled_flag = bool(payload["live_enabled"])

    return get_voice_settings()


@router.post("/tts")
def synthesize_tts_chunk(payload: dict[str, Any] = Body(...)) -> Response:
    """Synthesize a single short text chunk into WAV audio."""
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object.")

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "'text' must be a non-empty string.")

    cleaned = text_clean.clean_text_for_speech(text)
    if not cleaned:
        raise HTTPException(400, "Text contains no speakable characters.")

    engine = tts.get_tts_engine()
    if not engine.available:
        engine.load()

    if not engine.available:
        raise HTTPException(503, "TTS engine is not available.")

    audio_array = engine.synthesize(cleaned)
    if audio_array is None or len(audio_array) == 0:
        raise HTTPException(500, "TTS synthesis failed or was cancelled.")

    wav_bytes = tts.audio_to_wav_bytes(audio_array, sample_rate=config.SAMPLE_RATE)
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/stop")
def stop_voice_turn(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, str]:
    """Cancel any in-flight voice synthesis, transcribing, or playback."""
    session_id = "default"
    if payload and isinstance(payload, dict) and "session_id" in payload:
        session_id = str(payload["session_id"])
    voice_session = session.get_voice_session(session_id)
    voice_session.reset()
    if session_id == "default":
        session.reset_all_sessions()
    return {"status": "stopped"}


def _calculate_pcm_energy(pcm_bytes: bytes) -> float:
    """Compute Root Mean Square (RMS) energy of 16-bit mono PCM samples."""
    if len(pcm_bytes) < 2:
        return 0.0
    num_samples = len(pcm_bytes) // 2
    # Unpack 16-bit signed integers
    fmt = f"<{num_samples}h"
    try:
        samples = struct.unpack(fmt, pcm_bytes[: num_samples * 2])
    except struct.error:
        return 0.0
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / max(1, num_samples))


@ws_router.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket) -> None:
    """WebSocket gateway for continuous mic streaming, STT, and live conversational turns."""
    if not await ws_authorized(websocket):
        return
    subproto = _accept_subprotocol(websocket)
    if subproto:
        await websocket.accept(subprotocol=subproto)
    else:
        await websocket.accept()
    client_id = f"ws-{id(websocket)}"
    voice_sess = session.get_voice_session(client_id)
    stt_engine = stt.get_stt()
    tts_engine = tts.get_tts_engine()

    mode = "live"
    chat_id: str | None = None
    is_speaking = False
    speech_detected = False
    speech_start_time = 0.0
    silence_start_time = 0.0
    pre_roll: list[bytes] = []  # Rolling ~500 ms pre-roll so silence never bloats PCM
    max_pre_roll_chunks = 5
    max_utterance_bytes = 16000 * 2 * 30  # Cap single utterance at 30 seconds (16kHz s16le)

    async def send_state(st: session.VState) -> None:
        voice_sess.state = st
        try:
            await websocket.send_text(json.dumps({"type": "state", "value": st.value}))
        except Exception:
            pass

    def _should_speak() -> bool:
        return mode in ("live", "ptt") or _read_speak_setting()

    async def _synthesize_and_send_sentence(sent: str, seq: int) -> bool:
        nonlocal is_speaking
        if voice_sess.cancel.is_set() or not sent.strip():
            return False
        if not tts_engine.available:
            await asyncio.to_thread(tts_engine.load)
        if not tts_engine.available:
            return False
        if not is_speaking:
            is_speaking = True
            await send_state(session.VState.SPEAKING)
        audio_array = await asyncio.to_thread(
            tts_engine.synthesize, sent, voice_sess.cancel
        )
        if audio_array is None or voice_sess.cancel.is_set():
            return False
        wav_data = tts.audio_to_wav_bytes(audio_array, sample_rate=config.SAMPLE_RATE)
        header = json.dumps({"type": "audio", "seq": seq, "sentence": sent})
        try:
            await websocket.send_text(header)
            await websocket.send_bytes(wav_data)
            return True
        except Exception:
            return False

    async def speak_sentences(reply_text: str) -> None:
        nonlocal is_speaking
        if not _should_speak():
            return
        cleaned = text_clean.summarize_for_speech(reply_text)
        sentences_list = sentences.split_sentences(cleaned, max_chars=config.MAX_SENTENCE_CHARS)
        if not sentences_list:
            return
        for seq, sent in enumerate(sentences_list):
            if voice_sess.cancel.is_set():
                break
            ok = await _synthesize_and_send_sentence(sent, seq)
            if not ok:
                break
        is_speaking = False

    async def process_utterance() -> None:
        nonlocal speech_detected, is_speaking
        speech_detected = False
        pcm_data = bytes(voice_sess.pcm)
        voice_sess.pcm.clear()

        if len(pcm_data) < 3200:  # Less than 100 ms of audio
            await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
            return

        # 1. Transcribe
        await send_state(session.VState.TRANSCRIBING)
        try:
            transcript = await stt_engine.transcribe_async(pcm_data)
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
            await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
            return

        if not transcript.strip() or voice_sess.cancel.is_set():
            await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
            return

        await websocket.send_text(json.dumps({"type": "transcript", "text": transcript}))

        # 2. Think / Stream reply + concurrent sentence-by-sentence TTS synthesis
        await send_state(session.VState.THINKING)
        stream_handler = get_stream_chat_handler()
        handler = get_chat_handler()
        reply_text = ""
        chat_res: dict[str, Any] = {}

        use_streaming = stream_handler is not None and (
            handler is None or getattr(handler, "_is_default_voice_handler", False)
        )
        if use_streaming:
            can_speak = _should_speak()
            sent_queue: asyncio.Queue[str | None] = asyncio.Queue()
            raw_stream_buf = ""
            partial_accum = ""
            in_code_fence = False
            spoken_any_streaming = False

            async def _tts_consumer() -> None:
                nonlocal is_speaking, spoken_any_streaming
                seq = 0
                try:
                    while not voice_sess.cancel.is_set():
                        item = await sent_queue.get()
                        if item is None:
                            break
                        for piece in sentences.split_sentences(item, max_chars=config.MAX_SENTENCE_CHARS):
                            if voice_sess.cancel.is_set():
                                break
                            ok = await _synthesize_and_send_sentence(piece, seq)
                            if not ok:
                                return
                            spoken_any_streaming = True
                            seq += 1
                finally:
                    is_speaking = False

            tts_worker = asyncio.create_task(_tts_consumer()) if can_speak else None

            def _drain_ready_sentences(force_flush: bool = False) -> list[str]:
                nonlocal raw_stream_buf, in_code_fence
                ready: list[str] = []
                while raw_stream_buf:
                    fence_idx = raw_stream_buf.find("```")
                    if fence_idx != -1:
                        before = raw_stream_buf[:fence_idx]
                        raw_stream_buf = raw_stream_buf[fence_idx + 3 :]
                        if not in_code_fence and before.strip():
                            cleaned = text_clean.clean_text_for_speech(before)
                            if cleaned:
                                ready.append(cleaned)
                        in_code_fence = not in_code_fence
                        continue
                    if in_code_fence:
                        # Hold inside code block until closing fence arrives
                        if force_flush:
                            raw_stream_buf = ""
                        break
                    match = _SENTENCE_BOUNDARY_RE.search(raw_stream_buf)
                    if not match:
                        if force_flush:
                            cleaned = text_clean.clean_text_for_speech(raw_stream_buf)
                            raw_stream_buf = ""
                            if cleaned:
                                ready.append(cleaned)
                        break
                    cut = match.end()
                    candidate = raw_stream_buf[:cut]
                    if len(candidate.strip()) < 28 and not force_flush:
                        # Wait for a little more text so tiny clauses batch naturally
                        next_match = _SENTENCE_BOUNDARY_RE.search(raw_stream_buf, pos=cut)
                        if not next_match:
                            break
                        cut = next_match.end()
                        candidate = raw_stream_buf[:cut]
                    raw_stream_buf = raw_stream_buf[cut:]
                    cleaned = text_clean.clean_text_for_speech(candidate)
                    if cleaned:
                        ready.append(cleaned)
                return ready

            async def _on_voice_token(delta: str) -> None:
                nonlocal raw_stream_buf, partial_accum
                if voice_sess.cancel.is_set() or not delta:
                    return
                partial_accum += delta
                raw_stream_buf += delta
                try:
                    await websocket.send_text(
                        json.dumps({"type": "reply_partial", "text": partial_accum})
                    )
                except Exception:
                    pass
                if tts_worker is not None:
                    for ready_sent in _drain_ready_sentences(force_flush=False):
                        await sent_queue.put(ready_sent)

            async def _on_voice_reset() -> None:
                nonlocal raw_stream_buf, partial_accum, in_code_fence
                raw_stream_buf = ""
                partial_accum = ""
                in_code_fence = False

            try:
                chat_res = await stream_handler(
                    transcript,
                    chat_id,
                    on_token=_on_voice_token,
                    on_stream_reset=_on_voice_reset,
                )
                reply_text = chat_res.get("response", "")
            except Exception as e:
                if tts_worker is not None:
                    await sent_queue.put(None)
                    tts_worker.cancel()
                await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
                return

            if not reply_text.strip() or voice_sess.cancel.is_set():
                if tts_worker is not None:
                    await sent_queue.put(None)
                    tts_worker.cancel()
                await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
                return

            spoken_source = chat_res.get("spoken_response") or reply_text
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "reply",
                        "text": reply_text,
                        "transcript": transcript,
                        "spoken_text": text_clean.summarize_for_speech(spoken_source),
                        "chat_id": chat_res.get("chat_id") or chat_id,
                        "messages": chat_res.get("messages"),
                        "navigate": chat_res.get("navigate"),
                        "provider": chat_res.get("provider"),
                        "ui_actions": chat_res.get("ui_actions"),
                    }
                )
            )

            if tts_worker is not None:
                # If turn came from deterministic local router (no streamed tokens yet), enqueue full spoken_source
                if not partial_accum.strip():
                    await sent_queue.put(text_clean.summarize_for_speech(spoken_source))
                else:
                    for tail_sent in _drain_ready_sentences(force_flush=True):
                        await sent_queue.put(tail_sent)
                await sent_queue.put(None)
                await tts_worker
        else:
            if handler:
                try:
                    chat_res = await handler(transcript, chat_id)
                    reply_text = chat_res.get("response", "")
                except Exception as e:
                    await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                    await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
                    return

            if not reply_text.strip() or voice_sess.cancel.is_set():
                await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)
                return

            spoken_source = chat_res.get("spoken_response") or reply_text
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "reply",
                        "text": reply_text,
                        "transcript": transcript,
                        "spoken_text": text_clean.summarize_for_speech(spoken_source),
                        "chat_id": chat_res.get("chat_id") or chat_id,
                        "messages": chat_res.get("messages"),
                        "navigate": chat_res.get("navigate"),
                        "provider": chat_res.get("provider"),
                        "ui_actions": chat_res.get("ui_actions"),
                    }
                )
            )

            # 3. Speak
            await speak_sentences(spoken_source)

        # 4. Finish turn
        if mode == "live" and not voice_sess.cancel.is_set():
            await send_state(session.VState.LISTENING)
        else:
            await send_state(session.VState.IDLE)

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "text" in msg:
                try:
                    payload = json.loads(msg["text"])
                except Exception:
                    continue

                msg_type = payload.get("type")
                if msg_type == "start":
                    mode = payload.get("mode", "live")
                    chat_id = payload.get("chat_id")
                    voice_sess.reset()
                    speech_detected = False
                    pre_roll.clear()
                    await send_state(session.VState.LISTENING)

                elif msg_type == "set_chat":
                    chat_id = payload.get("chat_id")

                elif msg_type == "stop":
                    voice_sess.reset()
                    is_speaking = False
                    speech_detected = False
                    pre_roll.clear()
                    await send_state(session.VState.IDLE)

                elif msg_type == "commit":
                    if voice_sess.state == session.VState.LISTENING and len(voice_sess.pcm) >= 3200:
                        speech_detected = False
                        silence_start_time = 0.0
                        pre_roll.clear()
                        voice_sess.state = session.VState.TRANSCRIBING
                        task = asyncio.create_task(process_utterance())
                        voice_sess.tasks.add(task)
                    else:
                        voice_sess.pcm.clear()
                        pre_roll.clear()
                        speech_detected = False
                        await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)

                elif msg_type == "interrupt":
                    voice_sess.reset()
                    is_speaking = False
                    speech_detected = False
                    pre_roll.clear()
                    await send_state(session.VState.LISTENING if mode == "live" else session.VState.IDLE)

            elif "bytes" in msg:
                pcm_chunk = msg["bytes"]
                now = time.perf_counter()
                energy = _calculate_pcm_energy(pcm_chunk)

                # Check barge-in during assistant speaking
                if is_speaking:
                    if energy >= config.LIVE_BARGE_IN_THRESHOLD:
                        voice_sess.reset()
                        is_speaking = False
                        speech_detected = True
                        speech_start_time = now
                        pre_roll.clear()
                        voice_sess.pcm.extend(pcm_chunk)
                        await send_state(session.VState.LISTENING)
                    continue

                if voice_sess.state != session.VState.LISTENING:
                    continue

                # In push-to-talk mode, capture continuously until explicit "commit"
                if mode == "ptt":
                    if len(voice_sess.pcm) < max_utterance_bytes:
                        voice_sess.pcm.extend(pcm_chunk)
                    continue

                if energy >= config.VAD_ENERGY_THRESHOLD:
                    if not speech_detected:
                        speech_detected = True
                        speech_start_time = now
                        for prev_chunk in pre_roll:
                            voice_sess.pcm.extend(prev_chunk)
                        pre_roll.clear()
                    silence_start_time = 0.0
                    voice_sess.pcm.extend(pcm_chunk)
                    if len(voice_sess.pcm) >= max_utterance_bytes:
                        speech_detected = False
                        silence_start_time = 0.0
                        voice_sess.state = session.VState.TRANSCRIBING
                        task = asyncio.create_task(process_utterance())
                        voice_sess.tasks.add(task)
                elif speech_detected:
                    voice_sess.pcm.extend(pcm_chunk)
                    if silence_start_time == 0.0:
                        silence_start_time = now
                    elif (now - silence_start_time) * 1000 >= config.VAD_TRAILING_SILENCE_MS:
                        # Ensure minimum speech length was satisfied
                        if (now - speech_start_time) * 1000 >= config.VAD_MIN_SPEECH_MS:
                            speech_detected = False
                            silence_start_time = 0.0
                            voice_sess.state = session.VState.TRANSCRIBING
                            task = asyncio.create_task(process_utterance())
                            voice_sess.tasks.add(task)
                        else:
                            speech_detected = False
                            silence_start_time = 0.0
                            voice_sess.pcm.clear()
                else:
                    # Keep a small rolling pre-roll buffer while waiting for speech onset
                    pre_roll.append(pcm_chunk)
                    if len(pre_roll) > max_pre_roll_chunks:
                        pre_roll.pop(0)

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        log.exception("Voice WebSocket error: %s", e)
    finally:
        voice_sess.reset()
        session.remove_voice_session(client_id)
