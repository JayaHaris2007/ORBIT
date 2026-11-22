"""Deterministic learning roadmap/topic command handlers."""

from __future__ import annotations

import re
from typing import Any

from learning import code_rag as learning_code_rag, progress as learning_progress, schema as learning_schema


def _app():
    import app

    return app


_LEARNING_PROGRESS_PATTERN = re.compile(
    r"^(?:(?:show|check|view|tell|give)\s+(?:me\s+)?)?(?:my\s+)?learning\s+"
    r"(?:progress|status|stats|statistics|summary|overview)$"
    r"|^learning\s+(?:progress|status|stats|summary)$"
    r"|^how(?:'s| is)\s+my\s+learning\s+(?:going|progress|doing)$",
    re.IGNORECASE,
)

_LEARNING_NEXT_PATTERN = re.compile(
    r"^what(?:\s+should|\s+can|\s+do|\s+could|\s+shall)?\s+i\s+(?:learn|study|tackle|practice|master)\s+next$"
    r"|^what(?:'s| is)\s+next\s+(?:to\s+|in\s+my\s+)?(?:learn|learning|study|studying)$"
    r"|^(?:what(?:'s| is)\s+)?(?:my\s+|the\s+)?next\s+(?:learning\s+)?(?:topic|lesson|module|subject)s?(?:\s+to\s+(?:learn|study))?$"
    r"|^(?:suggest|recommend)(?:\s+me)?\s+(?:a\s+|some\s+)?(?:learning\s+)?(?:topics?|something\s+to\s+(?:learn|study))(?:\s+next)?$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_PROGRESS_PATTERN = re.compile(
    r"^(?:check|show|view)\s+(?:me\s+)?(?:my\s+)?(?:the\s+)?"
    r"(?:(?:status|progress)\s+(?:of|for|in)\s+(.+)"
    r"|(.+?)\s+(?:roadmap\s+)?(?:status|progress))$"
    r"|^what(?:'s| is)\s+(?:my\s+)?(?:the\s+)?"
    r"(?:status|progress)\s+(?:of|for|in)\s+(.+)$"
    r"|^how(?:'s| is)\s+(?:my\s+)?(.+?)\s+(?:going|progress)$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_TOPICS_PATTERN = re.compile(
    r"^(?:(?:show|list|view|check|what(?:'s| is| are))\s+(?:me\s+)?)?"
    r"(?:(?:all|the|my)\s+)*topics?\s+(?:in|for|under|from|of|inside)\s+(.+)$"
    r"|^(?:show|list|view|inspect)\s+(?:me\s+)?(?:the\s+|my\s+)?(.+?)\s+(?:roadmap\s+)?topics$"
    r"|^what(?:'s| is)\s+(?:inside|in)\s+(?:the\s+|my\s+)?(.+?)\s+roadmap$",
    re.IGNORECASE,
)

_LEARNING_STATUS_LIST_PATTERN = re.compile(
    r"^what\s+(?:topics?\s+)?am\s+i\s+(?:currently\s+)?(?:learning|studying)(?:\s+right\s+now|\s+now)?$"
    r"|^(?:(?:show|list|view|check|what\s+are)\s+(?:me\s+)?)?(?:(?:my|the|all)\s+)*"
    r"(?P<filter>in[\s\-]progress|active|current|currently\s+learning|completed|finished|learned|mastered|on[\s\-]hold|paused|not\s+started|unlocked)\s+"
    r"(?:learning\s+)?topics?$"
    r"|^(?:(?:show|list|view|check|what\s+are)\s+(?:me\s+)?)?(?:(?:my|the|all)\s+)*"
    r"(?:learning\s+)?topics?\s+(?:that\s+are\s+|which\s+are\s+|i\s+have\s+|i've\s+)?"
    r"(?P<filter2>in\s+progress|currently\s+learning|completed|finished|learned|mastered|on\s+hold|paused|not\s+started)$"
    r"|^what\s+(?:topics?\s+)?have\s+i\s+(?P<filter3>learned|completed|mastered|finished)(?:\s+so\s+far)?$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_NEXT_PATTERN = re.compile(
    r"^(?:check\s+)?what\s+"
    r"(?:(?:to\s+)?should\s+i|i\s+should|can\s+i|to)\s+"
    r"(?:learn|study)(?:\s+next)?\s+(?:from|in|on|for)\s+(.+)$"
    r"|^what(?:'s| is)\s+next\s+(?:in|for|on)\s+(.+)$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_TASK_PATTERN = re.compile(
    r"^(?:suggest|recommend)(?:\s+me)?\s+(?:a\s+)?"
    r"(?:task|topic|something)\s+"
    r"(?:(?:to\s+)?(?:learn|study)(?:\s+next)?\s+(?:from|in|on)\s+(.+)"
    r"|(?:for|about)\s+(.+))$",
    re.IGNORECASE,
)

_LEARNING_START_PATTERN = re.compile(
    r"^(?:start|begin|resume|continue)\s+(?:learning|studying|working\s+on|with\s+topic|topic)\s+(.+)$"
    r"|^(?:start|begin|resume|continue)\s+(it|that|this|that\s+topic|this\s+topic|(?:the\s+)?(?:first|second|third|1st|2nd|3rd)(?:\s+one|\s+topic)?)$"
    r"|^i(?:'ve| have|'m| am)?\s+(?:just\s+|now\s+)?(?:started|begun|learning|studying|working\s+on)\s+(?:learning\s+|studying\s+|the\s+topic\s+|topic\s+)?(.+)$"
    r"|^mark\s+(.+?)\s+as\s+(?:learning|in\s+progress|studying|started)$",
    re.IGNORECASE,
)

_LEARNING_COMPLETE_PATTERN = re.compile(
    r"^(?:complete|finish|master)\s+(?:the\s+)?(?:topic|learning\s+topic|lesson|module)\s+(.+)$"
    r"|^mark\s+(?:(?:the\s+)?(?:topic|learning\s+topic)\s+)?(.+?)\s+(?:as\s+)?(?:learned|mastered|completed|done|finished)$",
    re.IGNORECASE,
)

