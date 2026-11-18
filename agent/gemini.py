"""Google AI Studio (Gemini) REST client & schema adapter for S.P.I.D.E.Y.

Provides synchronous and async-streaming chat completions with full
function-calling support, normalized to the same message/chunk shape
used by `agent/loop.py` and `app.py`.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

log = logging.getLogger("orbit007.gemini")

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
FALLBACK_GEMINI_MODELS = ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-4-hydrogen")
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Per-request contextvars so mobile/web users can supply their own AI Studio key
_request_gemini_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_gemini_key", default=None
)
_request_gemini_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_gemini_model", default=None
)


def set_request_gemini_config(
    api_key: str | None,
    model: str | None = None,
) -> tuple[contextvars.Token[str | None], contextvars.Token[str | None]]:
    """Bind per-request Gemini credentials into the current execution context."""
    clean_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
    clean_model = model.strip() if isinstance(model, str) and model.strip() else None
    tok_key = _request_gemini_key.set(clean_key)
    tok_model = _request_gemini_model.set(clean_model)
    return tok_key, tok_model


def reset_request_gemini_config(
    tokens: tuple[contextvars.Token[str | None], contextvars.Token[str | None]],
) -> None:
    """Restore previous per-request Gemini credentials."""
    tok_key, tok_model = tokens
    _request_gemini_key.reset(tok_key)
    _request_gemini_model.reset(tok_model)


def get_active_gemini_config() -> tuple[str | None, str]:
    """Return `(api_key, model)` if Gemini should be used for the current request.

    Priority:
      1. Per-request key supplied by the UI (`X-Gemini-Api-Key` / WS payload).
      2. Server-level `GEMINI_API_KEY` when `LLM_BACKEND=gemini`.
    """
    req_key = _request_gemini_key.get()
    req_model = _request_gemini_model.get()
    default_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

    if req_key:
        return req_key, req_model or default_model

    backend = os.environ.get("LLM_BACKEND", "ollama").strip().lower()
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if backend == "gemini" and env_key:
        return env_key, req_model or default_model

    return None, req_model or default_model


def is_gemini_active() -> bool:
    """Return True when the current request or server config targets Gemini."""
    api_key, _ = get_active_gemini_config()
    return bool(api_key)


def _sanitize_schema(schema: Any) -> Any:
    """Strip JSON-schema keys that Gemini's Schema proto rejects."""
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema", "default"):
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {pk: _sanitize_schema(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            cleaned[k] = _sanitize_schema(v)
        else:
            cleaned[k] = v
    return cleaned


def convert_tools_to_gemini(ollama_tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Convert OpenAI/Ollama tool schemas into Gemini `functionDeclarations`."""
    if not ollama_tools:
        return None
    declarations: list[dict[str, Any]] = []
    for item in ollama_tools:
        fn = item.get("function") if isinstance(item, dict) else None
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        decl: dict[str, Any] = {
            "name": fn["name"],
            "description": fn.get("description", ""),
        }
        params = fn.get("parameters")
        if isinstance(params, dict) and params.get("properties"):
            decl["parameters"] = _sanitize_schema(params)
        declarations.append(decl)
    return [{"functionDeclarations": declarations}] if declarations else None


def convert_messages_to_gemini(
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Convert Ollama/OpenAI-style messages into Gemini `(system_instruction, contents)`."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []

    def _append_content(role: str, parts: list[dict[str, Any]]) -> None:
        if not parts:
            return
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or ""

        if role == "system":
            if content:
                system_parts.append(str(content))
            continue

        if role == "user":
            _append_content("user", [{"text": str(content)}])
            continue

        if role == "assistant":
            parts: list[dict[str, Any]] = []
            if content:
                parts.append({"text": str(content)})
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                name = fn.get("name")
                if not name:
                    continue
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                parts.append({"functionCall": {"name": name, "args": args}})
            _append_content("model", parts)
            continue

        if role == "tool":
            tool_name = msg.get("tool_name") or "tool"
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                if not isinstance(parsed, dict):
                    parsed = {"result": parsed}
            except Exception:
                parsed = {"result": str(content)}
            _append_content(
                "user",
                [{"functionResponse": {"name": tool_name, "response": parsed}}],
            )

    system_instruction = (
        {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
    )
    return system_instruction, contents


def _build_gemini_payload(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 512,
) -> dict[str, Any]:
    system_instruction, contents = convert_messages_to_gemini(messages)
    payload: dict[str, Any] = {
        "contents": contents or [{"role": "user", "parts": [{"text": "Hello"}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max(64, int(max_tokens or 512)),
        },
    }
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    gemini_tools = convert_tools_to_gemini(tools)
    if gemini_tools:
        payload["tools"] = gemini_tools
    return payload


def _extract_parts(candidate: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Extract text and normalized Ollama-style tool_calls from a Gemini candidate."""
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for part in parts:
        if not isinstance(part, dict):
            continue
        if "text" in part and part["text"]:
            texts.append(str(part["text"]))
        if "functionCall" in part and isinstance(part["functionCall"], dict):
            fc = part["functionCall"]
            name = fc.get("name", "")
            args = fc.get("args") or {}
            if name:
                tool_calls.append({
                    "function": {
                        "name": name,
                        "arguments": args if isinstance(args, dict) else {},
                    }
                })

    return "".join(texts), tool_calls


def _format_gemini_error(status: int, body: str) -> str:
    try:
        err_json = json.loads(body)
        msg = err_json.get("error", {}).get("message") or body[:200]
    except Exception:
        msg = body[:200]
    if status in (400, 401, 403):
        return f"Gemini API authentication/request error ({status}): {msg}"
    if status == 429:
        return f"Gemini API rate limit exceeded (429): {msg}"
    return f"Gemini API HTTP error ({status}): {msg}"


def _candidate_models(primary_model: str) -> list[str]:
    primary = (primary_model or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    models = [primary]
    for fb in FALLBACK_GEMINI_MODELS:
        if fb not in models:
            models.append(fb)
    return models


def gemini_chat_request(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 60.0,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Execute a synchronous Gemini generateContent request with transient retry & model fallback."""
    payload = _build_gemini_payload(messages, tools=tools, max_tokens=max_tokens)
    data = json.dumps(payload).encode("utf-8")
    candidates_list = _candidate_models(model)
    last_error: RuntimeError | None = None

    raw: dict[str, Any] | None = None
    for idx, candidate_model in enumerate(candidates_list):
        safe_model = urllib.parse.quote(candidate_model, safe=".-_")
        url = f"{GEMINI_API_BASE}/{safe_model}:generateContent"
        for attempt in range(2):
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(_format_gemini_error(exc.code, body))
                if exc.code in TRANSIENT_HTTP_STATUSES and attempt == 0:
                    log.warning("Gemini %s returned %d, retrying shortly...", candidate_model, exc.code)
                    time.sleep(0.8)
                    continue
                if exc.code in (*TRANSIENT_HTTP_STATUSES, 404) and idx + 1 < len(candidates_list):
                    log.warning(
                        "Gemini %s failed (%d); falling back to %s",
                        candidate_model,
                        exc.code,
                        candidates_list[idx + 1],
                    )
                    break
                raise last_error from exc
            except Exception as exc:
                raise RuntimeError(f"Gemini API connection failed: {exc}") from exc
        if raw is not None:
            break

    if raw is None:
        raise last_error or RuntimeError("Gemini API request failed.")

    candidates = raw.get("candidates") or []
    if not candidates:
        block_reason = (raw.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise RuntimeError(f"Gemini blocked the prompt ({block_reason}).")
        return {"message": {"role": "assistant", "content": ""}, "done": True}

    text, tool_calls = _extract_parts(candidates[0])
    msg: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        msg["tool_calls"] = tool_calls

    usage = raw.get("usageMetadata") or {}
    return {
        "message": msg,
        "done": True,
        "prompt_eval_count": usage.get("promptTokenCount", 0),
        "eval_count": usage.get("candidatesTokenCount", 0),
    }


async def gemini_chat_stream(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 60.0,
    max_tokens: int = 512,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield normalized chat chunks from Gemini's SSE `streamGenerateContent` endpoint."""
    payload = _build_gemini_payload(messages, tools=tools, max_tokens=max_tokens)
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-goog-api-key": api_key,
    }

    client_timeout = aiohttp.ClientTimeout(total=timeout)
    candidates_list = _candidate_models(model)
    last_usage: dict[str, Any] = {}
    last_error: RuntimeError | None = None
    completed = False

    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            for idx, candidate_model in enumerate(candidates_list):
                safe_model = urllib.parse.quote(candidate_model, safe=".-_")
                url = f"{GEMINI_API_BASE}/{safe_model}:streamGenerateContent?alt=sse"
                should_fallback_model = False

                for attempt in range(2):
                    async with session.post(url, json=payload, headers=headers) as resp:
                        if resp.status >= 400:
                            body = await resp.text()
                            last_error = RuntimeError(_format_gemini_error(resp.status, body))
                            if resp.status in TRANSIENT_HTTP_STATUSES and attempt == 0:
                                log.warning(
                                    "Gemini stream %s returned %d, retrying shortly...",
                                    candidate_model,
                                    resp.status,
                                )
                                await asyncio.sleep(0.8)
                                continue
                            if resp.status in (*TRANSIENT_HTTP_STATUSES, 404) and idx + 1 < len(candidates_list):
                                log.warning(
                                    "Gemini stream %s failed (%d); falling back to %s",
                                    candidate_model,
                                    resp.status,
                                    candidates_list[idx + 1],
                                )
                                should_fallback_model = True
                                break
                            raise last_error

                        while True:
                            raw_line = await resp.content.readline()
                            if not raw_line:
                                break
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line.startswith("data:"):
                                continue
                            json_str = line[5:].strip()
                            if not json_str:
                                continue
                            try:
                                chunk = json.loads(json_str)
                            except json.JSONDecodeError:
                                continue

                            if "usageMetadata" in chunk:
                                last_usage = chunk["usageMetadata"] or {}

                            candidates = chunk.get("candidates") or []
                            if not candidates:
                                continue
                            text, tool_calls = _extract_parts(candidates[0])
                            msg_chunk: dict[str, Any] = {}
                            if text:
                                msg_chunk["content"] = text
                            if tool_calls:
                                msg_chunk["tool_calls"] = tool_calls
                            if msg_chunk:
                                yield {"message": msg_chunk, "done": False}
                        completed = True
                        break

                if completed:
                    break
                if not should_fallback_model:
                    break

        if not completed:
            raise last_error or RuntimeError("Gemini streaming request failed.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Gemini streaming request failed: {exc}") from exc

    yield {
        "message": {},
        "done": True,
        "prompt_eval_count": last_usage.get("promptTokenCount", 0),
        "eval_count": last_usage.get("candidatesTokenCount", 0),
    }
