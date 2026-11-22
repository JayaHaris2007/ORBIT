"""Deterministic parsers and formatters for tasks, habits, and web search."""

from __future__ import annotations

import difflib
import logging
import re
from datetime import datetime
from typing import Any

def _app():
    import app

    return app


def _normalize_command(prompt: str) -> str:
    """Strip greetings, politeness, conversational lead-ins, and trailing punctuation."""
    normalized = re.sub(r"\s+", " ", prompt.strip()).rstrip(".!?")
    normalized = re.sub(
        r"^(?:hey\s+|hi\s+|hello\s+)?(?:spidey|s\.p\.i\.d\.e\.y)[,\s]+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    # Collapse split or hyphenated negative/action prefixes ("un mark" -> "unmark", "re open" -> "reopen")
    normalized = re.sub(
        r"\bun[\s\-]+(mark(?:ed)?|check(?:ed)?|complet(?:e|ed)|tick(?:ed)?|do(?:ne)?)\b",
        r"un\1",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bre[\s\-]+(open(?:ed)?|start(?:ed)?)\b",
        r"re\1",
        normalized,
        flags=re.IGNORECASE,
    )
    # Strip conversational filler prefixes ("Now I am...", "Okay please...", "I mean...")
    # while preserving short follow-up phrases like "now" or "okay now".
    if len(normalized.split()) > 2:
        normalized = re.sub(
            r"^(?:(?:now|okay|ok|alright|so|well|actually|hey|wait|sorry|oops|no\s+i\s+mean|i\s+mean|i\s+meant)\b[,\s]*)+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
    normalized = re.sub(
        r"^(?:(?:please|kindly)\s+|(?:can|could|would)\s+you\s+)+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip()



_WEB_SEARCH_PATTERN = re.compile(
    r"^(?:web\s*search|search\s+(?:the\s+)?(?:web|internet|online)"
    r"|(?:google|bing|duckduckgo)|browse\s+(?:the\s+)?(?:web|internet))"
    r"(?:\s+(?:for|about|on))?\s+(?P<query>.+)$",
    re.IGNORECASE,
)
_WEB_SEARCH_SUFFIX_PATTERN = re.compile(
    r"^(?P<query>.+?)\s+(?:on\s+(?:the\s+)?(?:web|internet|google)|"
    r"in\s+web\s*search|with\s+web\s*search|via\s+web\s*search|"
    r"search\s+(?:the\s+)?(?:web|online)|web\s*search)$",
    re.IGNORECASE,
)
_LATEST_NEWS_SEARCH_PATTERN = re.compile(
    r"^(?:what\s+(?:are|is)\s+(?:the\s+)?)?(?:latest|breaking|current|today'?s)\s+"
    r"(?:news|headlines|updates)\s+(?:in|about|on|for|from)\s+(?P<query>.+)$",
    re.IGNORECASE,
)
# "search for india sports news" and "look up the score" mean the same thing.
_PLAIN_SEARCH_PATTERN = re.compile(
    r"^(?:search|look\s+(?:it\s+|this\s+)?up)\s+(?:for\s+|about\s+|on\s+)?(?P<query>.+)$",
    re.IGNORECASE,
)
# Keep local data queries local: "search my tasks", "search reminders", ...
_LOCAL_SEARCH_TARGET = re.compile(
    r"^(?:(?:my|the|a|an|all)\s+)*(?:tasks?|to[\s-]?dos?|habits?|reminders?|"
    r"memor(?:y|ies)|notes?|chats?|conversations?|history|lists?|productivity)\b",
    re.IGNORECASE,
)


def _parse_web_search_query(prompt: str) -> str | None:
    """Return the query of a search request, else None."""
    normalized = _app()._normalize_command(prompt)
    match = _WEB_SEARCH_PATTERN.match(normalized)
    if not match:
        match = _WEB_SEARCH_SUFFIX_PATTERN.match(normalized)
        if match:
            cleaned = re.sub(
                r"^(?:what\s+(?:are|is)\s+(?:the\s+)?|tell\s+me\s+(?:about\s+)?|"
                r"find\s+(?:me\s+)?|show\s+(?:me\s+)?)",
                "",
                match.group("query").strip(),
                flags=re.IGNORECASE,
            )
            return cleaned.strip(" \"'") if len(cleaned.strip(" \"'")) >= 2 else None
    if not match:
        match = _LATEST_NEWS_SEARCH_PATTERN.match(normalized)
        if match:
            topic = match.group("query").strip(" \"'")
            return f"latest news in {topic}" if len(topic) >= 2 else None
    if not match:
        match = _PLAIN_SEARCH_PATTERN.match(normalized)
        if not match or _LOCAL_SEARCH_TARGET.match(match.group("query")):
            return None
    query = match.group("query").strip(" \"'")
    return query if len(query) >= 2 else None


def _search_snippet(text: str, limit: int = 200) -> str:
    # Page text often arrives with scraped markdown headings and nav crumbs.
    text = re.sub(r"[#*_>`]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rsplit(' ', 1)[0]}…"


def _web_search_reply(query: str) -> tuple[str, str]:
    """Run one live search and format the hits as chat-friendly markdown."""
    try:
        sources = _app().web_search(query, max_results=5, search_depth="basic")
    except _app().SearchNotConfigured as error:
        _app().LOGGER.warning("Web search unavailable: %s", error)
        return (
            "I can search the web, but the search key is not set yet. Add "
            "TAVILY_API_KEY to the .env file next to app.py, restart the server, "
            "and ask me again.",
            "web-search-unconfigured",
        )
    except _app().SearchFailed as error:
        logging.getLogger("orbit007").warning("Web search failed for %r: %s", query, error)
        return (
            "I reached for the web but the search provider didn't answer. "
            "Give it another try in a moment.",
            "web-search-failed",
        )
    except Exception as error:
        logging.getLogger("orbit007").warning("Web search error for %r: %s", query, error)
        return (
            "Web search is currently unavailable or timed out. Please try again in a moment.",
            "web-search-failed",
        )
    if not sources:
        return (
            f"I searched for **{query}** but nothing solid came back. "
            "Want to try different wording?",
            "web-search",
        )

    if _app()._llm_available():
        try:
            source_blocks = []
            for source in sources:
                content = re.sub(r"\s+", " ", (source.get("content") or "")).strip()[:600]
                source_blocks.append(
                    f"[{source['id']}] {source['title']} ({source['domain']})\n"
                    f"URL: {source['url']}\n"
                    f"Content: {content}"
                )
            summary_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are S.P.I.D.E.Y. Summarize web search results clearly in simple, everyday English. "
                        "For each relevant result, give a short, plain-words summary (1-2 sentences) with the source name or link. "
                        "Ignore website navigation text or boilerplate. Do not invent facts outside the provided results."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Query: {query}\n\n"
                        "Search results:\n" + "\n\n".join(source_blocks) + "\n\n"
                        "Explain each item in simple words as a short, easy-to-read summary."
                    ),
                },
            ]
            gemini_key, gemini_model = _app().get_active_gemini_config()
            if gemini_key:
                resp = _app().gemini_chat_request(
                    summary_messages,
                    api_key=gemini_key,
                    model=gemini_model,
                    max_tokens=512,
                )
                summary = ((resp.get("message") or {}).get("content") or "").strip()
            else:
                summary = _app()._generate_ollama(summary_messages, 512).strip()
            if summary:
                return summary, "web-search"
        except Exception as err:
            logging.getLogger("orbit007").warning("Web search summarization failed, using raw list: %s", err)

    lines = [f"Here's what I found on **{query}**:", ""]
    for source in sources:
        snippet = _search_snippet(source.get("content", ""))
        lines.append(
            f"{source['id']}. [{source['title']}]({source['url']}) — {source['domain']}"
        )
        if snippet:
            lines.append(f"> {snippet}")
        lines.append("")
    lines.append("Want me to dig into one of these?")
    return "\n".join(lines).strip(), "web-search"


_TASK_DMY_DATE = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$")
_TASK_YMD_DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_TASK_DATE_HINT = re.compile(
    r"(?:\d{1,4}[-/]\d{1,2}[-/]\d{2,4}"
    r"|\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?"
    r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r"|next\s+\w+|this\s+\w+|in\s+\d+\s+(?:days?|weeks?|months?|hours?))\b)",
    re.IGNORECASE,
)
_TASK_DUE_CLAUSE = re.compile(
    r"^(?P<title>.+?)\s+(?:due\s+(?:on|by|date)?|by|before|until|deadline|on)\s+(?P<when>.+)$",
    re.IGNORECASE,
)
_TASK_TRAILING_DAY = re.compile(
    r"^(?P<title>.+?)\s+(?P<when>today|tomorrow|tonight)$",
    re.IGNORECASE,
)


def _parse_task_due_date(value: str) -> str | None:
    """Parse a task due date string into ISO format, honoring DD-MM-YYYY and YYYY-MM-DD."""
    raw = (value or "").strip(" .,;:!?\"'")
    if not raw:
        return None
    tz = _app().LOCAL_TIMEZONE

    ymd = _TASK_YMD_DATE.fullmatch(raw)
    if ymd:
        try:
            dt = datetime(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)), tzinfo=tz)
            return dt.isoformat()
        except ValueError:
            return None

    dmy = _TASK_DMY_DATE.fullmatch(raw)
    if dmy:
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        try:
            dt = datetime(year, month, day, tzinfo=tz)
            return dt.isoformat()
        except ValueError:
            # Fall back to MM-DD-YYYY if day > 12 wasn't valid as DMY (e.g. month > 12)
            try:
                dt = datetime(year, day, month, tzinfo=tz)
                return dt.isoformat()
            except ValueError:
                return None

    try:
        parsed = _app()._parse_reminder_time(raw)
    except (TypeError, ValueError):
        parsed = None
    return parsed.isoformat() if parsed is not None else None