_LEARNING_FINISHED_PATTERN = re.compile(
    r"^(?:now\s+)?i(?:'ve|'d| have| had| was| am|'m)?\s+"
    r"(?:just\s+|already\s+|finally\s+|now\s+)?"
    r"(?:comp\w*|finis\w*ed|finis\w*ht|finish|learn(?:ed|t)|master\w*|done\s+with)\s+"
    r"(?:learning\s+|studying\s+|the\s+topic\s+|topic\s+|with\s+)?(.+)$",
    re.IGNORECASE,
)

_LEARNING_HOLD_PATTERN = re.compile(
    r"^(?:put|place|set|move)\s+(?:(?:the\s+)?(?:topic|learning\s+topic)\s+)?(.+?)\s+(?:on\s+hold|to\s+on\s+hold|as\s+on\s+hold)$"
    r"|^(?:pause|postpone|hold|defer)\s+(?:learning\s+|studying\s+|(?:the\s+)?topic\s+)?(.+)$",
    re.IGNORECASE,
)

_LEARNING_REOPEN_PATTERN = re.compile(
    r"^(?:reopen|re-open|reset|redo|uncomplete|unmark|uncheck|undo|restart)\s+(?:learning\s+|studying\s+|(?:the\s+)?(?:learning\s+)?topic\s+)(.+)$"
    r"|^mark\s+(?:(?:the\s+)?(?:learning\s+)?topic\s+)?(.+?)\s+(?:as\s+)?(?:not\s+started|not\s+completed|not\s+done|unlearned|incomplete|unmarked|unchecked)$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_CREATE_PATTERN = re.compile(
    r"^(?:create|add|start|make)\s+(?:a\s+)?(?:new\s+)?"
    r"(?:(?P<cat>academic|technical|personal)\s+)?(?:learning\s+)?roadmap\s+"
    r"(?:called\s+|named\s+|for\s+|on\s+)?(?P<name>.+?)"
    r"(?:\s+in\s+(?P<cat2>academic|technical|personal)(?:\s+category)?)?$",
    re.IGNORECASE,
)

_LEARNING_PATH_AUTO_CREATE_PATTERN = re.compile(
    r"^(?:create|add|start|make|build|generate)\s+(?:a\s+)?(?:new\s+)?"
    r"(?:(?P<cat>academic|technical|personal)\s+)?"
    r"(?:"
    r"learning\s+path\s+(?:called\s+|named\s+|for\s+|on\s+)?(?P<name1>.+?)"
    r"|learning\s+(?:for\s+|on\s+|called\s+|named\s+)?(?P<name2>[A-Za-z0-9+#.\-/&\s]{1,50}?)"
    r"|(?:learning\s+)?roadmap\s+(?:called\s+|named\s+|for\s+|on\s+)?(?P<name3>.+?)\s+(?:and\s+)?(?:with\s+|divide(?:\s+into)?\s+|auto[\s\-]?generate\s+)sub[\s\-]?topics?"
    r")"
    r"(?:\s+(?:and\s+)?(?:with\s+|divide(?:\s+into)?\s+|auto[\s\-]?generate\s+)?sub[\s\-]?topics?)?"
    r"(?:\s*[:\-]\s*(?P<inline_topics>.+))?$",
    re.IGNORECASE,
)

_LEARNING_BULK_TOPICS_ADD_PATTERN = re.compile(
    r"^(?:add|create|insert)\s+(?:a\s+)?(?:new\s+)?(?:learning\s+)?(?:sub[\s\-]?)?topics?\s+"
    r"(?:called\s+|named\s+)?(?P<topics>.+?)\s+(?:to|in|under|into|for)\s+"
    r"(?:the\s+|my\s+)?(?P<roadmap>.+?)(?:\s+(?:roadmap|learning\s+path))?$",
    re.IGNORECASE,
)

_LEARNING_ROADMAP_DELETE_PATTERN = re.compile(
    r"^(?:delete|remove|drop)\s+(?:the\s+|my\s+)?(?:learning\s+)?roadmap\s+(?:called\s+|named\s+)?(.+)$"
    r"|^(?:delete|remove|drop)\s+(?:the\s+|my\s+)?(.+?)\s+(?:learning\s+)?roadmap$",
    re.IGNORECASE,
)

_LEARNING_TOPIC_CREATE_PATTERN = re.compile(
    r"^(?:add|create)\s+(?:a\s+)?(?:new\s+)?(?:learning\s+)?topic\s+"
    r"(?:called\s+|named\s+)?(?P<topic>.+?)\s+(?:to|in|under|into|for)\s+"
    r"(?:the\s+|my\s+)?(?P<roadmap>.+?)(?:\s+roadmap)?$",
    re.IGNORECASE,
)

_LEARNING_TOPIC_DELETE_PATTERN = re.compile(
    r"^(?:delete|remove|drop)\s+(?:the\s+|my\s+)?(?:learning\s+)?topic\s+(?:called\s+|named\s+)?(.+)$"
    r"|^(?:delete|remove|drop)\s+(?:the\s+|my\s+)?(.+?)\s+(?:(?:learning\s+)?topic|(?:in|from)\s+(?:the\s+|my\s+)?(?:learning|roadmap|topics?))$",
    re.IGNORECASE,
)

_LEARNING_TOPIC_PRIORITY_PATTERN = re.compile(
    r"^(?:set|change|update|make)\s+(?:the\s+)?(?:priority\s+of\s+)?(?:learning\s+)?topic\s+(.+?)\s+"
    r"(?:priority\s+)?(?:to\s+|as\s+)?(high|medium|low|1|2|3)(?:\s+priority)?$",
    re.IGNORECASE,
)

_LEARNING_LINKS_LIST_PATTERN = re.compile(
    r"^(?:(?:show|list|view|check|what\s+are)\s+(?:me\s+)?)?"
    r"(?:(?:my|the|all|pending|suggested)\s+)*"
    r"(?:suggested\s+learning\s+links?|learning\s+links?|task[\s\-]topic\s+links?|topic\s+links?)$",
    re.IGNORECASE,
)

_LEARNING_LINK_ACTION_PATTERN = re.compile(
    r"^(?P<action>confirm|accept|approve|reject|dismiss|decline)\s+"
    r"(?:(?P<all>all)\s+)?(?:(?:the|my|suggested)\s+)*(?:learning\s+|task[\s\-]topic\s+)?links?"
    r"(?:\s+(?:for\s+|#)(?P<target>.+))?$",
    re.IGNORECASE,
)

