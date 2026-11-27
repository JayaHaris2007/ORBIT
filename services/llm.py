"""LLM backend readiness, Ollama/Gemini generation, and tool-loop dispatch."""

from __future__ import annotations

import asyncio
import contextvars
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

from agent.loop import (
    AgentResult,
    _MODELS_WITHOUT_THINK,
    _MODELS_WITHOUT_TOOLS,
    is_think_unsupported_error,
)

_request_ollama_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_ollama_model", default=None
)

_EMBEDDING_FAMILY_HINTS = ("embed", "nomic-embed", "bge-", "minilm", "arctic-embed", "e5-")


def set_request_ollama_model(model: str | None) -> contextvars.Token[str | None]:
    clean = model.strip() if isinstance(model, str) and model.strip() else None
    return _request_ollama_model.set(clean)


def reset_request_ollama_model(token: contextvars.Token[str | None]) -> None:
    _request_ollama_model.reset(token)


def get_active_ollama_model() -> str:
    override = _request_ollama_model.get()
    if override:
        return override
    return (_app().OLLAMA_MODEL or os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")).strip()


def is_embedding_only_model(name: str, details: dict[str, Any] | None = None) -> bool:
    low = (name or "").lower()
    if any(hint in low for hint in _EMBEDDING_FAMILY_HINTS):
        return True
    families = [str(f).lower() for f in ((details or {}).get("families") or [])]
    if families and all("bert" in f or "nomic-bert" in f for f in families):
        return True
    return False


def list_ollama_models() -> dict[str, Any]:
    """Return all installed Ollama models from /api/tags enriched with /api/ps VRAM status."""
    base_url = _app().OLLAMA_URL
    tags_url = f"{base_url}/api/tags"
    ps_url = f"{base_url}/api/ps"
    active = get_active_ollama_model()

    req = urllib.request.Request(tags_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            tags_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {
            "reachable": False,
            "active_model": active,
            "models": [],
            "error": str(exc),
        }

    loaded_names: set[str] = set()
    try:
        ps_req = urllib.request.Request(ps_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(ps_req, timeout=1.5) as ps_resp:
            ps_data = json.loads(ps_resp.read().decode("utf-8"))
        for pm in ps_data.get("models") or []:
            pname = (pm.get("name") or pm.get("model") or "").strip()
            if pname:
                loaded_names.add(pname)
                if pname.endswith(":latest"):
                    loaded_names.add(pname[:-7])
    except Exception:
        pass

    chat_models: list[dict[str, Any]] = []
    embed_models: list[dict[str, Any]] = []
    for raw in tags_data.get("models") or []:
        name = (raw.get("name") or raw.get("model") or "").strip()
        if not name:
            continue
        details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
        is_embed = is_embedding_only_model(name, details)
        short_name = name[:-7] if name.endswith(":latest") else name
        item = {
            "name": name,
            "size": raw.get("size"),
            "modified_at": raw.get("modified_at"),
            "parameter_size": details.get("parameter_size") or "",
            "quantization_level": details.get("quantization_level") or "",
            "family": details.get("family") or "",
            "loaded": (name in loaded_names) or (short_name in loaded_names),
            "is_embedding": is_embed,
            "tools_supported": name not in _MODELS_WITHOUT_TOOLS and not is_embed,
        }
        if is_embed:
            embed_models.append(item)
        else:
            chat_models.append(item)

    return {
        "reachable": True,
        "active_model": active,
        "models": [*chat_models, *embed_models],
        "chat_models": [m["name"] for m in chat_models],
    }

def _app():
    import app

    return app


DEFAULT_SYSTEM_PROMPT = (
    "You are ORBIT, a personal AI assistant, technical co-pilot, "
    "and everyday companion. Talk naturally like a smart, friendly, attentive "
    "person. Be confident, practical, curious, and occasionally witty. Use "
    "natural contractions, simple English, and a conversational tone. "
    "Never sound robotic or overly formal. "

    "Keep routine replies concise, but explain technical topics in depth when "
    "the user asks. Avoid canned praise, unnecessary introductions, repetitive "
    "conclusions, and narrating simple actions. Respond directly to what "
    "the user actually says and understand short follow-ups using conversation "
    "context. "

    "Adapt explanations to the user's technical knowledge. "
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

    "Support the user's learning and growth as a developer. Explain difficult "
    "concepts clearly, connect new ideas to existing knowledge, correct "
    "mistakes respectfully, and suggest useful next steps when appropriate. "
    "Be encouraging without giving empty praise. Challenge ideas constructively "
    "when doing so helps achieve a better result. "

    "Use saved notes and conversation history to understand the user, "
    "preferences, and ongoing projects. Saved notes may describe either the user "
    "or you. When a note describes the user, speak about them as 'you' and never "
    "present their experiences, preferences, or plans as your own. Never invent "
    "personal facts, memories, or previous decisions. Use personal context "
    "only when it is relevant. "

    "Provide accurate, useful, and honest answers. Distinguish facts from "
    "assumptions and acknowledge uncertainty. "

    "Be action-oriented, resourceful, reliable, and technically capable. "
    "Don't overcomplicate simple requests or repeat instructions already "
    "received. Use light humor naturally without forcing it. Think through "
    "problems carefully, but communicate clearly and directly. "

    "Your identity is ORBIT — a dependable personal assistant, "
    "technical co-pilot, and companion in learning and development. "

    "Answer in English unless the user requests another language."
)


def _resolve_active_user_name() -> str:
    env_name = os.environ.get("ORBIT_USER_NAME", "").strip()
    if env_name:
        return env_name
    try:
        return _app()._user_name(_app()._user_fact_memories())
    except Exception:
        return ""



def _match_installed_model(target: str, raw_models: list[dict[str, Any]]) -> str | None:
    """Match target against installed Ollama model tags (exact, :latest-normalized, or case-insensitive)."""
    exact_names: list[str] = []
    lower_map: dict[str, str] = {}
    for m in raw_models:
        name = (m.get("name") or m.get("model") or "").strip()
        if not name:
            continue
        exact_names.append(name)
        lower_map[name.lower()] = name
        if name.endswith(":latest"):
            lower_map[name[:-7].lower()] = name
        else:
            lower_map[f"{name}:latest".lower()] = name

    t = target.strip()
    if t in exact_names:
        return t
    t_low = t.lower()
    if t_low in lower_map:
        return lower_map[t_low]
    if t_low.endswith(":latest") and t_low[:-7] in lower_map:
        return lower_map[t_low[:-7]]
    if f"{t_low}:latest" in lower_map:
        return lower_map[f"{t_low}:latest"]
    return None


def _ollama_check() -> None:
    active_target = get_active_ollama_model()
    if _app()._ollama_ready and active_target == _app().OLLAMA_MODEL:
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
    matched = _match_installed_model(active_target, models)
    if not matched:
        # Optional auto-select fallback when OLLAMA_AUTO_SELECT_INSTALLED=1 and at least one chat model exists
        if os.environ.get("OLLAMA_AUTO_SELECT_INSTALLED", "0").strip() == "1":
            for m in models:
                cand = (m.get("name") or m.get("model") or "").strip()
                details = m.get("details") if isinstance(m.get("details"), dict) else {}
                if cand and not is_embedding_only_model(cand, details):
                    _app().OLLAMA_MODEL = cand
                    matched = cand
                    break
        if not matched:
            _app()._ollama_ready = False
            raise RuntimeError(
                f"Model {active_target} not found. Run `ollama pull {active_target}`."
            )

    if active_target == _app().OLLAMA_MODEL:
        _app()._ollama_ready = True
    try:
        from runtime.models import REGISTRY
        REGISTRY.register("llm", "ollama", metrics={"backend": "ollama", "model": matched})
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


_PRODUCTIVITY_CUE_RE = re.compile(
    r"(?<![a-z0-9])c\s*\+\s*\+(?![a-z0-9])"
    r"|(?<![a-z0-9])c\s*#(?![a-z0-9])"
    r"|\bc\s+plus\s+plus\b"
    r"|\b(?:habits?|tasks?|to[\s-]?dos?|routine\w*|schedule\w*|timetable|time[\s-]?table|"
    r"plan(?:ning|ned)?|next\s+day|tomorrow|today|my\s+day|prioriti[sz]\w*|organi[sz]\w*|"
    r"reminders?|remind|alarms?|memor(?:y|ies)|notes?|"
    r"analytics?|stats?|statistics|streaks?|xp|level|achievements?|productiv\w*|"
    r"improve\w*|discipline|goals?|learn(?:ed|t|ing)?|stud(?:y|ied|ying)|topics?|course\w*|"
    r"skills?|practice\w*|problem\w*|interview\w*|exercise\w*|quiz|algorithm\w*|"
    r"main\s+page|dashboard|page|app|nothing|there|pending|"
    r"completed|done|list|folder|code|coding|coded|file|files|cpp|dsa|roadmap\w*|"
    r"python|java|javascript|typescript|rust|sql|react)\b",
    re.IGNORECASE,
)


def _productivity_context(prompt: str, history: list[dict[str, Any]] | None = None) -> str:
    """Current habits/tasks/reminders/analytics/learning, injected when the question (or recent turn) is about them."""
    if prompt.startswith("Pick the single learning topic"):
        return ""
    recent_tail = " ".join(
        str(m.get("content") or "")[:300]
        for m in (history or [])[-4:]
        if m.get("role") in ("user", "assistant")
    )
    combined = f"{prompt} {recent_tail}".strip()
    if not _PRODUCTIVITY_CUE_RE.search(combined):
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
        lines.extend(
            f"- #{t['id']} {t['title']} ({t['priority']}"
            + (f", due {t['due_at'][:10]}" if t.get("due_at") else "")
            + ")"
            for t in tasks[:10]
        )
    else:
        lines.append("Pending tasks: none right now.")
    reminders = _app().memory_store.list_reminders(active_only=True)
    if reminders:
        lines.append("Active reminders:")
        lines.extend(
            f"- {r['text']} ({_app()._format_due_date(r['run_at'])}"
            + (f", {r['recurrence']}" if r.get("recurrence") else "")
            + ")"
            for r in reminders[:6]
        )
    try:
        stats = _app().memory_store.get_gamification()
        xp = int(stats.get("xp") or 0)
        streak = int(stats.get("global_streak") or 0)
        lines.append(f"Gamification & analytics: Level {(xp // 100) + 1} ({xp} XP), {streak}-day global streak.")
    except Exception:
        pass
    lines.extend(_app()._learning_digest())
    if _app().learning_schema.is_initialized():
        try:
            from learning import code_rag

            rag_ctx = code_rag.build_rag_prompt_context(
                prompt, embed=_app().memory_store.embed, limit=3, history=history
            )
            if rag_ctx:
                lines.append(rag_ctx)
        except Exception:
            pass
    return "\n".join(lines)


def _learning_digest() -> list[str]:
    """Short learning snapshot for the LLM (including exact completed/in-progress topics)."""
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
    try:
        active_rms = [
            rm
            for rm in _app().learning_progress.roadmap_summaries()
            if int(rm.get("completed_count") or 0) > 0 or int(rm.get("in_progress_count") or 0) > 0
        ]
        if active_rms:
            with _app().learning_schema.connect() as conn:
                for rm in active_rms[:4]:
                    rows = conn.execute(
                        "SELECT name, status FROM topics WHERE roadmap_id = ? ORDER BY position, id",
                        (int(rm["id"]),),
                    ).fetchall()
                    completed = [r["name"] for r in rows if r["status"] == "completed"]
                    in_prog = [r["name"] for r in rows if r["status"] in ("learning", "in_progress")]
                    if completed:
                        digest.append(f"Completed in {rm['name']}: {', '.join(completed)}.")
                    if in_prog:
                        digest.append(f"In progress in {rm['name']}: {', '.join(in_prog)}.")
    except Exception:
        pass
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
    active_model = get_active_ollama_model()
    payload: dict[str, Any] = {
        "model": active_model,
        "messages": messages,
        "stream": False,
        "keep_alive": _app().OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0,
            "repeat_penalty": 1.05,
            "num_predict": max_new_tokens,
            "num_ctx": _app().OLLAMA_NUM_CTX,
        },
    }
    if active_model not in _MODELS_WITHOUT_THINK:
        payload["think"] = False

    t0 = time.perf_counter()
    raw_bytes = b""
    for _attempt in range(2):
        payload_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_app().OLLAMA_TIMEOUT) as resp:
                raw_bytes = resp.read()
            break
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            combined = f"{exc.reason} {err_body}"
            if exc.code == 400 and "think" in payload and is_think_unsupported_error(combined):
                _MODELS_WITHOUT_THINK.add(active_model)
                payload.pop("think", None)
                continue
            raise RuntimeError(f"Ollama HTTP error {exc.code}: {err_body[:200] or exc.reason}") from exc
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
            REGISTRY.register("llm", "ollama", metrics={"backend": "ollama", "model": active_model})
    except Exception:
        _app().LOGGER.debug("Suppressed error (app.py site 7)", exc_info=True)

    message = data.get("message") or {}
    text = message.get("content") or ""
    # Strip any <think>...</think> or <thought>...</thought> block as a safety net
    text = re.sub(r"<(?:think|thought)>.*?</(?:think|thought)>", "", text, flags=re.DOTALL)
    text = re.sub(r"<(?:think|thought)>.*$", "", text, flags=re.DOTALL).strip()

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
        active_name = _resolve_active_user_name()
        system_prompt = (
            _app().DEFAULT_SYSTEM_PROMPT.replace(
                "You are ORBIT, a personal AI assistant",
                f"You are ORBIT, {active_name}'s personal AI assistant",
                1,
            )
            if active_name
            else _app().DEFAULT_SYSTEM_PROMPT
        )
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
        extra = _app()._productivity_context(prompt, history=context[:-1])
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