def _extract_task_due_date(title: str) -> tuple[str, str | None]:
    """Split a trailing due-date clause (e.g. 'by 20-11-2026', 'due tomorrow') from a task title."""
    cleaned = title.strip()
    if not cleaned:
        return cleaned, None

    for pattern in (_TASK_DUE_CLAUSE, _TASK_TRAILING_DAY):
        m = pattern.fullmatch(cleaned)
        if not m:
            continue
        base_title = m.group("title").strip(" :-'\",")
        when_raw = m.group("when").strip(" .,;:!?\"'")
        if not base_title or not _TASK_DATE_HINT.search(when_raw):
            continue
        due_iso = _parse_task_due_date(when_raw)
        if due_iso:
            return base_title, due_iso

    return cleaned, None


def _parse_task_create(prompt: str) -> tuple[str, str] | None:
    normalized = _app()._normalize_command(prompt)
    match = re.fullmatch(
        r"(?:add|create|new)\s+(?:a\s+)?(?:new\s+)?(?:task|to[\s-]?do)"
        r"(?:\s+(?:to|for|in|about))*"
        r"(?:\s+(?:called|named))?"
        r"(?:\s*[:\-]\s*|\s+)(.+?)"
        r"(?:\s+(?:with\s+)?priority\s+(low|medium|high)"
        r"|\s+(?:with\s+)?(low|medium|high)\s+priority)?",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        # Shorthand prefix: "todo: buy milk" or "task: finish slides high priority"
        match = re.fullmatch(
            r"(?:task|to[\s-]?do)\s*[:\-]\s*(.+?)"
            r"(?:\s+(?:with\s+)?priority\s+(low|medium|high)"
            r"|\s+(?:with\s+)?(low|medium|high)\s+priority)?",
            normalized,
            re.IGNORECASE,
        )
    if not match:
        # Natural list phrasing: "add buy milk to my tasks" / "put finish report on my todo list"
        match = re.fullmatch(
            r"(?:add|put)\s+(.+?)\s+(?:to|on|into)\s+(?:my\s+|the\s+)?"
            r"(?:tasks?|task\s+list|to[\s-]?dos?|to[\s-]?do\s+list)"
            r"(?:\s+(?:with\s+)?priority\s+(low|medium|high)"
            r"|\s+(?:with\s+)?(low|medium|high)\s+priority)?",
            normalized,
            re.IGNORECASE,
        )
    if not match:
        return None
    title = match.group(1).strip(" :-'\"")
    if not title:
        return None
    priority = match.group(2) or match.group(3) or "medium"
    return title, priority.lower()


_TECH_TEXT_REPLACEMENTS = (
    (re.compile(r"\bc\s*\+\s*\+", re.IGNORECASE), "cpp"),
    (re.compile(r"\bc\s+plus\s+plus\b", re.IGNORECASE), "cpp"),
    (re.compile(r"\bc\s*#", re.IGNORECASE), "csharp"),
    (re.compile(r"\bc\s+sharp\b", re.IGNORECASE), "csharp"),
    (re.compile(r"\bnode\.?js\b", re.IGNORECASE), "nodejs"),
    (re.compile(r"\bnext\.?js\b", re.IGNORECASE), "nextjs"),
    (re.compile(r"\breact\.?js\b", re.IGNORECASE), "reactjs"),
    (re.compile(r"\boops\b", re.IGNORECASE), "oop"),
)

_DELETE_FILLER_TAIL = re.compile(
    r"(?:\s*[,;\-]\s*|\s+)(?:"
    r"(?:that|which)\s+i\s+(?:have\s+|'ve\s+)?(?:just\s+)?(?:added|created|made|put)\b.*"
    r"|i\s+(?:have\s+|'ve\s+)?(?:just\s+)?(?:added|created|made|put)\b.*"
    r"|because\b.*"
    r"|since\s+i\b.*"
    r"|for\s+testing\b.*"
    r"|for\s+me\b.*"
    r"|please\b.*"
    r")$",
    re.IGNORECASE,
)


def _normalize_tech_text(value: str) -> str:
    """Normalize programming symbols and spoken aliases (e.g. C++ / C plus plus -> cpp)."""
    text = str(value or "").strip().lower()
    for pattern, repl in _TECH_TEXT_REPLACEMENTS:
        text = pattern.sub(repl, text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_delete_filler(reference: str) -> str:
    """Strip leading articles and conversational explanation tails from a delete target."""
    cleaned = str(reference or "").strip(" \"'`?!.,;:")
    cleaned = _DELETE_FILLER_TAIL.sub("", cleaned).strip(" \"'`?!.,;:")
    cleaned = re.sub(r"^(?:the|my|that|this)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _fuzzy_best_match(
    query: str, items: list[dict[str, Any]], key: str, threshold: float = 0.76
) -> dict[str, Any] | None:
    """Return a single fuzzy match when the user has a minor typo (e.g. garder vs garden)."""
    if len(query) < 3 or not items:
        return None
    tech_query = _normalize_tech_text(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        candidate = re.sub(r"\s+", " ", str(item.get(key, "")).strip().lower())
        raw_ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
        tech_cand = _normalize_tech_text(candidate)
        tech_ratio = (
            difflib.SequenceMatcher(None, tech_query, tech_cand).ratio()
            if (tech_query and tech_cand)
            else 0.0
        )
        ratio = max(raw_ratio, tech_ratio)
        if ratio >= threshold:
            scored.append((ratio, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 0.05:
        return None
    return scored[0][1]


def _find_task_reference(
    reference: str, include_completed: bool = True
) -> dict[str, Any] | None:
    """Resolve '#12', '12', or a unique (partial, tech-normalized, or fuzzy) task title."""
    cleaned = _strip_delete_filler(reference).strip("#").strip()
    if not cleaned:
        return None
    tasks = _app().memory_store.list_tasks(include_completed=True)
    if not include_completed:
        tasks = [task for task in tasks if not task["completed"]]
    if cleaned.isdigit():
        task_id = int(cleaned)
        return next((task for task in tasks if task["id"] == task_id), None)

    normalized = re.sub(r"\s+", " ", cleaned.lower())
    tech_norm = _normalize_tech_text(normalized)

    exact_matches = [
        task for task in tasks
        if task["title"].strip().lower() == normalized
        or (tech_norm and _normalize_tech_text(task["title"]) == tech_norm)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    partial_matches = [
        task for task in tasks
        if normalized in task["title"].strip().lower()
        or (tech_norm and tech_norm in _normalize_tech_text(task["title"]))
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        raise ValueError(
            f"More than one task matches '{reference}'. Use 'task <number>'."
        )
    requested_words = set(tech_norm.split()) if tech_norm else set(re.findall(r"[a-z0-9]+", normalized))
    word_matches = [
        task for task in tasks
        if requested_words
        and requested_words.issubset(
            set(_normalize_tech_text(task["title"]).split())
        )
    ]
    if len(word_matches) == 1:
        return word_matches[0]
    if len(word_matches) > 1:
        raise ValueError(
            f"More than one task matches '{reference}'. Use 'task <number>'."
        )
    return _fuzzy_best_match(normalized, tasks, "title")


def _format_task_list(tasks: list[dict[str, Any]], completed: bool = False) -> str:
    if not tasks:
        if completed:
            return "You haven't completed any tasks yet."
        return "You're all caught up—there's nothing waiting on your task list."
    if completed:
        lines = "\n".join(f"- #{task['id']} **{task['title']}**" for task in tasks)
        return f"Here are your completed tasks:\n{lines}"
    if len(tasks) == 1:
        task = tasks[0]
        return (
            f"You still have **{task['title']}** (#{task['id']}, "
            f"{task['priority']} priority) on your list. Want to tackle that now?"
        )
    if len(tasks) == 2:
        first, second = tasks[0], tasks[1]
        return (
            f"You've got **{first['title']}** (#{first['id']}) and "
            f"**{second['title']}** (#{second['id']}) still to do. "
            "Which one do you want to tackle first?"
        )
    lines = "\n".join(
        f"- #{task['id']} **{task['title']}** ({task['priority']})"
        for task in tasks
    )
    return (
        f"You've got a few tasks waiting:\n{lines}\n"
        "Which one should we start with?"
    )


def _parse_task_update(prompt: str) -> tuple[str, str, str] | None:
    """Return (field, reference, value) for task priority, due date, or rename."""
    normalized = _app()._normalize_command(prompt)
    priority_match = re.fullmatch(
        r"(?:set|change|update|make)\s+(?:(?:the|my)\s+)?(?:priority\s+of\s+)?"
        r"(?:(?:the|my)\s+)?task\s+(.+?)\s+"
        r"(?:to\s+)?(?:be\s+)?(?:priority\s+)?(low|medium|high)(?:\s+priority)?",
        normalized,
        re.IGNORECASE,
    )
    if priority_match:
        return (
            "priority",
            priority_match.group(1).strip(),
            priority_match.group(2).lower(),
        )
    due_match = re.fullmatch(
        r"(?:set|change|reschedule|update)\s+(?:(?:the|my)\s+)?"
        r"(?:due\s+date\s+of\s+)?(?:(?:the|my)\s+)?task\s+"
        r"(.+?)\s+due(?:\s+date)?\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if due_match:
        return "due", due_match.group(1).strip(), due_match.group(2).strip()
    title_match = re.fullmatch(
        r"(?:rename|retitle|update)\s+(?:(?:the|my)\s+)?task\s+(.+?)\s+to\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if title_match:
        return "title", title_match.group(1).strip(), title_match.group(2).strip()
    return None


def _parse_task_delete(prompt: str) -> str | None:
    normalized = _app()._normalize_command(prompt)
    patterns = (
        r"(?:delete|remove|drop|cancel|forget)\s+(?:(?:the|my)\s+)?(?:task|to[\s-]?do)\s+(.+)",
        r"(?:delete|remove|drop|cancel|forget)\s+(?:(?:the|my)\s+)?(.+?)\s+"
        r"(?:(?:in|from|on)\s+(?:(?:the|my)\s+)?(?:tasks?|task\s+list|to[\s-]?dos?|to[\s-]?do\s+list)|task|to[\s-]?do)",
        r"(?:delete|remove|drop|cancel|forget)\s+#(\d+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized, re.IGNORECASE)
        if match:
            ref = _strip_delete_filler(match.group(1))
            if ref:
                return ref
    return None


def _parse_generic_delete(prompt: str) -> str | None:
    """Catch natural 'remove X' / 'delete the oops I just added for testing' without an entity word."""
    normalized = _app()._normalize_command(prompt)
    # Explicit entity-typed deletes are handled by their dedicated parsers.
    if re.search(r"\b(?:tasks?|to[\s-]?dos?|habits?|reminders?|alarms?|timers?|notes?|memor(?:y|ies)|roadmaps?|topics?)\b", normalized, re.IGNORECASE):
        return None
    match = re.fullmatch(
        r"(?:delete|remove|drop|cancel)\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    ref = _strip_delete_filler(match.group(1))
    if not ref or ref.lower() in {"it", "that", "this", "them", "all", "everything"}:
        return None
    return ref


def _has_negation_or_unmark(normalized: str) -> bool:
    """Return True if the normalized prompt is an unmark/undo/reopen command or negated completion."""
    if re.match(
        r"^(?:unmark|unmarked|uncheck|unchecked|uncomplete|uncompleted|untick|unticked|undo|undid|reset|reopen|reopened)\b",
        normalized,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\b(?:not\s+(?:yet\s+)?(?:completed|complete|done|finished|started|checked\s+off)|"
        r"(?:haven't|hasn't|didn't|don't|am\s+not|'m\s+not|aren't|isn't|wasn't|weren't)\s+(?:yet\s+)?(?:completed|complete|done|finished|did|checked\s+off)|"
        r"(?:as\s+)?(?:incomplete|unchecked|unmarked|not\s+done|not\s+completed|not\s+complete|open|pending)$)",
        normalized,
        re.IGNORECASE,
    ):
        # Allow positive commands like "complete the habits that are not completed" or "... as completed"
        if re.match(r"^(?:complete|finish|check\s+off|tick\s+off)\b", normalized, re.IGNORECASE):
            return False
        if re.search(r"\bas\s+(?:completed|complete|done|finished)$", normalized, re.IGNORECASE):
            return False
        return True
    return False


def _parse_task_reopen(prompt: str) -> str | None:
    """Match 'reopen task 3', 'unmark all tasks', 'mark task 3 as incomplete', or negated task completion."""
    normalized = _app()._normalize_command(prompt)
    if re.search(r"\b(?:habits?|topics?|roadmaps?|reminders?)\b", normalized, re.IGNORECASE):
        return None

    # 1. Batch reopen/unmark/uncheck/undo/reset all tasks
    if re.fullmatch(
        r"(?:(?:i\s+)?(?:have\s+|'ve\s+|am\s+)?(?:just\s+)?(?:unmarked|unmark|unchecked|uncheck|undid|undo|uncompleted|uncomplete|unticked|untick|reset|reopened|reopen))\s+"
        r"(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my|both)\s+)*(?:tasks?|to[\s\-]?dos?)"
        r"(?:\s+(?:for\s+today|today|(?:that\s+|which\s+)?(?:i\s+)?(?:am|have|haven't|are|were)?\s*(?:not\s+)?(?:completed|complete|done|finished)))?",
        normalized,
        re.IGNORECASE,
    ):
        return "all tasks"

    # 2. "mark [all/my] tasks [as] not completed / incomplete / open"
    if re.fullmatch(
        r"mark\s+(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my)\s+)*(?:tasks?|to[\s\-]?dos?)\s+(?:as\s+)?"
        r"(?:not\s+done|not\s+completed|not\s+complete|not\s+finished|incomplete|unchecked|unmarked|pending|open)",
        normalized,
        re.IGNORECASE,
    ):
        return "all tasks"

    # 3. Conversational negation: "i have not completed [all/my] tasks", "i am not completed tasks"
    if re.fullmatch(
        r"(?:i\s+)?(?:have\s+not|haven't|did\s+not|didn't|am\s+not|'m\s+not|not)\s+"
        r"(?:yet\s+)?(?:completed|complete|finished|finish|done|did|checked\s+off)\s+"
        r"(?:with\s+)?(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my)\s+)*(?:tasks?|to[\s\-]?dos?)(?:\s+today)?",
        normalized,
        re.IGNORECASE,
    ):
        return "all tasks"

    # 4. Specific task: "reopen/unmark/uncheck/undo/reset [my/the] task <name>"
    m = re.fullmatch(
        r"(?:reopen|uncomplete|unmark|uncheck|undo|untick|reset)\s+"
        r"(?:(?:the|my)\s+)?(?:tasks?|to[\s\-]?dos?)\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(
            r"(?:all|all\s+of\s+them|them|both|today|for\s+today|(?:i\s+)?(?:am|have)\s+not\s+(?:completed|done))",
            target,
            re.IGNORECASE,
        ):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 5. Specific task: "reopen/unmark/uncheck [my/the] <name> task"
    m = re.fullmatch(
        r"(?:reopen|uncomplete|unmark|uncheck|undo|untick|reset)\s+"
        r"(?:(?:the|my)\s+)?(.+?)\s+(?:tasks?|to[\s\-]?dos?)(?:\s+today)?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all\s+of\s+my|all|my|both)?", target, re.IGNORECASE):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 6. Specific task: "mark [my/the] task <name> [as] incomplete/not completed/open" or "mark <name> task ..."
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?(?:(?:tasks?|to[\s\-]?dos?)\s+(.+?)|(.+?)\s+(?:tasks?|to[\s\-]?dos?))\s+(?:as\s+)?"
        r"(?:incomplete|open|pending|unchecked|unmarked|not\s+completed|not\s+complete|not\s+done|not\s+finished)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = (m.group(1) or m.group(2)).strip()
        if re.fullmatch(r"(?:(?:my\s+all|all\s+my|all|my)\s+)*tasks?|my\s+all|all\s+my|all|my", target, re.IGNORECASE):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 7. Conversational specific task negation: "i didn't complete [my] [task] <name> [task]"
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+not|haven't|did\s+not|didn't|am\s+not|'m\s+not)\s+"
        r"(?:yet\s+)?(?:completed|complete|finished|finish|done|did|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?(?:task\s+(.+)|(.+?)\s+tasks?)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = (m.group(1) or m.group(2)).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    return None


_ADVICE_PATTERN = re.compile(
    r"\b(?:what\s+(?:new|else|other|should|can|could|would)|"
    r"should\s+i|how\s+(?:can|do|should|could|to)|"
    r"suggest\w*|recommend\w*|advice|tips?|ideas?|improv\w+|better|"
    r"think\s+about|opinion|why|help\s+me|ways?\s+to|"
    r"good\s+habits?|bad\s+habits?)\b",
    re.IGNORECASE,
)


def _is_advice_question(normalized_prompt: str) -> bool:
    """Open-ended questions belong to the LLM, not the list handlers."""
    return bool(_ADVICE_PATTERN.search(normalized_prompt))


def _is_task_list_request(prompt: str) -> bool:
    normalized_prompt = _app()._normalize_command(prompt).lower()
    # Habit, reminder, analytics, overview, and learning focus queries belong to their own handlers / LLM tools.
    if re.search(
        r"\b(?:habits?|reminders?|analytics?|telemetry|overview|roadmaps?|learning|study|focus\s+more|improve|average)\b",
        normalized_prompt,
    ):
        return False
    if _app()._is_advice_question(normalized_prompt):
        return False
    if re.match(
        r"^(?:add|create|new|complete|completed|finish|finished|mark|"
        r"unmark|unmarked|uncheck|unchecked|uncomplete|uncompleted|untick|unticked|undo|reset|"
        r"check off|tick off|delete|remove|rename|retitle|reopen|set|change|"
        r"update|make|cancel|done\s+with)\b",
        normalized_prompt,
    ):
        return False
    if _app()._parse_task_reopen(prompt) is not None or _app()._parse_task_completion(prompt) is not None:
        return False

    # Conversational or assertive completion expressions for tasks
    if (
        re.search(
            r"\b(?:i\s+(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|did|done|checked\s+off)|"
            r"mark\s+.*(?:completed|complete|done|finished))\b",
            normalized_prompt,
        )
        or re.match(
            r"^(?:just\s+)?(?:completed|finished)\s+(?:all\s+)?(?:my\s+)?(?:tasks?|to[\s-]?dos?)\b",
            normalized_prompt,
        )
        or re.match(
            r"^(?:all\s+)?(?:my\s+)?(?:tasks?|to[\s-]?dos?)\s+(?:are\s+)?(?:completed|complete|done|finished)$",
            normalized_prompt,
        )
    ):
        return False

    # Bare / short task queries: "tasks", "my tasks", "todos", "pending tasks", "tasks today"
    if re.fullmatch(
        r"(?:(?:my|the|all|today'?s|daily|current)\s+)*"
        r"(?:tasks?|to[\s-]?dos?|task\s+list|to[\s-]?do\s+list)"
        r"(?:\s+(?:today|for\s+today|status|list))?",
        normalized_prompt,
    ):
        return True

    task_reference = re.search(
        r"\b(?:tasks?|to[\s-]?dos?|things to do)\b",
        normalized_prompt,
    )
    if not task_reference:
        # Common shorthand such as “what's pending?” or “what are the
        # pending to do?” still means the user's open task list.
        return bool(
            re.search(r"\b(?:what|which|show|list|check|tell me|any)\b", normalized_prompt)
            and re.search(
                r"\b(?:pending|unfinished|remaining|left|to do|need to complete|need to do)\b",
                normalized_prompt,
            )
        )

    list_intent = re.search(
        r"\b(?:show|list|check|review|see|find|what|which|tell me|"
        r"do i have|are there|any)\b",
        normalized_prompt,
    )
    pending_intent = re.search(
        r"\b(?:pending|incomplete|unfinished|remaining|left|to do|"
        r"need to do|still need to do|need to complete|to complete|"
        r"need to finish|open)\b",
        normalized_prompt,
    )
    return bool(list_intent or pending_intent)


def _is_habit_list_request(prompt: str) -> bool:
    normalized_prompt = _app()._normalize_command(prompt).lower()

    if not re.search(r"\bhabits?\b", normalized_prompt):
        return False
    if _app()._is_advice_question(normalized_prompt):
        return False
    # Let explicit create/complete/uncomplete/update commands reach their own handlers.
    if re.match(
        r"^(?:add|create|new|start|track|complete|completed|finish|finished|done with|mark|"
        r"unmark|unmarked|uncheck|unchecked|uncomplete|uncompleted|untick|unticked|undo|reset|reopen|"
        r"check off|tick off|delete|remove|drop|rename|retitle|set|change|update)\b",
        normalized_prompt,
    ):
        return False
    if _app()._parse_habit_uncomplete(prompt) is not None or _app()._parse_habit_completion(prompt) is not None:
        return False

    # Conversational or assertive completion: "i have completed...", "i finished...", "all habits are done", "mark ... completed"
    if (
        re.search(
            r"\b(?:i\s+(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|did|done|checked\s+off)|"
            r"mark\s+.*(?:completed|complete|done|finished))\b",
            normalized_prompt,
        )
        or re.match(
            r"^(?:just\s+)?(?:completed|finished)\s+(?:all\s+)?(?:my\s+)?habits?\b",
            normalized_prompt,
        )
        or re.match(
            r"^(?:all\s+)?(?:my\s+)?habits?\s+(?:are\s+)?(?:completed|complete|done|finished)$",
            normalized_prompt,
        )
    ):
        return False

    # Bare / short habit queries: "habits", "my habits", "habits today", "daily habits", "habit status"
    if re.fullmatch(
        r"(?:(?:my|the|all|today'?s|daily|current)\s+)*"
        r"habits?(?:\s+(?:today|for\s+today|status|list|streaks?))?",
        normalized_prompt,
    ):
        return True

    list_intent = re.search(
        r"\b(?:check|show|list|review|see|tell me|find|what|which|"
        r"do i have|are there|any|status)\b",
        normalized_prompt,
    )
    incomplete_intent = re.search(
        r"\b(?:pending|incomplete|unfinished|remaining|left|not complete|"
        r"not completed|still not complete|still not completed|to complete|"
        r"to do|need to complete|need to finish)\b",
        normalized_prompt,
    )
    return bool(list_intent or incomplete_intent)


def _is_habit_follow_up(prompt: str, previous_messages: list[dict[str, str]]) -> bool:
    normalized_prompt = re.sub(r"\s+", " ", prompt.strip().lower()).rstrip(".!?")
    if normalized_prompt not in {
        "now", "what now", "now what", "and now", "okay now", "ok now",
        "then what", "what next", "what should i do now",
    }:
        return False
    previous_assistant_messages = [
        item["content"].lower()
        for item in previous_messages
        if item["role"] == "assistant"
    ]
    return any(
        "habit" in content
        and any(marker in content for marker in (
            "list", "all caught up", "all set for today", "haven't set up",
            "haven't added", "set up yet",
        ))
        for content in previous_assistant_messages[-2:]
    )


def _parse_chat_habit(prompt: str) -> tuple[str, str] | None:
    normalized_prompt = _app()._normalize_command(prompt)
    if _app()._is_advice_question(normalized_prompt.lower()):
        return None
    match = re.fullmatch(
        r"(?:add|create|start|track|set(?:\s+up)?|make|new)\s+"
        r"(?:(?:a|an)\s+)?(?:new\s+)?(?:daily\s+)?habits?\b"
        r"(?:\s+(?:for|to|called|named|of))?\s*[:\-]?\s*(.+)",
        normalized_prompt,
        re.IGNORECASE,
    )
    if not match:
        match = re.fullmatch(
            r"habit\s*[:\-]\s*(.+)"
            r"|(?:add|put)\s+(.+?)\s+(?:to|on|into)\s+(?:my\s+|the\s+)?(?:daily\s+)?habits?"
            r"|track\s+(.+?)\s+(?:every\s*day|daily)",
            normalized_prompt,
            re.IGNORECASE,
        )
        if match:
            raw = next((g for g in match.groups() if g), "")
            habit_name = raw.strip(" :-'\"")
            return (habit_name, "Activity") if habit_name else None
        return None
    habit_name = match.group(1).strip(" :-'\"")
    return (habit_name, "Activity") if habit_name else None


def _parse_habit_uncomplete(prompt: str) -> str | None:
    """Match 'uncheck habit X', 'unmark all habits', 'mark habit X as not done', or negated habit completion."""
    normalized = _app()._normalize_command(prompt)
    if re.search(r"\b(?:tasks?|to[\s\-]?dos?|topics?|roadmaps?|reminders?)\b", normalized, re.IGNORECASE):
        return None

    # 1. Batch unmark/uncheck/undo/reset all habits (including trailing qualifiers like "i am not completed", "for today")
    if re.fullmatch(
        r"(?:(?:i\s+)?(?:have\s+|'ve\s+|am\s+)?(?:just\s+)?(?:unmarked|unmark|unchecked|uncheck|undid|undo|uncompleted|uncomplete|unticked|untick|reset|reopened|reopen))\s+"
        r"(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my|both)\s+)*habits?"
        r"(?:\s+(?:for\s+today|today|(?:that\s+|which\s+)?(?:i\s+)?(?:am|have|haven't|are|were)?\s*(?:not\s+)?(?:completed|complete|done|finished)))?",
        normalized,
        re.IGNORECASE,
    ):
        return "all habits"

    # 2. "mark [all/my] habits [as] not completed / incomplete / unchecked"
    if re.fullmatch(
        r"mark\s+(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my)\s+)*habits?\s+(?:as\s+)?"
        r"(?:not\s+done|not\s+completed|not\s+complete|not\s+finished|incomplete|unchecked|unmarked|pending|open)",
        normalized,
        re.IGNORECASE,
    ):
        return "all habits"

    # 3. Conversational negation: "i have not completed [all/my] habits", "i am not completed habits"
    if re.fullmatch(
        r"(?:i\s+)?(?:have\s+not|haven't|did\s+not|didn't|am\s+not|'m\s+not|not)\s+"
        r"(?:yet\s+)?(?:completed|complete|finished|finish|done|did|checked\s+off)\s+"
        r"(?:with\s+)?(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my)\s+)*habits?(?:\s+today)?",
        normalized,
        re.IGNORECASE,
    ):
        return "all habits"

    # 4. Specific habit: "unmark/uncheck/undo/reset [my/the] habit <name>"
    m = re.fullmatch(
        r"(?:unmark|uncheck|undo|uncomplete|untick|reset|reopen)\s+"
        r"(?:(?:the|my)\s+)?habits?\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(
            r"(?:all|all\s+of\s+them|them|both|today|for\s+today|(?:i\s+)?(?:am|have)\s+not\s+(?:completed|done))",
            target,
            re.IGNORECASE,
        ):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 5. Specific habit: "unmark/uncheck [my/the] <name> habit"
    m = re.fullmatch(
        r"(?:unmark|uncheck|undo|uncomplete|untick|reset|reopen)\s+"
        r"(?:(?:the|my)\s+)?(.+?)\s+habits?(?:\s+today)?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all\s+of\s+my|all|my|both)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 6. Specific habit: "mark [my/the] [habit] <name> [habit] [as] not done/not completed/incomplete"
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?(?:habit\s+)?(.+?)(?:\s+habits?)?\s+(?:as\s+)?"
        r"(?:not\s+done|not\s+completed|not\s+complete|not\s+finished|incomplete|unchecked|unmarked|pending)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:(?:my\s+all|all\s+my|all|my)\s+)*habits?|my\s+all|all\s+my|all|my", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 7. Conversational specific habit negation: "i didn't complete [my] [habit] <name> [habit]"
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+not|haven't|did\s+not|didn't|am\s+not|'m\s+not)\s+"
        r"(?:yet\s+)?(?:completed|complete|finished|finish|done|did|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?(?:habit\s+(.+)|(.+?)\s+habits?)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = (m.group(1) or m.group(2)).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    return None


def _parse_habit_completion(prompt: str) -> str | None:
    """Match habit completion commands (batch, phrased with 'mark', or conversational)."""
    normalized = _app()._normalize_command(prompt)
    if _app()._has_negation_or_unmark(normalized):
        return None

    # 1. Direct batch completion: all habits (including "complete the habits that are not completed")
    if re.fullmatch(
        r"(?:(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|did|done|checked\s+off)|"
        r"mark|done\s+with)\s+(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my|remaining|pending|incomplete|open)\s+)*habits?"
        r"(?:\s+(?:that\s+|which\s+)?(?:i\s+)?(?:am|have|haven't|are|were)?\s*(?:not\s+)?(?:completed|complete|done|finished|pending|left|remaining))?"
        r"(?:\s+(?:as\s+)?(?:completed|complete|done|finished))?",
        normalized,
        re.IGNORECASE,
    ) or re.fullmatch(
        r"(?:(?:all\s+)?(?:my\s+)?habits?|my\s+all\s+habits?)\s+(?:are\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    ):
        return "all habits"

    # 2. 'mark [my/the] habit <name> [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?habit\s+(.+?)\s+(?:as\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 3. 'mark [my/the] <name> habit [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?(.+?)\s+habits?\s+(?:as\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 4. Conversational specific habit: 'i (have) completed [my] [habit] <name>'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?habit\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 5. Conversational specific habit: 'i (have) completed [my] <name> habit'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?(.+?)\s+habits?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 6. Standard 'complete habit <name>' or batch 'complete habits'
    m = re.fullmatch(
        r"(?:complete|completed|finish|finished|done\s+with|mark\s+done|check\s+off)\s+"
        r"(?:(?:the|my)\s+)?habits?(?:\s+(.+))?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1)
        if not target or target.strip().lower() in {"", "all", "all of them", "them", "both"}:
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target.strip(), flags=re.IGNORECASE)

    return None


def _parse_habit_rename(prompt: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"(?:rename|retitle|update)\s+(?:(?:the|my)\s+)?habit\s+(.+?)\s+to\s+(.+)",
        _app()._normalize_command(prompt),
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _parse_habit_delete(prompt: str) -> str | None:
    normalized = _app()._normalize_command(prompt)
    patterns = (
        r"(?:delete|remove|stop|drop)\s+(?:(?:the|my)\s+)?habit\s+(.+)",
        r"(?:delete|remove|stop|drop)\s+(?:(?:the|my)\s+)?(.+?)\s+"
        r"(?:(?:in|from|on)\s+(?:(?:the|my)\s+)?habits?|habit)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized, re.IGNORECASE)
        if match:
            ref = _strip_delete_filler(match.group(1))
            if ref:
                return ref
    return None


def _find_habit(habit_title: str) -> dict[str, Any] | None:
    normalized_title = re.sub(r"\s+", " ", _strip_delete_filler(habit_title).lower())
    if not normalized_title:
        return None
    tech_norm = _normalize_tech_text(normalized_title)
    habits = _app().memory_store.list_habits()
    exact_matches = [
        habit for habit in habits
        if habit["name"].strip().lower() == normalized_title
        or (tech_norm and _normalize_tech_text(habit["name"]) == tech_norm)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    matches = [
        habit for habit in habits
        if normalized_title in habit["name"].strip().lower()
        or habit["name"].strip().lower() in normalized_title
        or (tech_norm and tech_norm in _normalize_tech_text(habit["name"]))
    ]
    if len(matches) > 1:
        raise ValueError(
            f"More than one habit matches '{habit_title}'. Be more specific."
        )
    if len(matches) == 1:
        return matches[0]
    return _fuzzy_best_match(normalized_title, habits, "name")


def _parse_task_completion(prompt: str) -> str | None:
    """Match task completion commands (batch, phrased with 'mark', or conversational)."""
    normalized = _app()._normalize_command(prompt)
    if _app()._has_negation_or_unmark(normalized):
        return None

    # 1. Direct batch completion: all tasks
    if re.fullmatch(
        r"(?:(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|did|done|checked\s+off)|"
        r"mark|done\s+with)\s+(?:(?:the|my\s+all|all\s+my|all\s+of\s+my|all|my|remaining|pending|incomplete|open)\s+)*(?:tasks?|to[\s\-]?dos?)"
        r"(?:\s+(?:that\s+|which\s+)?(?:i\s+)?(?:am|have|haven't|are|were)?\s*(?:not\s+)?(?:completed|complete|done|finished|pending|left|remaining))?"
        r"(?:\s+(?:as\s+)?(?:completed|complete|done|finished))?",
        normalized,
        re.IGNORECASE,
    ) or re.fullmatch(
        r"(?:(?:all\s+)?(?:my\s+)?(?:tasks?|to[\s\-]?dos?)|my\s+all\s+(?:tasks?|to[\s\-]?dos?))\s+(?:are\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    ):
        return "all tasks"

    # 2. 'mark [my/the] task <name> [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?task\s+(.+?)\s+(?:as\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 3. 'mark [my/the] <name> task [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?(.+?)\s+tasks?\s+(?:as\s+)?(?:completed|complete|done|finished)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 4. Conversational specific task: 'i (have) completed [my] [task] <name>'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?task\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 5. Conversational specific task: 'i (have) completed [my] <name> task'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?(.+?)\s+tasks?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 6. Standard 'complete task <name>' or batch 'complete tasks'
    m = re.fullmatch(
        r"(?:complete|completed|finish|finished|done\s+with|mark\s+done|check\s+off)\s+"
        r"(?:(?:the|my)\s+)?tasks?(?:\s+(.+))?",
        normalized,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1)
        if not target or target.strip().lower() in {"", "all", "all of them", "them", "both"}:
            return "all tasks"
        return re.sub(r"^(?:my|the)\s+", "", target.strip(), flags=re.IGNORECASE)

    return None


_COMPLETION_VERB_PATTERN = (
    r"(?:complete|completed|finish|finished|mark\s+done|mark\s+completed|"
    r"check\s+off|tick\s+off|done\s+with)"
)

_ACTION_WITHOUT_HANDLER = re.compile(
    r"^(?:add|create|new|set|make|mark|complete|finish|delete|remove|"
    r"rename|reschedule|cancel)\b.*\b(?:tasks?|habits?|reminders?)\b",
    re.IGNORECASE,
)


def _parse_completion_target(prompt: str) -> str | None:
    """Catch generic 'complete X' or 'now I am completed X' phrasing without an entity keyword."""
    normalized = _app()._normalize_command(prompt)
    if _app()._has_negation_or_unmark(normalized):
        return None
    patterns = (
        rf"{_COMPLETION_VERB_PATTERN}\s+(.+)",
        r"mark\s+(?:the\s+|my\s+)?(.+?)\s+(?:tasks?\s+|habits?\s+)?(?:as\s+)?"
        r"(?:being\s+)?(?:completed|complete|done|finished)",
        r"(?:i\s+)?(?:am|'m|was|have|'ve|had|'d)?\s*"
        r"(?:just\s+|already\s+|finally\s+|now\s+)*"
        r"(?:completed|complete|finished|finish|done(?:\s+with)?|checked\s+off)\s+"
        r"(?:with\s+|doing\s+)?(.+)",
        r"(.+?)\s+(?:task|habit)\s+(?:is\s+)?(?:completed|complete|finished|finish|done)"
        r"(?:\s+(?:and\s+)?mark\s+it(?:\s+as)?(?:\s+completed|\s+done)?)?",
        r"(.+?)\s+is\s+(?:now\s+)?(?:completed|complete|finished|done)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        target = match.group(1).strip()
        target = re.sub(
            r"^(?:(?:the|my)\s+)?(?:task|habit)\s+",
            "",
            target,
            flags=re.IGNORECASE,
        )
        target = re.sub(
            r"^(?:the|my)\s+", "", target, flags=re.IGNORECASE
        )
        target = re.sub(
            r"\s+(?:today|right\s+now|now|already)$", "", target, flags=re.IGNORECASE
        ).strip()
        target = re.sub(r"\s+mark\s+it.*$", "", target, flags=re.IGNORECASE).strip()
        if target:
            return target

    did_match = re.fullmatch(r"(?:i\s+)?did\s+(.+)", normalized, re.IGNORECASE)
    if did_match:
        words = re.findall(r"[a-z0-9]+", did_match.group(1).lower())
        deduplicated = [
            word for index, word in enumerate(words)
            if index == 0 or word != words[index - 1]
        ]
        return " ".join(deduplicated) or None
    return None



def _format_habit_list(
    all_habits: list[dict[str, Any]], pending_habits: list[dict[str, Any]]
) -> str:
    if not all_habits:
        return "I don't see any habits set up yet. What would you like to start with?"
    if not pending_habits:
        return "You're all caught up on habits for today. What else is on your mind?"
    names = [habit["name"] for habit in pending_habits]
    if len(names) == 1:
        return (
            f"You've still got **{names[0]}** on your habit list today. "
            "Want to start with that?"
        )
    if len(names) == 2:
        return (
            f"You've still got **{names[0]}** and **{names[1]}** on your habit "
            "list today. Which one feels easier to start with?"
        )
    formatted_names = "\n".join(f"- **{name}**" for name in names)
    return (
        f"You've still got a few habits on your list today:\n{formatted_names}\n"
        "Which one do you feel like starting with?"
    )



def _task_completion_line(task: dict[str, Any], name: str = "") -> str:
    """Encouraging reply that names the next task, if one is waiting."""
    # list_tasks already orders by priority, so the first row is the best next pick.
    remaining = _app().memory_store.list_tasks(include_completed=False)
    next_task = remaining[0] if remaining else None
    return _app().assistant_tone.task_completed(
        task["title"],
        len(remaining),
        next_title=next_task["title"] if next_task else "",
        next_priority=next_task["priority"] if next_task else "",
        name=name,
    )


def _habit_completion_line(habit: dict[str, Any], name: str = "") -> str:
    """Encouraging reply that names the habits still open today."""
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    pending = [
        item["name"]
        for item in _app().memory_store.list_habits()
        if item["id"] != habit["id"] and today not in item["completed_dates"]
    ]
    return _app().assistant_tone.habit_completed(
        habit["name"], habit["streak"], pending=pending, person=name
    )


def _complete_task(task: dict[str, Any], name: str = "") -> str:
    if task["completed"]:
        return (
            f"**{task['title']}** is already done — say "
            f"'reopen task {task['title']}' if you want it back on the list."
        )
    updated = _app().memory_store.update_task(task["id"], completed=True)
    if updated is None:
        raise ValueError(f"Task {task['id']} was not found.")
    _app()._run_learning_hook(lambda: _app()._learning_on_task_completed(task["id"]))
    reply = _app()._task_completion_line(updated, name=name)
    if _app().learning_schema.is_initialized():
        try:
            with _app().learning_schema.connect() as connection:
                row = connection.execute(
                    "SELECT t.id, t.name FROM task_topic_links AS link "
                    "JOIN topics AS t ON t.id = link.topic_id "
                    "WHERE link.task_id = ? AND link.state = 'confirmed' "
                    "LIMIT 1",
                    (task["id"],),
                ).fetchone()
            if row:
                topic_id = row["id"]
                topic_name = row["name"]
                links = _app().learning_progress.list_confirmed_task_links(topic_id)
                total = len(links)
                completed = sum(1 for link in links if link.get("task_completed"))
                reply = f"{reply.rstrip()}\nThat counts toward {topic_name}, now {completed}/{total}."
        except Exception:
            _app().LOGGER.debug("Suppressed error (app.py site 3)", exc_info=True)

    return reply


def _complete_habit(habit: dict[str, Any], name: str = "") -> str:
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    if today in habit["completed_dates"]:
        return f"**{habit['name']}** is already ticked off today — I won't count it twice."
    updated = _app().memory_store.set_habit_completion(habit["id"], today, True)
    return _app()._habit_completion_line(updated, name=name)


def _uncomplete_habit(habit: dict[str, Any], name: str = "") -> str:
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    if today not in habit["completed_dates"]:
        return f"**{habit['name']}** wasn't checked off today."
    updated = _app().memory_store.set_habit_completion(habit["id"], today, False)
    return f"Unchecked **{updated['name']}** for today (streak: {updated['streak']})."


def _uncomplete_all_habits() -> tuple[str, str]:
    all_habits = _app().memory_store.list_habits()
    if not all_habits:
        return ("You don't have any habits set up yet.", "local-habit-manager")
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    completed_habits = [h for h in all_habits if today in h["completed_dates"]]
    if not completed_habits:
        return (
            "None of your habits are checked off for today — they're all already unmarked.",
            "local-habit-manager",
        )
    names = [h["name"] for h in completed_habits]
    for h in completed_habits:
        _app().memory_store.set_habit_completion(h["id"], today, False)
    if len(names) == len(all_habits):
        return (
            f"Unchecked all {len(names)} habits for today: "
            + ", ".join(f"**{n}**" for n in names) + ".",
            "local-habit-manager",
        )
    return (
        f"Unchecked {len(names)} habit{'s' if len(names) != 1 else ''} for today: "
        + ", ".join(f"**{n}**" for n in names)
        + f" (all {len(all_habits)} habits are now unmarked).",
        "local-habit-manager",
    )


def _reopen_all_tasks() -> tuple[str, str]:
    all_tasks = _app().memory_store.list_tasks(include_completed=True)
    if not all_tasks:
        return ("You don't have any tasks set up yet.", "local-task-manager")
    completed_tasks = [t for t in all_tasks if t["completed"]]
    if not completed_tasks:
        return (
            "None of your tasks are marked completed — they're all already open.",
            "local-task-manager",
        )
    titles = [t["title"] for t in completed_tasks]
    for t in completed_tasks:
        _app().memory_store.update_task(t["id"], completed=False)
    if len(titles) == len(all_tasks):
        return (
            f"Reopened all {len(titles)} tasks: "
            + ", ".join(f"**{title}**" for title in titles) + ".",
            "local-task-manager",
        )
    return (
        f"Reopened {len(titles)} completed task{'s' if len(titles) != 1 else ''}: "
        + ", ".join(f"**{title}**" for title in titles)
        + f" (all {len(all_tasks)} tasks are now open).",
        "local-task-manager",
    )


