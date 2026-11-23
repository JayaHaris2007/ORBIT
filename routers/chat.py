"""Chat, generation, streaming, and WebSocket routes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from voice.text_clean import summarize_for_speech

router = APIRouter(tags=["chat"])


class ChatPayload(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None


def _app():
    import app

    return app


@router.post("/generate")
@router.post("/api/generate")
async def generate(payload: dict[str, Any] = Body(...)):
    a = _app()
    prompt, _max_new_tokens, chat_id = a._validate_generate_payload(payload)

    try:
        # 1. Pending confirmation check
        handled, conf_reply, conf_actions = a.confirmation_mgr.check_and_handle(chat_id, prompt, a.agent_deps)
        if handled:
            a.memory_store.add_message(chat_id, "user", prompt.strip())
            a.memory_store.add_message(chat_id, "assistant", conf_reply)
            return {
                "response": conf_reply,
                "spoken_response": summarize_for_speech(conf_reply),
                "chat_id": chat_id,
                "messages": a.memory_store.get_messages(chat_id),
                "provider": "local-confirmation",
                "navigate": None,
                "ui_actions": conf_actions,
            }

        # 2. Rules-first command handling
        local_error_msg: str | None = None
        try:
            command = a._handle_local_command(prompt, chat_id)
        except ValueError as cmd_err:
            a.LOGGER.info("Local command raised ValueError (%s) for %r", cmd_err, prompt)
            command = None
            local_error_msg = str(cmd_err)
        a.LOGGER.info("[route] %s <- %r", "local:" + command[1] if command else "tools/llm", prompt)
        if command is not None:
            response, provider = command
            a.memory_store.add_message(chat_id, "user", prompt.strip())
            a.memory_store.add_message(chat_id, "assistant", response)
            nav, ui_actions = a._build_local_command_ui_actions(provider)
            return {
                "response": response,
                "spoken_response": summarize_for_speech(response),
                "chat_id": chat_id,
                "messages": a.memory_store.get_messages(chat_id),
                "provider": provider.split(":", 1)[0],
                "navigate": nav,
                "ui_actions": ui_actions,
            }

        # 3. Native tools / LLM response
        a.memory_store.add_message(chat_id, "user", prompt.strip())
        context = a.memory_store.build_context(chat_id, None, prompt)
        model_prompt = a.resolve_short_follow_up(prompt, context)
        memories = a._memories_for_prompt(model_prompt)
        history = list(context)
        if history and history[-1].get("role") == "user" and history[-1].get("content") == prompt.strip():
            history.pop()
        try:
            agent_result = await asyncio.to_thread(
                a.respond_with_tools,
                model_prompt,
                chat_id,
                history,
                memories,
                "web",
            )
            response = agent_result.reply
            ui_actions = agent_result.ui_actions
            provider = agent_result.provider
        except RuntimeError as err:
            logging.getLogger("orbit007").warning("LLM generation failed in chat route: %s", err)
            if a.is_gemini_active():
                response = local_error_msg or f"Gemini API error: {err}"
                provider = "gemini"
            else:
                response = local_error_msg or "I'm having trouble connecting to my local language model right now. Please make sure Ollama is running (`ollama serve`)."
                provider = "ollama"
            ui_actions = []

        a.memory_store.add_message(chat_id, "assistant", response)
        nav_page = next((act.get("page") for act in reversed(ui_actions) if act.get("type") == "navigate"), None)
        return {
            "response": response,
            "spoken_response": summarize_for_speech(response),
            "chat_id": chat_id,
            "messages": a.memory_store.get_messages(chat_id),
            "provider": provider,
            "navigate": nav_page,
            "ui_actions": ui_actions,
        }
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/generate/stream")
@router.post("/api/generate/stream")
async def generate_stream(payload: dict[str, Any] = Body(...)):
    a = _app()
    prompt, _max_new_tokens, chat_id = a._validate_generate_payload(payload)

    async def event_generator():
        try:
            # 1. Pending confirmation check
            handled, conf_reply, conf_actions = a.confirmation_mgr.check_and_handle(chat_id, prompt, a.agent_deps)
            if handled:
                a.memory_store.add_message(chat_id, "user", prompt.strip())
                a.memory_store.add_message(chat_id, "assistant", conf_reply)
                done_payload = {
                    "type": "done",
                    "response": conf_reply,
                    "spoken_response": summarize_for_speech(conf_reply),
                    "chat_id": chat_id,
                    "messages": a.memory_store.get_messages(chat_id),
                    "provider": "local-confirmation",
                    "navigate": None,
                    "ui_actions": conf_actions,
                }
                yield f"data: {json.dumps(done_payload)}\n\n"
                return

            # 2. Rules-first command handling
            local_error_msg: str | None = None
            try:
                command = await asyncio.to_thread(a._handle_local_command, prompt, chat_id)
            except ValueError as cmd_err:
                a.LOGGER.info("Local command raised ValueError (%s) for %r", cmd_err, prompt)
                command = None
                local_error_msg = str(cmd_err)
            a.LOGGER.info("[route] %s <- %r", "local:" + command[1] if command else "tools/llm", prompt)
            if command is not None:
                response, provider = command
                a.memory_store.add_message(chat_id, "user", prompt.strip())
                a.memory_store.add_message(chat_id, "assistant", response)
                nav, ui_actions = a._build_local_command_ui_actions(provider)
                done_payload = {
                    "type": "done",
                    "response": response,
                    "spoken_response": summarize_for_speech(response),
                    "chat_id": chat_id,
                    "messages": a.memory_store.get_messages(chat_id),
                    "provider": provider.split(":", 1)[0],
                    "navigate": nav,
                    "ui_actions": ui_actions,
                }
                yield f"data: {json.dumps(done_payload)}\n\n"
                return

            # 3. Native tools / LLM streaming response
            a.memory_store.add_message(chat_id, "user", prompt.strip())
            context = a.memory_store.build_context(chat_id, None, prompt)
            model_prompt = a.resolve_short_follow_up(prompt, context)
            memories = a._memories_for_prompt(model_prompt)
            history = list(context)
            if history and history[-1].get("role") == "user" and history[-1].get("content") == prompt.strip():
                history.pop()

            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

            async def _on_token(text: str) -> None:
                if text:
                    await queue.put({"type": "token", "text": text})

            async def _on_reset() -> None:
                await queue.put({"type": "stream_reset"})

            async def _run() -> None:
                try:
                    agent_result = await a.respond_with_tools_stream(
                        model_prompt,
                        chat_id,
                        history,
                        memories,
                        "web",
                        on_token=_on_token,
                        on_stream_reset=_on_reset,
                    )
                    response = agent_result.reply
                    ui_actions = agent_result.ui_actions
                    provider = agent_result.provider
                except RuntimeError as err:
                    logging.getLogger("orbit007").warning("LLM streaming failed in chat route: %s", err)
                    if a.is_gemini_active():
                        response = local_error_msg or f"Gemini API error: {err}"
                        provider = "gemini"
                    else:
                        response = (
                            local_error_msg
                            or "I'm having trouble connecting to my local language model right now. Please make sure Ollama is running (`ollama serve`)."
                        )
                        provider = "ollama"
                    ui_actions = []
                    await queue.put({"type": "stream_reset"})
                    await queue.put({"type": "token", "text": response})

                await queue.put({"type": "stream_done"})
                a.memory_store.add_message(chat_id, "assistant", response)
                nav_page = next((act.get("page") for act in reversed(ui_actions) if act.get("type") == "navigate"), None)
                await queue.put({
                    "type": "done",
                    "response": response,
                    "spoken_response": summarize_for_speech(response),
                    "chat_id": chat_id,
                    "messages": a.memory_store.get_messages(chat_id),
                    "provider": provider,
                    "navigate": nav_page,
                    "ui_actions": ui_actions,
                })
                await queue.put(None)

            task = asyncio.create_task(_run())
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                await task
            finally:
                if not task.done():
                    task.cancel()
        except Exception as err:
            logging.getLogger("orbit007").warning("Stream error in chat route: %s", err)
            yield f"data: {json.dumps({'type': 'error', 'error': str(err)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat")
async def api_chat(payload: ChatPayload):
    a = _app()
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if payload.gemini_api_key:
        tokens = a.set_request_gemini_config(payload.gemini_api_key, payload.gemini_model)
        try:
            return await a.process_agent_turn(payload.message, payload.session_id or "default")
        finally:
            a.reset_request_gemini_config(tokens)
    return await a.process_agent_turn(payload.message, payload.session_id or "default")


@router.websocket("/ws")
async def websocket_agent_endpoint(websocket: WebSocket):
    a = _app()
    if not await a.ws_authorized(websocket):
        return
    await a.ws_manager.connect(websocket)
    a._ensure_chat_exists(a.DEFAULT_CHAT_ID)
    current_chat_id = a.DEFAULT_CHAT_ID
    # Never accept API keys via URL query parameters (prevents leaking keys into server/proxy logs)
    ws_gemini_key: str | None = None
    ws_gemini_model: str | None = None
    try:
        await websocket.send_json({
            "type": "connected",
            "reminders": a._live_reminders(),
            "history": a.memory_store.get_messages(current_chat_id)[-20:],
            "chat_id": current_chat_id,
        })

        async def _ws_on_token(text: str) -> None:
            await websocket.send_json({"type": "token", "text": text})

        async def _ws_on_reset() -> None:
            await websocket.send_json({"type": "stream_reset"})

        async def _ws_on_done() -> None:
            await websocket.send_json({"type": "stream_done"})

        async def _run_and_send_turn(text: str) -> None:
            await websocket.send_json({"type": "status", "state": "thinking"})
            tokens = a.set_request_gemini_config(ws_gemini_key, ws_gemini_model)
            try:
                result = await a.process_agent_turn(
                    text,
                    session_id=current_chat_id,
                    chat_id=current_chat_id,
                    on_token=_ws_on_token,
                    on_stream_reset=_ws_on_reset,
                    on_stream_done=_ws_on_done,
                )
            finally:
                a.reset_request_gemini_config(tokens)
            await websocket.send_json(result)

        audio_buffer = bytearray()
        while True:
            packet = await websocket.receive()
            if "bytes" in packet and packet["bytes"]:
                pcm_bytes = packet["bytes"]
                if len(pcm_bytes) > 2 * 1024 * 1024:
                    await websocket.send_json({"type": "error", "error": "Binary payload exceeds 2 MB limit"})
                    continue
                if len(pcm_bytes) >= 16000:
                    # Full utterance payload
                    transcript = await asyncio.to_thread(a.transcribe_pcm_bytes, pcm_bytes)
                    if transcript and transcript.strip():
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript,
                        })
                        await _run_and_send_turn(transcript)
                else:
                    # Streamed 100ms chunk from AudioWorklet
                    audio_buffer.extend(pcm_bytes)
                    if len(audio_buffer) >= 64000:
                        data_to_transcribe = bytes(audio_buffer)
                        audio_buffer.clear()
                        transcript = await asyncio.to_thread(a.transcribe_pcm_bytes, data_to_transcribe)
                        if transcript and transcript.strip():
                            await websocket.send_json({
                                "type": "transcript",
                                "text": transcript,
                            })
                            await _run_and_send_turn(transcript)

            elif "text" in packet and packet["text"]:
                try:
                    payload = json.loads(packet["text"])
                except json.JSONDecodeError:
                    payload = {"message": packet["text"]}

                msg_type = payload.get("type")
                if "gemini_api_key" in payload:
                    raw_gkey = payload.get("gemini_api_key")
                    ws_gemini_key = raw_gkey.strip() if isinstance(raw_gkey, str) and raw_gkey.strip() else None
                if "gemini_model" in payload:
                    raw_gmodel = payload.get("gemini_model")
                    ws_gemini_model = raw_gmodel.strip() if isinstance(raw_gmodel, str) and raw_gmodel.strip() else None

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                elif msg_type == "set_gemini_config":
                    await websocket.send_json({
                        "type": "gemini_config_set",
                        "active": bool(ws_gemini_key),
                        "model": ws_gemini_model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
                    })
                    continue
                elif msg_type == "set_chat":
                    req_cid = payload.get("chat_id")
                    if req_cid and a.memory_store.chat_exists(req_cid):
                        current_chat_id = req_cid
                    else:
                        current_chat_id = a.DEFAULT_CHAT_ID
                    await websocket.send_json({
                        "type": "chat_set",
                        "chat_id": current_chat_id,
                        "history": a.memory_store.get_messages(current_chat_id)[-20:],
                    })
                    continue
                elif msg_type == "end_audio":
                    if len(audio_buffer) >= 3200:
                        data_to_transcribe = bytes(audio_buffer)
                        audio_buffer.clear()
                        transcript = await asyncio.to_thread(a.transcribe_pcm_bytes, data_to_transcribe)
                        if transcript and transcript.strip():
                            await websocket.send_json({
                                "type": "transcript",
                                "text": transcript,
                            })
                            await _run_and_send_turn(transcript)
                    else:
                        audio_buffer.clear()
                    continue

                user_msg = payload.get("message") or payload.get("text") or ""
                # Accept optional chat_id on every text message
                msg_chat_id = payload.get("chat_id")
                if msg_chat_id is not None:
                    if msg_chat_id and a.memory_store.chat_exists(msg_chat_id):
                        current_chat_id = msg_chat_id
                    else:
                        current_chat_id = a.DEFAULT_CHAT_ID

                if user_msg.strip():
                    await _run_and_send_turn(user_msg)
    except WebSocketDisconnect:
        logging.getLogger("orbit007").info("WebSocket client disconnected")
    except Exception as exc:
        logging.getLogger("orbit007").warning("WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            a.LOGGER.debug("Suppressed error (routers/chat.py ws)", exc_info=True)
    finally:
        a.ws_manager.disconnect(websocket)
