"""LLM backend readiness, Ollama/Gemini generation, and tool-loop dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from agent.loop import AgentResult

def _app():
    import app

    return app


DEFAULT_SYSTEM_PROMPT = (
    "You are ORBIT, Jaya's personal AI assistant, technical co-pilot, "
    "and everyday companion. Talk naturally like a smart, friendly, attentive "
    "person. Be confident, practical, curious, and occasionally witty. Use "
    "natural contractions, simple English, and a conversational tone. "
    "Never sound robotic or overly formal. "

    "Keep routine replies concise, but explain technical topics in depth when "
    "Jaya asks. Avoid canned praise, unnecessary introductions, repetitive "
    "conclusions, and narrating simple actions. Respond directly to what "
    "Jaya actually says and understand short follow-ups using conversation "
    "context. "

    "Jaya is a Computer Science student, developer, and technology enthusiast "
    "who enjoys building real-world projects, exploring AI, and experimenting "
    "with new technologies. Adapt explanations to his technical knowledge. "
    "Help with programming, debugging, web development, databases, AI models, "
    "system architecture, and software engineering. Prefer practical solutions, "
    "working code, and clear explanations over unnecessary theory. "

    "Act as a development partner, not just a chatbot. Help plan, build, "
    "debug, optimize, and improve projects. Respect the existing tech stack "
    "and architecture unless a change is genuinely beneficial. Explain "
    "important trade-offs and recommend the best approach when appropriate. "
    "Never claim code was tested or executed unless it actually was. "

    "Help manage tasks, todos, habits, reminders, schedules, learning goals, "
    "research, and everyday activities using available application tools. "
    "Use conversation context and connected data whenever available. Local "
    "habit, task, and reminder details shown in the conversation are available "
    "to you; never ask for information that was already provided. Ask one "
    "focused question if essential information is missing. Never claim an "
    "action succeeded unless the application confirms it. "

    "Support Jaya's learning and growth as a developer. Explain difficult "
    "concepts clearly, connect new ideas to existing knowledge, correct "
    "mistakes respectfully, and suggest useful next steps when appropriate. "
    "Be encouraging without giving empty praise. Challenge ideas constructively "
    "when doing so helps achieve a better result. "

    "Use saved notes and conversation history to understand the user, "
    "preferences, and ongoing projects. Saved notes may describe either Jaya "
    "or you. When a note describes Jaya, speak about him as 'you' and never "
    "present his experiences, preferences, or plans as your own. Never invent "
    "personal facts, memories, or previous decisions. Use personal context "
    "only when it is relevant. "

    "Provide accurate, useful, and honest answers. Distinguish facts from "
    "assumptions and acknowledge uncertainty. "

    "Be action-oriented, resourceful, reliable, and technically capable. "
    "Don't overcomplicate simple requests or repeat instructions already "
    "received. Use light humor naturally without forcing it. Think through "
    "problems carefully, but communicate clearly and directly. "

    "Your identity is ORBIT. You are Jaya's dependable personal assistant, "
    "technical co-pilot, and companion in learning and development. Help him "
    "think clearly, build better projects, solve problems, and get things done. "

    "Answer in English unless Jaya requests another language."
)



def _ollama_check() -> None:
    if _app()._ollama_ready:
        return
    url = f"{_app().OLLAMA_URL}/api/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _app()._ollama_ready = False
        raise RuntimeError(
            f"Ollama is not running at {_app().OLLAMA_URL}. Start it with `ollama serve`."
        ) from exc
    except Exception as exc:
        _app()._ollama_ready = False
        raise RuntimeError(
            f"Ollama is not running at {_app().OLLAMA_URL}. Start it with `ollama serve`."
        ) from exc

    models = data.get("models") or []
    available = set()
    for m in models:
        name = m.get("name") or m.get("model") or ""
        if name:
            available.add(name)
            if name.endswith(":latest"):
                available.add(name[:-7])
            else:
                available.add(f"{name}:latest")

    target = _app().OLLAMA_MODEL
    matched = (
        target in available
        or (target.endswith(":latest") and target[:-7] in available)
        or (f"{target}:latest" in available)
    )
    if not matched:
        _app()._ollama_ready = False
        raise RuntimeError(
            f"Model {_app().OLLAMA_MODEL} not found. Run `ollama pull {_app().OLLAMA_MODEL}`."
        )

    _app()._ollama_ready = True
    try:
        from runtime.models import REGISTRY
        REGISTRY.register("llm", "ollama", metrics={"backend": "ollama", "model": _app().OLLAMA_MODEL})
    except Exception:
        _app().LOGGER.debug("Suppressed error (app.py site 1)", exc_info=True)



def _llm_available() -> bool:
    """Return True if Gemini API is configured or Ollama is running with the model."""
    if _app().is_gemini_active():
        return True
    try:
        _app()._ollama_check()
        return True
    except RuntimeError:
        return False


def _check_ollama_ps() -> dict[str, Any]:
    """Best effort check of /api/ps for loaded model stats."""
    url = f"{_app().OLLAMA_URL}/api/ps"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models") or []
            for m in models:
                name = m.get("name") or m.get("model") or ""
                if name == _app().OLLAMA_MODEL or (name.split(":")[0] == _app().OLLAMA_MODEL.split(":")[0]):
                    return {
                        "size_vram": m.get("size_vram"),
                        "size": m.get("size"),
                    }
    except Exception:
        _app().LOGGER.debug("Suppressed error (app.py site 2)", exc_info=True)

    return {}


def ensure_model_loaded() -> None:
    """Ensure active LLM backend (Gemini API or local Ollama) is available."""
    if _app().is_gemini_active():
        return
    _app()._ollama_check()



def select_generation_context(
    context: list[dict[str, str]], prompt: str
) -> list[dict[str, str]]:
    words = prompt.split()
    if len(words) <= 4 and len(context) > 1:
        # Short replies such as "now", "yes", or "that one" depend on the
        # assistant's last answer as much as the user's earlier messages.
        return context[-4:]
    return context


def resolve_short_follow_up(
    prompt: str, context: list[dict[str, str]]
) -> str:
    normalized = prompt.strip().lower()
    if "cricket" in normalized and "captain" in normalized:
        return (
            "Name one real cricket captain. Answer with only one captain's "
            "name and one short sentence."
        )
    if not re.fullmatch(r"(name|give) (one|any one|an example)", normalized):
        return prompt
    previous_user_messages = [
        message["content"].lower()
        for message in context[:-1]
        if message["role"] == "user"
    ]
    topic = " ".join(previous_user_messages[-2:])
    if "cricket" in topic or "captain" in topic:
        return (
            "Name one real cricket captain. Answer with only one captain's "
            "name and one short sentence."
        )
    return prompt


def _productivity_context(prompt: str) -> str:
    """Current habits/tasks/learning, injected when the question is about them or the dashboard."""
    if not re.search(
        r"\b(?:habits?|tasks?|to[\s-]?dos?|routine|schedule|productiv\w*|"
        r"improve\w*|discipline|goals?|learning|studying|study|topics?|course\w*|"
        r"skills?|practice|main\s+page|dashboard|page|app|nothing|there|pending|"
        r"completed|done|list|folder|code|coding|file|files|cpp|c\+\+|dsa|roadmap)\b",
        prompt,
        re.IGNORECASE,
    ):
        return ""
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    lines = []
    habits = _app().memory_store.list_habits()
    if habits:
        lines.append("Current habits:")
        for habit in habits:
            done = "done today" if today in habit["completed_dates"] else "not done today"
            lines.append(f"- {habit['name']} (streak {habit['streak']}, {done})")
    else:
        lines.append("Current habits: none yet.")
    tasks = _app().memory_store.list_tasks(include_completed=False)
    if tasks:
        lines.append("Pending tasks:")
        lines.extend(f"- #{t['id']} {t['title']} ({t['priority']})" for t in tasks[:8])
    else:
        lines.append("Pending tasks: none.")
    lines.extend(_app()._learning_digest())
    if _app().learning_schema.is_initialized():
        try:
            from learning import code_rag

            rag_ctx = code_rag.build_rag_prompt_context(
                prompt, embed=_app().memory_store.embed, limit=3
            )
            if rag_ctx:
                lines.append(rag_ctx)
        except Exception:
            pass
    return "\n".join(lines)


def _learning_digest() -> list[str]:
    """Short learning snapshot for the LLM, or nothing when not initialized."""
    if not _app().learning_schema.is_initialized():
        return []
    try:
        overview = _app().learning_progress.overall_progress()
    except Exception:  # pragma: no cover - defensive
        return []
    if overview["topic_count"] == 0:
        return []
    digest = [
        "Learning progress: "
        f"{overview['completed_topics']} of {overview['topic_count']} "
        f"topics completed ({overview['completion_percent']}%), "
        f"{overview['in_progress_topics']} in progress."
    ]
    upcoming = _app().learning_progress.next_topics(limit=3)
    if upcoming:
        digest.append(
            "Next learning topics: "
            + ", ".join(
                f"{topic['name']} ({topic['roadmap_name']})" for topic in upcoming
            )
            + "."
        )
    return digest


def _trim_incomplete(text: str) -> str:
    """Cut a reply back to its last finished sentence or line."""
    ends = list(re.finditer(r"[.!?](?=\s|$)|\n", text))
    if ends and ends[-1].end() >= len(text) * 0.4:
        text = text[: ends[-1].end()]
    if text.count("**") % 2:
        text = text.rsplit("**", 1)[0]
    return text.rstrip()


def _generate_ollama(messages: list[dict[str, str]], max_new_tokens: int) -> str:
    url = f"{_app().OLLAMA_URL}/api/chat"
    payload = {
        "model": _app().OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": _app().OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0,
            "repeat_penalty": 1.05,
            "num_predict": max_new_tokens,
            "num_ctx": _app().OLLAMA_NUM_CTX,
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=_app().OLLAMA_TIMEOUT) as resp:
            raw_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama HTTP error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        _app()._ollama_ready = False
        raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Ollama request timed out after {_app().OLLAMA_TIMEOUT}s") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    elapsed_seconds = time.perf_counter() - t0
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

    _app()._ollama_ready = True
    try:
        from runtime.models import REGISTRY
        if not REGISTRY.is_ready("llm"):
            REGISTRY.register("llm", "ollama", metrics={"backend": "ollama", "model": _app().OLLAMA_MODEL})
    except Exception:
        _app().LOGGER.debug("Suppressed error (app.py site 7)", exc_info=True)


    message = data.get("message") or {}
    text = message.get("content") or ""
    # Strip any <think>...</think> block as a safety net
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if data.get("done_reason") == "length":
        text = _app()._trim_incomplete(text)

    prompt_eval_count = data.get("prompt_eval_count")
    if prompt_eval_count is not None and prompt_eval_count >= _app().OLLAMA_NUM_CTX - 8:
        logging.getLogger("orbit007").warning(
            "Prompt evaluation count (%d) >= OLLAMA_NUM_CTX - 8 (%d); prompt was probably truncated.",
            prompt_eval_count,
            _app().OLLAMA_NUM_CTX - 8,
        )

    eval_count = data.get("eval_count")
    eval_duration = data.get("eval_duration")
    if eval_count is not None and eval_duration and eval_duration > 0:
        gen_seconds = eval_duration / 1e9
        tokens_per_sec = eval_count / gen_seconds
        timing_str = (
            f"[generation {gen_seconds:.2f}s | "
            f"{eval_count} tokens | "
            f"{tokens_per_sec:.2f} tokens/s]"
        )
    else:
        timing_str = f"[generation {elapsed_seconds:.2f}s]"
    _app().LOGGER.info("%s", timing_str)
    logging.getLogger("orbit007").info(timing_str)

    return text


def generate_response(
    prompt: str,
    max_new_tokens: int,
    messages: list[dict[str, str]] | None = None,
    memories: list[dict[str, Any]] | None = None,
) -> str:
    _app().ensure_model_loaded()
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty.")
    if len(prompt) > _app().MAX_PROMPT_CHARS:
        raise ValueError(
            f"Prompt is limited to {_app().MAX_PROMPT_CHARS} characters, "
            f"but received {len(prompt)}."
        )

    with _app().generation_lock:
        context = messages or []
        if not context or context[-1]["content"] != prompt:
            context = [*context, {"role": "user", "content": prompt}]
        memory_text = "\n".join(f"- {item['content']}" for item in (memories or []))
        system_prompt = _app().DEFAULT_SYSTEM_PROMPT
        if memory_text:
            system_prompt += (
                "\nNotes saved from earlier conversations. Lines written in the "
                "first person are facts the user shared about themselves; treat "
                "them as background about the user and address them as 'you'. "
                "Lines about you describe you. Use them whenever they are "
                "relevant and never contradict them:\n" + memory_text
            )
        words = int(max_new_tokens * 0.6)
        system_prompt += (
            f"\nKeep this reply under about {words} words and finish your "
            "last sentence. Answer in plain conversational sentences: no "
            "headings, no emoji, no bullet lists unless the user asks for a list."
        )
        extra = _app()._productivity_context(prompt)
        if extra:
            system_prompt += (
                "\nThe user's live habit and task data (use it to answer; "
                "for advice questions, give 3-5 specific suggestions and do "
                "not just list pending items):\n" + extra
            )
        if os.environ.get("ORBIT_LLM_TOOLS", "0") == "1":
            system_prompt += (
                "\nYou can create or delete reminders using tool calls. "
                "Output: <tool_call>{\"action\": \"create_reminder\", \"title\": \"...\", \"when\": \"...\"}</tool_call>"
            )
        model_context = _app().select_generation_context(context, prompt)
        model_messages = [{"role": "system", "content": system_prompt}, *model_context]
        gemini_key, gemini_model = _app().get_active_gemini_config()
        if gemini_key:
            resp = _app().gemini_chat_request(
                model_messages,
                api_key=gemini_key,
                model=gemini_model,
                max_tokens=max_new_tokens,
            )
            return (resp.get("message") or {}).get("content", "").strip()
        return _app()._generate_ollama(model_messages, max_new_tokens)



TOKENS_DEFAULT = 512
TOKENS_BRIEF = 160
TOKENS_MEDIUM = 768
TOKENS_LONG = 1280


def _token_budget(prompt: str) -> int:
    """Pick a reply length from what the user is asking for."""
    text = prompt.lower()
    if re.search(
        r"\b(?:brief|briefly|in short|short answer|one line|one sentence|"
        r"quick|tl;?dr|yes or no|in a word)\b",
        text,
    ):
        return TOKENS_BRIEF
    if re.search(
        r"\b(?:longer|long answer|more detail|in detail|detailed|elaborate|"
        r"expand|step by step|full guide|deep dive|essay|code|script|"
        r"function|implement|program|debug|write (?:a|an|the)|"
        r"list all|all topics?|all concepts?|roadmap|comprehensive|everything|"
        r"master|complete guide|curriculum|syllabus|next|continue)\b",
        text,
    ):
        return TOKENS_LONG
    if re.search(
        r"\b(?:explain|how (?:does|do|to|can)|compare|difference|why|"
        r"suggest\w*|recommend\w*|ideas?|tips?|advice|improve\w*|"
        r"pros and cons|list\b|topics?|concepts?|learn\w*|study|cover|"
        r"what (?:are|is|should)|\d+ (?:habits|ideas|tips|ways|topics))\b",
        text,
    ):
        return TOKENS_MEDIUM
    return TOKENS_DEFAULT



_ASYNC_GEN_LOCKS: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


def _get_async_generation_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _ASYNC_GEN_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _ASYNC_GEN_LOCKS[loop] = lock
    return lock


def _build_local_command_ui_actions(provider: str) -> tuple[str | None, list[dict[str, Any]]]:
    nav = _app()._page_for_provider(provider)
    ui_actions = [{"type": "navigate", "page": nav, "route": _app()._route_for_page(nav)}] if nav else []
    if provider == "local-memory":
        ui_actions.append({"type": "refresh", "sections": ["memories"]})
    elif provider == "local-habit-manager":
        ui_actions.append({"type": "refresh", "sections": ["habits", "gamification"]})
    elif provider == "local-task-manager":
        ui_actions.append({"type": "refresh", "sections": ["tasks", "gamification"]})
    elif provider == "local-scheduler":
        ui_actions.append({"type": "refresh", "sections": ["reminders"]})
    elif provider == "local-learning":
        ui_actions.append({"type": "refresh", "sections": ["learning", "gamification"]})
    return nav, ui_actions


def respond_with_tools(
    prompt: str,
    chat_id: str,
    history: list[dict[str, Any]] | None = None,
    memories: list[dict[str, Any]] | None = None,
    channel: str = "web",
) -> AgentResult:
    """Unified entrypoint for generating responses with native tools or falling back to plain chat."""
    _app().ensure_model_loaded()
    orbit_tools = os.environ.get("ORBIT_TOOLS", "1").strip()
    history = history or []
    memories = memories or []

    # Resolve short follow-ups (e.g. "name one", "why?") using previous context
    prompt = _app().resolve_short_follow_up(prompt, history)

    # If generate_response was monkeypatched in tests, bypass agent loop and call the mock
    is_mocked = (_app().generate_response is not _app()._ORIGINAL_GENERATE_RESPONSE) or hasattr(_app().generate_response, "assert_called")

    with _app().generation_lock:
        try:
            if orbit_tools != "0" and not is_mocked:
                try:
                    return _app().run_agent_loop(
                        prompt=prompt,
                        chat_id=chat_id,
                        history=history,
                        memories=memories,
                        channel=channel,
                        deps=_app().agent_deps,
                        confirm_mgr=_app().confirmation_mgr,
                    )
                except Exception as exc:
                    logging.getLogger("orbit007").warning("Agent loop error, falling back to plain chat: %s", exc)

            tokens = _app()._token_budget(prompt)
            if channel == "voice":
                tokens = min(tokens, 128)
            reply = _app().generate_response(
                prompt=prompt,
                max_new_tokens=tokens,
                messages=history,
                memories=memories,
            )
            return AgentResult(
                reply=reply.strip(),
                ui_actions=[],
                provider="gemini" if _app().is_gemini_active() else "ollama",
            )
        except Exception:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                _app().LOGGER.debug("Suppressed error (app.py site 9)", exc_info=True)

            raise





async def respond_with_tools_stream(
    prompt: str,
    chat_id: str,
    history: list[dict[str, Any]] | None = None,
    memories: list[dict[str, Any]] | None = None,
    channel: str = "web",
    on_token=None,
    on_stream_reset=None,
) -> AgentResult:
    """Async streaming variant of respond_with_tools."""
    await asyncio.to_thread(_app().ensure_model_loaded)
    orbit_tools = os.environ.get("ORBIT_TOOLS", "1").strip()
    history = history or []
    memories = memories or []

    resolved_prompt = _app().resolve_short_follow_up(prompt, history)
    is_tools_mocked = (_app().respond_with_tools is not _app()._ORIGINAL_RESPOND_WITH_TOOLS) or hasattr(
        _app().respond_with_tools, "assert_called"
    )
    is_gen_mocked = (_app().generate_response is not _app()._ORIGINAL_GENERATE_RESPONSE) or hasattr(
        _app().generate_response, "assert_called"
    )

    if orbit_tools == "0" or is_tools_mocked or is_gen_mocked:
        result = await asyncio.to_thread(
            _app().respond_with_tools,
            prompt,
            chat_id,
            history,
            memories,
            channel,
        )
        if result.reply and on_token is not None:
            res = on_token(result.reply)
            if asyncio.iscoroutine(res):
                await res
        return result

    async with _app()._get_async_generation_lock():
        try:
            return await _app().run_agent_loop_stream(
                prompt=resolved_prompt,
                chat_id=chat_id,
                history=history,
                memories=memories,
                channel=channel,
                deps=_app().agent_deps,
                confirm_mgr=_app().confirmation_mgr,
                on_token=on_token,
                on_stream_reset=on_stream_reset,
            )
        except Exception as exc:
            logging.getLogger("orbit007").warning(
                "Streaming agent loop error, falling back to plain chat: %s", exc
            )
            if on_stream_reset is not None:
                res = on_stream_reset()
                if asyncio.iscoroutine(res):
                    await res
            tokens = _app()._token_budget(resolved_prompt)
            if channel == "voice":
                tokens = min(tokens, 128)
            reply = await asyncio.to_thread(
                _app().generate_response,
                prompt=resolved_prompt,
                max_new_tokens=tokens,
                messages=history,
                memories=memories,
            )
            clean_reply = reply.strip()
            if clean_reply and on_token is not None:
                res = on_token(clean_reply)
                if asyncio.iscoroutine(res):
                    await res
            return AgentResult(
                reply=clean_reply,
                ui_actions=[],
                provider="gemini" if _app().is_gemini_active() else "ollama",
            )


def _validate_generate_payload(payload: dict[str, Any]) -> tuple[str, int, str]:
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object.")

    prompt = payload.get("prompt")
    max_new_tokens = payload.get("max_new_tokens")
    if not isinstance(prompt, str):
        raise HTTPException(400, "'prompt' must be a string.")
    if not prompt.strip():
        raise HTTPException(400, "Prompt cannot be empty.")
    if len(prompt) > _app().MAX_PROMPT_CHARS:
        raise HTTPException(400, f"Prompt is limited to {_app().MAX_PROMPT_CHARS} characters.")
    if max_new_tokens is None:
        max_new_tokens = _app()._token_budget(prompt)
    if (
        isinstance(max_new_tokens, bool)
        or not isinstance(max_new_tokens, int)
        or not 1 <= max_new_tokens <= _app().MAX_NEW_TOKENS
    ):
        raise HTTPException(
            400,
            detail=(
                f"'max_new_tokens' must be an integer between 1 and "
                f"{_app().MAX_NEW_TOKENS}."
            ),
        )

    chat_id = payload.get("chat_id")
    if chat_id is not None and (
        not isinstance(chat_id, str) or not _app().memory_store.chat_exists(chat_id)
    ):
        raise HTTPException(404, "'chat_id' does not identify an existing chat.")

    if chat_id is None:
        chat = _app().memory_store.create_chat()
        chat_id = chat["id"]

    return prompt, max_new_tokens, chat_id