_LEARNING_ACTIVITY_PATTERN = re.compile(
    r"^(?:(?:show|list|view|check|what\s+is)\s+(?:me\s+)?)?"
    r"(?:(?:my|the|recent|latest)\s+)*"
    r"(?:learning\s+activity|learning\s+activities|learning\s+history|learning\s+log|study\s+history|study\s+log)$",
    re.IGNORECASE,
)

_LEARNING_NUDGES_PATTERN = re.compile(
    r"^(?:(?P<enable>enable|turn\s+on|activate|unmute|resume)"
    r"|(?P<disable>disable|turn\s+off|deactivate|mute|pause))"
    r"\s+(?:my\s+|the\s+)?learning\s+(?:nudges?|reminders?|notifications?)$"
    r"|^(?:learning\s+nudges?\s+(?P<state>on|off|status))$",
    re.IGNORECASE,
)

_LEARNING_BARE_PATTERN = re.compile(
    r"^(?:(?:show|check|view|list|what(?:'s| is| are))\s+(?:me\s+)?)?"
    r"(?:(?:my|the|all|current)\s+)*"
    r"(?:learning|learning\s+roadmaps?|roadmaps?|learning\s+tracker|study\s+plan|learning\s+goals?)$",
    re.IGNORECASE,
)

_LEARNING_LINK_FOLDER_RAW_PATTERN = re.compile(
    r"^(?:link|connect|attach|track|watch|bind)\s+(?:(?:my|the)\s+)?(?:learning\s+|code\s+|coding\s+)?folder\s+"
    r"(?P<path>(?:[A-Za-z]:\\[^\n]+?|/[^\n]+?|\"[^\"]+\"|'[^']+'))\s+"
    r"(?:to|for|with|on)\s+(?:(?:my|the)\s+)?(?P<roadmap>.+?)(?:\s+roadmap)?[.!?]*$",
    re.IGNORECASE,
)

_LEARNING_SYNC_FOLDER_PATTERN = re.compile(
    r"^(?:sync|scan|analyze|analyse|check|refresh|track|inspect)\s+"
    r"(?:(?:my|the|all)\s+)?(?:(?P<roadmap>.+?)\s+)?(?:learning|coding|code|practice)\s+folders?$"
    r"|^(?:sync|scan|analyze|analyse|check)\s+(?:my|the)\s+folder\s+(?:for|of)\s+(?P<roadmap2>.+)$"
    r"|^what\s+have\s+i\s+coded(?:\s+(?:so\s+far|in\s+(?P<roadmap3>.+)))?$",
    re.IGNORECASE,
)

_LEARNING_CODE_SUGGESTION_ACTION_PATTERN = re.compile(
    r"^(?P<action>confirm|accept|approve|dismiss|reject|ignore)\s+"
    r"(?:(?P<all>all)\s+)?(?:(?:the|my|pending)\s+)?code\s+(?:completion\s+)?suggestions?"
    r"(?:\s+(?:for\s+|#)(?P<target>.+))?$",
    re.IGNORECASE,
)

_LEARNING_PRONOUNS = {
    "it", "that", "this", "this one", "that one", "the one",
    "the topic", "that topic", "this topic", "the lesson", "that lesson",
    "the roadmap", "that roadmap", "this roadmap",
    "first", "the first", "first one", "the first one", "first topic", "the first topic", "1st", "the 1st",
    "second", "the second", "second one", "the second one", "second topic", "the second topic", "2nd", "the 2nd",
    "third", "the third", "third one", "the third one", "third topic", "the third topic", "3rd", "the 3rd",
    "both", "both of them", "them", "all", "all of them",
}


