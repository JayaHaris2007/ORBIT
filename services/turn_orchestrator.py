"""Unified turn orchestration shared by HTTP chat, SSE streaming, ORBIT WS, and Live Voice."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from voice.text_clean import summarize_for_speech


def _app():
    import app

    return app


@dataclass
class TurnOutcome:
    """Normalized result of any conversational turn across channels."""

    response: str
    spoken_response: str
    chat_id: str
    provider: str
    navigate: str | None = None
    ui_actions: list[dict[str, Any]] = field(default_factory=list)


async def _call_maybe_async(cb: Callable[..., Any] | None, *args: Any) -> None:
    if cb is None:
        return
    res = cb(*args)
    if inspect.isawaitable(res):
        await res


def _fallback_error_reply(err: Exception, local_error_msg: str | None, channel: str) -> tuple[str, str]:
    a = _app()
    if local_error_msg:
        provider = "gemini" if a.is_gemini_active() else "ollama"
        return local_error_msg, provider
    if a.is_gemini_active():
        prefix = "I'm having trouble reaching the Gemini API" if channel == "agent" else "Gemini API error"
        return f"{prefix}: {err}", "gemini"
    return (
        "I'm having trouble connecting to my local language model right now. "
        "Please make sure Ollama is running (`ollama serve`).",
        "ollama",
    )


def _prepare_history_and_memories(chat_id: str, prompt: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    a = _app()
    stripped = prompt.strip()
    a.memory_store.add_message(chat_id, "user", stripped)
    context = a.memory_store.build_context(chat_id, None, prompt)
    model_prompt = a.resolve_short_follow_up(prompt, context)
    memories = a._memories_for_prompt(model_prompt)
    history = list(context)
    if history and history[-1].get("role") == "user" and history[-1].get("content") == stripped:
        history.pop()
    return model_prompt, history, memories


async def execute_turn(
    prompt: str,
    chat_id: str,
    *,
    channel: str = "web",
) -> TurnOutcome:
    """Execute a complete conversational turn (confirmations -> rules -> tool loop) without streaming."""
    a = _app()
    stripped = prompt.strip()

    # 1. Pending confirmation check
    handled, conf_reply, conf_actions = a.confirmation_mgr.check_and_handle(chat_id, prompt, a.agent_deps)
    if handled:
        a.memory_store.add_message(chat_id, "user", stripped)
        a.memory_store.add_message(chat_id, "assistant", conf_reply)
        return TurnOutcome(
            response=conf_reply,
            spoken_response=summarize_for_speech(conf_reply),
            chat_id=chat_id,
            provider="local-confirmation",
            navigate=None,
            ui_actions=conf_actions,
        )

    # 2. Rules-first deterministic command handling
    local_error_msg: str | None = None
    command = None
    try:
        command = await asyncio.to_thread(a._handle_local_command, prompt, chat_id)
    except ValueError as cmd_err:
        a.LOGGER.info("Local command raised ValueError (%s) for %r", cmd_err, prompt)
        local_error_msg = str(cmd_err)
    except Exception:
        logging.getLogger("orbit007").exception("Local command handling failed for %r", prompt)

    a.LOGGER.info("[route] %s <- %r", "local:" + command[1] if command else "tools/llm", prompt)
    if command is not None:
        response, provider = command
        a.memory_store.add_message(chat_id, "user", stripped)
        a.memory_store.add_message(chat_id, "assistant", response)
        nav, ui_actions = a._build_local_command_ui_actions(provider)
        return TurnOutcome(
            response=response,
            spoken_response=summarize_for_speech(response),
            chat_id=chat_id,
            provider=provider.split(":", 1)[0],
            navigate=nav,
            ui_actions=ui_actions,
        )

    # 3. Native tools / LLM response
    model_prompt, history, memories = _prepare_history_and_memories(chat_id, prompt)
    try:
        agent_result = await asyncio.to_thread(
            a.respond_with_tools,
            model_prompt,
            chat_id,
            history,
            memories,
            channel,
        )
        response = agent_result.reply
        ui_actions = agent_result.ui_actions
        provider = agent_result.provider
    except Exception as err:
        logging.getLogger("orbit007").warning("LLM generation failed in %s turn: %s", channel, err)
        response, provider = _fallback_error_reply(err, local_error_msg, channel)
        ui_actions = []

    a.memory_store.add_message(chat_id, "assistant", response)
    nav_page = next((act.get("page") for act in reversed(ui_actions) if act.get("type") == "navigate"), None)
    return TurnOutcome(
        response=response,
        spoken_response=summarize_for_speech(response),
        chat_id=chat_id,
        provider=provider,
        navigate=nav_page,
        ui_actions=ui_actions,
    )


async def execute_turn_stream(
    prompt: str,
    chat_id: str,
    *,
    channel: str = "web",
    on_token: Callable[[str], Any] | None = None,
    on_stream_reset: Callable[[], Any] | None = None,
    on_stream_done: Callable[[], Any] | None = None,
    stream_local_tokens: bool = False,
) -> TurnOutcome:
    """Execute a complete conversational turn, streaming LLM tokens through callbacks."""
    a = _app()
    stripped = prompt.strip()

    # 1. Pending confirmation check
    handled, conf_reply, conf_actions = a.confirmation_mgr.check_and_handle(chat_id, prompt, a.agent_deps)
    if handled:
        a.memory_store.add_message(chat_id, "user", stripped)
        a.memory_store.add_message(chat_id, "assistant", conf_reply)
        if stream_local_tokens and conf_reply:
            await _call_maybe_async(on_token, conf_reply)
            await _call_maybe_async(on_stream_done)
        return TurnOutcome(
            response=conf_reply,
            spoken_response=summarize_for_speech(conf_reply),
            chat_id=chat_id,
            provider="local-confirmation",
            navigate=None,
            ui_actions=conf_actions,
        )

    # 2. Rules-first deterministic command handling
    local_error_msg: str | None = None
    command = None
    try:
        command = await asyncio.to_thread(a._handle_local_command, prompt, chat_id)
    except ValueError as cmd_err:
        a.LOGGER.info("Local command raised ValueError (%s) for %r", cmd_err, prompt)
        local_error_msg = str(cmd_err)
    except Exception:
        logging.getLogger("orbit007").exception("Local command handling failed for %r", prompt)

    a.LOGGER.info("[route] %s <- %r", "local:" + command[1] if command else "tools/llm", prompt)
    if command is not None:
        response, provider = command
        a.memory_store.add_message(chat_id, "user", stripped)
        a.memory_store.add_message(chat_id, "assistant", response)
        nav, ui_actions = a._build_local_command_ui_actions(provider)
        if stream_local_tokens and response:
            await _call_maybe_async(on_token, response)
            await _call_maybe_async(on_stream_done)
        return TurnOutcome(
            response=response,
            spoken_response=summarize_for_speech(response),
            chat_id=chat_id,
            provider=provider.split(":", 1)[0],
            navigate=nav,
            ui_actions=ui_actions,
        )

    # 3. Native tools / LLM streaming response
    model_prompt, history, memories = _prepare_history_and_memories(chat_id, prompt)
    try:
        agent_result = await a.respond_with_tools_stream(
            model_prompt,
            chat_id,
            history,
            memories,
            channel,
            on_token=on_token,
            on_stream_reset=on_stream_reset,
        )
        response = agent_result.reply
        ui_actions = agent_result.ui_actions
        provider = agent_result.provider
    except Exception as err:
        logging.getLogger("orbit007").warning("LLM streaming failed in %s turn: %s", channel, err)
        response, provider = _fallback_error_reply(err, local_error_msg, channel)
        ui_actions = []
        await _call_maybe_async(on_stream_reset)
        await _call_maybe_async(on_token, response)

    await _call_maybe_async(on_stream_done)
    a.memory_store.add_message(chat_id, "assistant", response)
    nav_page = next((act.get("page") for act in reversed(ui_actions) if act.get("type") == "navigate"), None)
    return TurnOutcome(
        response=response,
        spoken_response=summarize_for_speech(response),
        chat_id=chat_id,
        provider=provider,
        navigate=nav_page,
        ui_actions=ui_actions,
    )