def _clean_topic_reference(reference: str) -> str:
    """Drop a trailing 'mark it done/complete…' clause from a spoken topic.

    Users often tack an instruction onto the confession, e.g. "i had completed
    HTML Fundamentals mark it done". The topic name is everything before that.
    """
    cleaned = re.sub(
        r"\s+(?:and\s+)?mark\s+\S.*$", "", reference, flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(
        r"\s+(?:in|from|under)\s+(?:my\s+|the\s+)?learning(?:\s+tracker|\s+roadmap)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned.strip("\"'`?!.,;:")


def _extract_learning_context(
    chat_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Return (mentioned_topics, mentioned_roadmaps, is_most_recent_learning) from recent assistant turns."""
    if not chat_id or not learning_schema.is_initialized():
        return [], [], False
    messages = _app().memory_store.get_messages(chat_id)
    assistant_msgs = [
        m["content"] for m in reversed(messages) if m.get("role") == "assistant"
    ][:3]
    if not assistant_msgs:
        return [], [], False

    all_topics = learning_progress.list_topics()
    all_roadmaps = learning_progress.roadmap_summaries()

    def _scan_msg(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        lower_text = text.lower()
        found_topics: list[tuple[int, dict[str, Any]]] = []
        for topic in all_topics:
            t_name = topic["name"].strip().lower()
            pos = lower_text.find(t_name)
            if pos != -1:
                found_topics.append((pos, topic))
        found_topics.sort(key=lambda pair: pair[0])

        found_roadmaps: list[tuple[int, dict[str, Any]]] = []
        for rm in all_roadmaps:
            r_name = rm["name"].strip().lower()
            pos = lower_text.find(r_name)
            if pos != -1:
                found_roadmaps.append((pos, rm))
        found_roadmaps.sort(key=lambda pair: pair[0])
        return [t for _, t in found_topics], [r for _, r in found_roadmaps]

    most_recent_lower = assistant_msgs[0].lower()
    most_recent_topics, most_recent_roadmaps = _scan_msg(assistant_msgs[0])
    has_learning_cue = any(
        cue in most_recent_lower
        for cue in (
            "ready to learn",
            "roadmap",
            "next-topic",
            "in progress",
            "what should i learn next",
            "start learning",
            "reopen learning",
            "prerequisites",
            "unlocked",
            "learning link",
            "learning tracker",
        )
    )
    is_most_recent_learning = bool(
        has_learning_cue or most_recent_topics or most_recent_roadmaps
    ) and not bool(re.search(r"#\d+\b", assistant_msgs[0]))

    for content in assistant_msgs:
        topics, roadmaps = _scan_msg(content)
        if topics or roadmaps:
            return topics, roadmaps, is_most_recent_learning

    return [], [], False


def _resolve_topic_from_context_or_ref(
    reference: str, chat_id: str
) -> list[dict[str, Any]]:
    """Return 1+ matching topics either from pronoun/ordinal context or by name/fuzzy lookup."""
    cleaned = _clean_topic_reference(reference)
    lowered = re.sub(r"\s+", " ", cleaned.lower()).strip()
    if lowered in _LEARNING_PRONOUNS and chat_id:
        ctx_topics, ctx_roadmaps, _ = _extract_learning_context(chat_id)
        if not ctx_topics and ctx_roadmaps:
            next_in_rm = learning_progress.next_topics(
                limit=3, roadmap_id=ctx_roadmaps[0]["id"]
            )
            if next_in_rm:
                found = learning_progress.find_topic(next_in_rm[0]["name"])
                if found:
                    ctx_topics = [found]
        if ctx_topics:
            if lowered in {"both", "both of them", "them", "all", "all of them"}:
                return ctx_topics
            ordinal = (
                1
                if ("second" in lowered or "2nd" in lowered)
                else (2 if ("third" in lowered or "3rd" in lowered) else 0)
            )
            chosen = ctx_topics[ordinal] if ordinal < len(ctx_topics) else ctx_topics[0]
            fresh = learning_progress.find_topic(chosen["name"])
            return [fresh or chosen]
    topic = learning_progress.find_topic(cleaned)
    return [topic] if topic is not None else []


def _resolve_roadmap_from_context_or_ref(
    reference: str, chat_id: str
) -> dict[str, Any] | None:
    cleaned = reference.strip().strip("\"'`?!.,;:")
    lowered = re.sub(r"\s+", " ", cleaned.lower()).strip()
    if lowered in _LEARNING_PRONOUNS and chat_id:
        _, ctx_roadmaps, _ = _extract_learning_context(chat_id)
        if ctx_roadmaps:
            ordinal = (
                1
                if ("second" in lowered or "2nd" in lowered)
                else (2 if ("third" in lowered or "3rd" in lowered) else 0)
            )
            chosen = ctx_roadmaps[ordinal] if ordinal < len(ctx_roadmaps) else ctx_roadmaps[0]
            return learning_progress.find_roadmap(chosen["name"]) or chosen
    return learning_progress.find_roadmap(cleaned)


def _learning_progress_reply() -> tuple[str, str]:
    summary = learning_progress.overall_progress()
    if summary["topic_count"] == 0:
        return (
            "Your learning tracker is empty. Open the Learning page to add a "
            "roadmap, then I can coach you through it.",
            "local-learning",
        )
    lines = [
        f"- **{item['roadmap_name']}**: {item['completed']}/{item['total']} "
        f"({item['percent']}%)"
        for item in summary["per_roadmap"]
    ]
    return (
        f"You've completed **{summary['completed_topics']} of "
        f"{summary['topic_count']}** topics "
        f"({summary['completion_percent']}%) across "
        f"{summary['roadmap_count']} roadmaps.\n"
        + "\n".join(lines)
        + "\n\nSay 'what should I learn next' for a suggestion.",
        "local-learning",
    )


def _learning_roadmap_progress_reply(
    reference: str, chat_id: str = ""
) -> tuple[str, str]:
    roadmap = _resolve_roadmap_from_context_or_ref(reference, chat_id)
    if roadmap is None:
        return _learning_unknown_roadmap_reply(reference)
    reply = (
        f"**{roadmap['name']}**: you've completed "
        f"**{roadmap['completed_count']} of {roadmap['topic_count']}** topics "
        f"({roadmap['completion_percent']}%), with "
        f"{roadmap['in_progress_count']} in progress."
    )
    if roadmap["next_topic"]:
        reply += f" Next up: **{roadmap['next_topic']}**."
    else:
        reply += " There's nothing unlocked left to learn in this roadmap."
    return reply, "local-learning"


def _learning_roadmap_topics_reply(
    reference: str, chat_id: str = ""
) -> tuple[str, str]:
    roadmap = _resolve_roadmap_from_context_or_ref(reference, chat_id)
    if roadmap is None:
        return _learning_unknown_roadmap_reply(reference)
    detail = learning_progress.get_roadmap(roadmap["id"])
    topics = (detail or {}).get("topics") or []
    if not topics:
        return (
            f"**{roadmap['name']}** doesn't have any topics yet. "
            f"Say 'add topic <name> to {roadmap['name']}' to add one.",
            "local-learning",
        )
    status_badges = {
        "completed": "✅ Completed",
        "learning": "🔄 In progress",
        "on_hold": "⏸️ On hold",
        "not_started": "🔓 Ready",
    }
    lines = []
    for t in topics:
        if t["status"] == "not_started" and not t.get("available", True):
            prereqs = ", ".join(t.get("unmet_prerequisites") or [])
            badge = f"🔒 Locked (needs {prereqs})"
        else:
            badge = status_badges.get(t["status"], t["status"])
        lines.append(f"- **{t['name']}** — {badge}")
    return (
        f"Topics in **{roadmap['name']}** ({roadmap['completed_count']}/{roadmap['topic_count']} completed):\n"
        + "\n".join(lines),
        "local-learning",
    )


def _learning_status_topics_reply(raw_filter: str) -> tuple[str, str]:
    norm = re.sub(r"[\s\-]+", " ", raw_filter.strip().lower())
    if norm in {"in progress", "active", "current", "currently learning", "learning", "studying"}:
        status = "learning"
        label = "currently in progress"
        empty_msg = "You don't have any learning topics in progress right now. Say 'what should I learn next' to pick one!"
    elif norm in {"completed", "finished", "learned", "mastered"}:
        status = "completed"
        label = "completed"
        empty_msg = "You haven't marked any learning topics completed yet."
    elif norm in {"on hold", "paused"}:
        status = "on_hold"
        label = "on hold"
        empty_msg = "You don't have any learning topics on hold."
    else:
        status = "not_started"
        label = "not started"
        empty_msg = "All topics are either in progress or completed!"

    items = learning_progress.list_topics(status=status)
    if not items:
        return (empty_msg, "local-learning")
    lines = [
        f"- **{item['name']}** ({item['roadmap_name']})"
        for item in items
    ]
    return (
        f"Here are your learning topics **{label}** ({len(items)}):\n"
        + "\n".join(lines),
        "local-learning",
    )


def _learning_unknown_roadmap_reply(reference: str) -> tuple[str, str]:
    names = ", ".join(
        item["name"] for item in learning_progress.roadmap_summaries()
    )
    reply = f"I couldn't find a learning roadmap named **{reference}**."
    if names:
        reply += f" Your roadmaps are: {names}."
    return reply, "local-learning"


def _learning_next_reply(
    roadmap_reference: str | None = None,
    *,
    suggest_task: bool = False,
    chat_id: str = "",
) -> tuple[str, str]:
    roadmap = None
    if roadmap_reference:
        roadmap = _resolve_roadmap_from_context_or_ref(roadmap_reference, chat_id)
        if roadmap is None:
            return _learning_unknown_roadmap_reply(roadmap_reference)
    items = learning_progress.next_topics(
        limit=3, roadmap_id=roadmap["id"] if roadmap else None
    )
    if not items:
        scope = f" in {roadmap['name']}" if roadmap else ""
        return (
            f"Everything that's unlocked{scope} is already completed — add a "
            "new topic or roadmap when you're ready.",
            "local-learning",
        )
    if suggest_task:
        first = items[0]
        return (
            f"Try this task for **{first['roadmap_name']}**: "
            f"**Practice {first['name']}**. {first['reason']} "
            f"Say 'start learning {first['name']}' when you begin.",
            "local-learning",
        )
    lines = [
        f"- **{item['name']}** ({item['roadmap_name']}) — {item['reason']}"
        for item in items
    ]
    header = "Here's what's ready to learn"
    if roadmap:
        header += f" in **{roadmap['name']}**"
    return (
        header + ":\n"
        + "\n".join(lines)
        + "\n\nSay 'start learning <topic>' when you begin one.",
        "local-learning",
    )


def _learning_start_reply(
    reference: str, name: str = "", chat_id: str = ""
) -> tuple[str, str]:
    topics = _resolve_topic_from_context_or_ref(reference, chat_id)
    if not topics:
        raise ValueError(f"No topic matched '{reference}'.")
    topic = topics[0]
    if topic["status"] == "completed":
        return (
            f"**{topic['name']}** is already completed — say 'reopen "
            f"learning {topic['name']}' only if you really want to redo it.",
            "local-learning",
        )
    if topic["status"] == "learning":
        return (
            f"**{topic['name']}** is already in progress. Keep going!"
            + (f" {name.split()[0]}, you've got this." if name else ""),
            "local-learning",
        )
    unmet = learning_progress.unavailable_prerequisite_names(topic["id"])
    if unmet:
        return (
            f"**{topic['name']}** isn't unlocked yet — finish "
            f"{', '.join(unmet)} first.",
            "local-learning",
        )
    learning_progress.set_topic_status(topic["id"], "learning")
    return (
        f"Marked **{topic['name']}** as in progress. I'll keep it at the "
        f"top of your next-topic list.",
        "local-learning",
    )


def _learning_complete_reply(
    reference: str, name: str = "", chat_id: str = ""
) -> tuple[str, str]:
    topics = _resolve_topic_from_context_or_ref(reference, chat_id)
    if not topics:
        raise ValueError(f"No topic matched '{reference}'.")
    if len(topics) > 1:
        names = []
        for t in topics:
            learning_progress.set_topic_status(t["id"], "completed")
            names.append(f"**{t['name']}**")
        return (
            f"Nice work — marked {', '.join(names)} as completed. "
            "Say 'what should I learn next' to keep rolling.",
            "local-learning",
        )
    topic = topics[0]
    if topic["status"] == "completed":
        return (
            f"**{topic['name']}** was already marked completed.",
            "local-learning",
        )
    learning_progress.set_topic_status(topic["id"], "completed")
    return (
        f"Nice work — **{topic['name']}** is marked completed"
        + (f", {name.split()[0]}" if name else "")
        + ". Say 'what should I learn next' to keep rolling.",
        "local-learning",
    )


def _learning_hold_reply(
    reference: str, chat_id: str = ""
) -> tuple[str, str]:
    topics = _resolve_topic_from_context_or_ref(reference, chat_id)
    if not topics:
        raise ValueError(f"No topic matched '{reference}'.")
    topic = topics[0]
    learning_progress.set_topic_status(topic["id"], "on_hold")
    return (
        f"Put **{topic['name']}** on hold. Say 'start learning {topic['name']}' "
        "whenever you're ready to pick it back up.",
        "local-learning",
    )


def _learning_reopen_reply(
    reference: str, chat_id: str = ""
) -> tuple[str, str]:
    topics = _resolve_topic_from_context_or_ref(reference, chat_id)
    if not topics:
        raise ValueError(f"No topic matched '{reference}'.")
    topic = topics[0]
    learning_progress.set_topic_status(topic["id"], "not_started")
    return (
        f"Reopened **{topic['name']}** and reset its status to not started.",
        "local-learning",
    )


def _format_imported_path_reply(imported: dict[str, Any]) -> tuple[str, str]:
    roadmap = imported["roadmap"]
    added = imported["added_topics"]
    total = imported["topic_count"]
    action_word = "Created" if imported["created_roadmap"] else "Updated"
    preview_names = [f"**{t['name']}**" for t in added[:5]]
    more_suffix = f", and {len(added) - 5} more" if len(added) > 5 else ""
    preview_str = (", ".join(preview_names) + more_suffix) if preview_names else "no new sub-topics"
    first_topic = added[0]["name"] if added else (roadmap.get("next_topic") or "the first topic")
    return (
        f"{action_word} **{roadmap['category']}** learning path **{roadmap['name']}** with "
        f"**{len(added)} sub-topic{'s' if len(added) != 1 else ''}** ({total} total: {preview_str}).\n\n"
        f"Say `start learning {first_topic}` whenever you're ready!",
        "local-learning",
    )


def _try_bulk_learning_import(prompt: str, chat_id: str = "") -> tuple[str, str] | None:
    """Detect multi-line pasted sub-topic headings or bulk learning path commands."""
    raw = (prompt or "").strip()
    if "\n" not in raw:
        return None

    raw_lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(raw_lines) < 3:
        return None

    # Never hijack completion/deletion/update requests (e.g. pasting UI rows + "mark all this completed")
    if re.search(
        r"\b(?:mark\s+(?:all|these|this|them)\b.*(?:completed|complete|done|finished|started|in\s+progress)|"
        r"(?:delete|remove|complete|finish)\s+(?:all|these|them))\b",
        raw,
        re.IGNORECASE,
    ):
        return None

    first_line = raw_lines[0]
    has_learning_cue = bool(
        re.search(
            r"\b(?:headings?|sub[\s\-]?topics?|topics?|roadmap|learning(?:\s+path)?|syllabus|modules?|chapters?|paste\s+in)\b",
            raw,
            re.IGNORECASE,
        )
    )
    if not has_learning_cue:
        return None

    # Check if the user is adding multi-line topics to a specific existing roadmap
    add_to_match = re.match(
        r"^(?:add|create|insert|paste)\s+(?:these\s+|the\s+|new\s+)?(?:learning\s+)?(?:sub[\s\-]?topics?|topics?|headings?)\s+"
        r"(?:to|in|into|under|for)\s+(?:the\s+|my\s+)?(?P<roadmap>[A-Za-z0-9+#.\-/&\s]{1,50}?)(?:\s+(?:roadmap|learning\s+path))?\s*:?$",
        first_line,
        re.IGNORECASE,
    )
    explicit_name: str | None = None
    body_text = raw
    if add_to_match:
        rm_ref = add_to_match.group("roadmap").strip()
        existing_rm = _resolve_roadmap_from_context_or_ref(rm_ref, chat_id)
        explicit_name = existing_rm["name"] if existing_rm else rm_ref
        body_text = "\n".join(raw_lines[1:])

    parsed_name, parsed_topics = learning_progress.parse_learning_path_input(
        body_text, explicit_name=explicit_name
    )
    if len(parsed_topics) < 2:
        return None

    if not parsed_name:
        # Try context roadmap if one was recently discussed
        ctx_rm = _resolve_roadmap_from_context_or_ref("this roadmap", chat_id)
        parsed_name = ctx_rm["name"] if ctx_rm else "Custom Learning Path"

    imported = learning_progress.import_learning_path(
        name=parsed_name,
        topics=parsed_topics,
        auto_generate_if_empty=False,
    )
    return _format_imported_path_reply(imported)


def _learning_command(
    prompt: str, name: str = "", chat_id: str = ""
) -> tuple[str, str] | None:
    """Handle learning tracker commands; requires the schema to be ready."""
    if not learning_schema.is_initialized():
        return None

    # 1. Check for multi-line pasted sub-topic headings before collapsing newlines
    bulk_imported = _try_bulk_learning_import(prompt, chat_id=chat_id)
    if bulk_imported is not None:
        return bulk_imported

    # 1b. Link local learning folder (parse raw prompt before punctuation normalization)
    raw_stripped = (prompt or "").strip()
    link_folder_match = _LEARNING_LINK_FOLDER_RAW_PATTERN.fullmatch(raw_stripped)
    if link_folder_match:
        raw_path = link_folder_match.group("path").strip().strip("\"'")
        rm_ref = link_folder_match.group("roadmap").strip().strip("\"'?!.")
        roadmap = _resolve_roadmap_from_context_or_ref(rm_ref, chat_id)
        if roadmap is None:
            return _learning_unknown_roadmap_reply(rm_ref)
        try:
            embed = getattr(_app().memory_store, "embed", None)
            res = learning_code_rag.link_folder_to_roadmap(
                int(roadmap["id"]), raw_path, sync_now=True, embed=embed
            )
            sync_info = res.get("sync") or {}
            return (
                f"Linked `{res['folder']['folder_path']}` to **{roadmap['name']}**!\n\n"
                + (sync_info.get("friendly_summary") or "I'll keep tracking your code automatically."),
                "local-learning",
            )
        except ValueError as err:
            return (str(err), "local-learning")

    normalized = _app()._normalize_command(prompt)

    # Sync / analyze linked code folder(s)
    sync_match = _LEARNING_SYNC_FOLDER_PATTERN.fullmatch(normalized)
    if sync_match:
        rm_ref = (
            sync_match.group("roadmap")
            or sync_match.group("roadmap2")
            or sync_match.group("roadmap3")
            or ""
        ).strip()
        embed = getattr(_app().memory_store, "embed", None)
        if rm_ref:
            roadmap = _resolve_roadmap_from_context_or_ref(rm_ref, chat_id)
            if roadmap is None:
                return _learning_unknown_roadmap_reply(rm_ref)
            try:
                res = learning_code_rag.sync_roadmap_folder(int(roadmap["id"]), embed=embed)
                return (res["friendly_summary"], "local-learning")
            except ValueError as err:
                return (str(err), "local-learning")
        results = learning_code_rag.sync_all_linked_folders(embed=embed)
        if not results:
            return (
                "No learning folders are linked yet! Say `link folder <path> to <roadmap>` or link one on the Learning page.",
                "local-learning",
            )
        summaries = [r["friendly_summary"] for r in results if r.get("friendly_summary")]
        return ("\n\n".join(summaries) or "Synced your learning folders.", "local-learning")

    # Confirm or dismiss code-detected topic completion suggestions
    code_sugg_match = _LEARNING_CODE_SUGGESTION_ACTION_PATTERN.fullmatch(normalized)
    if code_sugg_match:
        action = code_sugg_match.group("action").lower()
        new_state = "confirmed" if action in {"confirm", "accept", "approve"} else "dismissed"
        pending = learning_code_rag.list_code_suggestions(state="pending")
        if not pending:
            return ("You don't have any pending code completion suggestions right now.", "local-learning")
        if code_sugg_match.group("all"):
            names_done = []
            for item in pending:
                learning_code_rag.resolve_code_suggestion(int(item["id"]), new_state)
                names_done.append(f"**{item['topic_name']}**")
            verb = "Marked completed" if new_state == "confirmed" else "Dismissed"
            return (f"{verb}: {', '.join(names_done)}.", "local-learning")
        target = (code_sugg_match.group("target") or "").strip().lower()
        chosen = pending[0]
        if target:
            if target.isdigit():
                chosen = next((p for p in pending if p["id"] == int(target)), chosen)
            else:
                chosen = next((p for p in pending if target in p["topic_name"].lower()), chosen)
        learning_code_rag.resolve_code_suggestion(int(chosen["id"]), new_state)
        if new_state == "confirmed":
            return (
                f"Nice work — confirmed **{chosen['topic_name']}** as completed based on your code!",
                "local-learning",
            )
        return (f"Got it, dismissed the completion suggestion for **{chosen['topic_name']}**.", "local-learning")
    if _LEARNING_PROGRESS_PATTERN.fullmatch(normalized) or _LEARNING_BARE_PATTERN.fullmatch(normalized):
        return _learning_progress_reply()
    if _LEARNING_NEXT_PATTERN.fullmatch(normalized):
        return _learning_next_reply(chat_id=chat_id)

    # Learning activity log
    if _LEARNING_ACTIVITY_PATTERN.fullmatch(normalized):
        activities = learning_progress.list_activities(limit=8)
        if not activities:
            return ("No learning activity recorded yet. Start a topic to log your progress!", "local-learning")
        lines = [
            f"- **{a['topic_name']}** ({a['roadmap_name']}): {a['kind']}"
            + (f" via task *{a['task_title']}*" if a.get("task_title") else "")
            for a in activities
        ]
        return ("Recent learning activity:\n" + "\n".join(lines), "local-learning")

    # Learning nudges toggle / status
    nudges_match = _LEARNING_NUDGES_PATTERN.fullmatch(normalized)
    if nudges_match:
        state_word = (nudges_match.group("state") or "").lower()
        if state_word == "status":
            enabled = learning_progress.get_nudges_enabled()
            return (
                f"Learning nudges are currently **{'enabled' if enabled else 'disabled'}**.",
                "local-learning",
            )
        enable = bool(nudges_match.group("enable")) or state_word == "on"
        learning_progress.set_nudges_enabled(enable)
        return (
            f"Learning nudges are now **{'enabled' if enable else 'disabled'}**.",
            "local-learning",
        )

    # Suggested task-topic links list & confirmation
    if _LEARNING_LINKS_LIST_PATTERN.fullmatch(normalized):
        links = learning_progress.list_suggested_links()
        if not links:
            return ("You don't have any pending suggested task-topic links right now.", "local-learning")
        lines = [
            f"- Link #{l['id']}: Task **{l['task_title']}** → Topic **{l['topic_name']}** ({l['roadmap_name']})"
            for l in links[:10]
        ]
        return (
            "Suggested task-topic learning links:\n"
            + "\n".join(lines)
            + "\n\nSay 'confirm learning link' or 'reject learning link' to manage them.",
            "local-learning",
        )

    link_act = _LEARNING_LINK_ACTION_PATTERN.fullmatch(normalized)
    if link_act:
        action = link_act.group("action").lower()
        new_state = "confirmed" if action in {"confirm", "accept", "approve"} else "rejected"
        links = learning_progress.list_suggested_links()
        if not links:
            return ("There are no pending suggested learning links right now.", "local-learning")
        target_str = (link_act.group("target") or "").strip()
        if link_act.group("all"):
            for l in links:
                learning_progress.update_task_link(l["id"], new_state)
            return (
                f"{new_state.capitalize()} all {len(links)} suggested learning links.",
                "local-learning",
            )
        chosen = links[0]
        if target_str:
            if target_str.isdigit():
                lid = int(target_str)
                chosen = next((l for l in links if l["id"] == lid), chosen)
            else:
                t_low = target_str.lower()
                chosen = next(
                    (
                        l for l in links
                        if t_low in l["topic_name"].lower() or t_low in l["task_title"].lower()
                    ),
                    chosen,
                )
        learning_progress.update_task_link(chosen["id"], new_state)
        return (
            f"{new_state.capitalize()} link between task **{chosen['task_title']}** and topic **{chosen['topic_name']}**.",
            "local-learning",
        )

    # Create learning path with automatic sub-topic division (or inline comma-separated sub-topics)
    auto_path = _LEARNING_PATH_AUTO_CREATE_PATTERN.fullmatch(normalized)
    if auto_path:
        raw_name = (
            auto_path.group("name1")
            or auto_path.group("name2")
            or auto_path.group("name3")
            or ""
        ).strip(" \"':-")
        # Guard against matching status/start commands like "start learning Java Basics"
        if raw_name and not normalized.lower().startswith(("start learning ", "continue learning ", "resume learning ")):
            raw_name = re.sub(
                r"\s+(?:and\s+)?(?:with\s+|divide(?:\s+into)?\s+|auto[\s\-]?generate\s+)?sub[\s\-]?topics?$",
                "",
                raw_name,
                flags=re.IGNORECASE,
            ).strip(" \"':-")
            cat = (auto_path.group("cat") or "technical").lower()
            inline_topics = auto_path.group("inline_topics")
            imported = learning_progress.import_learning_path(
                name=raw_name,
                raw_text=inline_topics,
                category=cat,
                auto_generate_if_empty=True,
            )
            return _format_imported_path_reply(imported)

    # Create / delete roadmap
    rm_create = _LEARNING_ROADMAP_CREATE_PATTERN.fullmatch(normalized)
    if rm_create:
        rm_name = rm_create.group("name").strip(" \"'")
        cat = (rm_create.group("cat") or rm_create.group("cat2") or "technical").lower()
        # Check if inline sub-topics were given after a colon or "with topics ..."
        inline_split = re.split(r"\s*(?::|\bwith\s+(?:sub[\s\-]?)?topics?\b)\s*", rm_name, maxsplit=1, flags=re.IGNORECASE)
        if len(inline_split) == 2 and inline_split[0].strip() and inline_split[1].strip():
            imported = learning_progress.import_learning_path(
                name=inline_split[0].strip(" \"'"),
                raw_text=inline_split[1],
                category=cat,
                auto_generate_if_empty=False,
            )
            return _format_imported_path_reply(imported)
        created = learning_progress.create_roadmap(rm_name, category=cat)
        return (
            f"Created **{created['category']}** learning roadmap **{created['name']}**. "
            f"Say 'add topic <name> to {created['name']}' to add topics.",
            "local-learning",
        )

    rm_delete = _LEARNING_ROADMAP_DELETE_PATTERN.fullmatch(normalized)
    if rm_delete:
        ref = (rm_delete.group(1) or rm_delete.group(2) or "").strip()
        roadmap = _resolve_roadmap_from_context_or_ref(ref, chat_id)
        if roadmap is None:
            return _learning_unknown_roadmap_reply(ref)
        learning_progress.delete_roadmap(roadmap["id"])
        return (f"Deleted learning roadmap **{roadmap['name']}**.", "local-learning")

    # Bulk add comma/semicolon-separated sub-topics to an existing roadmap
    bulk_t = _LEARNING_BULK_TOPICS_ADD_PATTERN.fullmatch(normalized)
    if bulk_t and ("," in bulk_t.group("topics") or ";" in bulk_t.group("topics")):
        raw_topics = bulk_t.group("topics").strip()
        rm_ref = bulk_t.group("roadmap").strip(" \"'")
        roadmap = _resolve_roadmap_from_context_or_ref(rm_ref, chat_id)
        if roadmap is None:
            return _learning_unknown_roadmap_reply(rm_ref)
        imported = learning_progress.import_learning_path(
            name=roadmap["name"],
            raw_text=raw_topics,
            category=roadmap["category"],
            auto_generate_if_empty=False,
        )
        return _format_imported_path_reply(imported)

    # Create / delete / reprioritize topic
    t_create = _LEARNING_TOPIC_CREATE_PATTERN.fullmatch(normalized)
    if t_create:
        t_name = t_create.group("topic").strip(" \"'")
        rm_ref = t_create.group("roadmap").strip(" \"'")
        roadmap = _resolve_roadmap_from_context_or_ref(rm_ref, chat_id)
        if roadmap is None:
            return _learning_unknown_roadmap_reply(rm_ref)
        created = learning_progress.create_topic(roadmap["id"], t_name)
        return (
            f"Added topic **{created['name']}** to **{roadmap['name']}**.",
            "local-learning",
        )

    t_delete = _LEARNING_TOPIC_DELETE_PATTERN.fullmatch(normalized)
    if t_delete:
        ref = (t_delete.group(1) or t_delete.group(2) or "").strip()
        topics = _resolve_topic_from_context_or_ref(ref, chat_id)
        if not topics:
            raise ValueError(f"No topic matched '{ref}'.")
        topic = topics[0]
        learning_progress.delete_topic(topic["id"])
        return (f"Removed topic **{topic['name']}**.", "local-learning")

    t_prio = _LEARNING_TOPIC_PRIORITY_PATTERN.fullmatch(normalized)
    if t_prio:
        ref = t_prio.group(1).strip()
        prio_raw = t_prio.group(2).lower()
        prio_map = {"low": 1, "1": 1, "medium": 2, "2": 2, "high": 3, "3": 3}
        prio_label = {1: "low", 2: "medium", 3: "high"}
        prio_val = prio_map[prio_raw]
        topics = _resolve_topic_from_context_or_ref(ref, chat_id)
        if not topics:
            raise ValueError(f"No topic matched '{ref}'.")
        updated = learning_progress.update_topic(topics[0]["id"], priority=prio_val)
        return (
            f"Updated **{updated['name']}** priority to **{prio_label[prio_val]}**.",
            "local-learning",
        )

    # Filter topics by status ("what am I currently learning", "completed topics", "topics on hold")
    status_match = _LEARNING_STATUS_LIST_PATTERN.fullmatch(normalized)
    if status_match:
        raw_filter = (
            status_match.group("filter")
            or status_match.group("filter2")
            or status_match.group("filter3")
            or "learning"
        )
        return _learning_status_topics_reply(raw_filter)

    # List topics in a specific roadmap
    rm_topics_match = _LEARNING_ROADMAP_TOPICS_PATTERN.fullmatch(normalized)
    if rm_topics_match:
        reference = next(group for group in rm_topics_match.groups() if group)
        return _learning_roadmap_topics_reply(reference.strip(), chat_id=chat_id)

    match = _LEARNING_ROADMAP_PROGRESS_PATTERN.fullmatch(normalized)
    if match:
        reference = next(group for group in match.groups() if group)
        return _learning_roadmap_progress_reply(reference.strip(), chat_id=chat_id)
    match = _LEARNING_ROADMAP_TASK_PATTERN.fullmatch(normalized)
    if match:
        reference = next(group for group in match.groups() if group)
        return _learning_next_reply(reference.strip(), suggest_task=True, chat_id=chat_id)
    match = _LEARNING_ROADMAP_NEXT_PATTERN.fullmatch(normalized)
    if match:
        reference = next(group for group in match.groups() if group)
        return _learning_next_reply(reference.strip(), chat_id=chat_id)

    has_learning_keyword = bool(
        re.search(
            r"\b(?:topic|topics|roadmap|roadmaps|lesson|lessons|module|modules|learning|study|studying)\b",
            normalized,
            re.IGNORECASE,
        )
    )

    # Pause / On hold
    hold_match = _LEARNING_HOLD_PATTERN.fullmatch(normalized)
    if hold_match:
        reference = next(group for group in hold_match.groups() if group).strip()
        topics = _resolve_topic_from_context_or_ref(reference, chat_id)
        if not topics and not has_learning_keyword:
            return None
        return _learning_hold_reply(reference, chat_id=chat_id)

    # Reopen / Reset
    reopen_match = _LEARNING_REOPEN_PATTERN.fullmatch(normalized)
    if reopen_match:
        reference = next(group for group in reopen_match.groups() if group).strip()
        topics = _resolve_topic_from_context_or_ref(reference, chat_id)
        if not topics and not has_learning_keyword:
            return None
        return _learning_reopen_reply(reference, chat_id=chat_id)

    match = _LEARNING_START_PATTERN.fullmatch(normalized)
    if match:
        reference = next(group for group in match.groups() if group).strip()
        topics = _resolve_topic_from_context_or_ref(reference, chat_id)
        if not topics and not has_learning_keyword:
            return None
        return _learning_start_reply(reference, name=name, chat_id=chat_id)

    if not _app()._has_negation_or_unmark(normalized):
        match = _LEARNING_COMPLETE_PATTERN.fullmatch(normalized)
        if match:
            reference = next(group for group in match.groups() if group).strip()
            topics = _resolve_topic_from_context_or_ref(reference, chat_id)
            if not topics and not has_learning_keyword:
                return None
            return _learning_complete_reply(reference, name=name, chat_id=chat_id)

        match = _LEARNING_FINISHED_PATTERN.fullmatch(normalized)
        if match:
            reference = match.group(1).strip()
            topics = _resolve_topic_from_context_or_ref(reference, chat_id)
            if not topics and not has_learning_keyword:
                return None
            return _learning_complete_reply(reference, name=name, chat_id=chat_id)
    return None


