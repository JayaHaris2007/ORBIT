"""Local deterministic command router and contextual follow-up resolution."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

def _app():
    import app

    return app


_MEMORY_CREATE_PATTERN = re.compile(
    r"^(?:(?:add|create|save|write|take)\s+(?:a\s+)?(?:new\s+)?(?:note|memory)"
    r"(?:\s+(?:that|about|for))?(?:\s*[:\-]\s*|\s+)"
    r"|remember\s+(?:that\s+|this\s*[:\-]?\s*)"
    r"|note\s+down(?:\s*[:\-]\s*|\s+))(.+)$",
    re.IGNORECASE,
)

_MEMORY_LIST_PATTERN = re.compile(
    r"^(?:(?:show|list|check|view|read|what\s+are)\s+(?:me\s+)?)?"
    r"(?:(?:my|the|all|saved)\s+)*(?:notes?|memories|saved\s+notes?|saved\s+memories)$",
    re.IGNORECASE,
)

_MEMORY_DELETE_PATTERN = re.compile(
    r"^(?:delete|remove|forget)\s+(?:(?:the|my)\s+)?(?:note|memory)\s+(?:#?)(.+)$"
    r"|^(?:delete|remove|forget)\s+(?:(?:the|my)\s+)?(.+?)\s+(?:(?:note|memory)|(?:in|from)\s+(?:(?:the|my)\s+)?(?:notes?|memor(?:y|ies)))$",
    re.IGNORECASE,
)


def _memory_command(prompt: str) -> tuple[str, str] | None:
    """Deterministic CRUD handler for notes and memories."""
    normalized = _app()._normalize_command(prompt)
    create_match = _MEMORY_CREATE_PATTERN.fullmatch(normalized)
    if create_match:
        content = create_match.group(1).strip(" \"'")
        if not content:
            return ("What would you like me to save in your notes?", "local-memory")
        try:
            saved = _app().memory_store.add_memory(content)
            return (f"Saved to your notes: **{saved['content']}**", "local-memory")
        except ValueError as err:
            if "already exists" in str(err).lower():
                return (f"I already have **{content}** in your notes.", "local-memory")
            raise

    delete_match = _MEMORY_DELETE_PATTERN.fullmatch(normalized)
    if delete_match:
        ref = (delete_match.group(1) or delete_match.group(2) or "").strip(" \"'")
        memories = _app().memory_store.list_memories()
        target_mem = None
        if ref.isdigit():
            mem_id = int(ref)
            target_mem = next((m for m in memories if m["id"] == mem_id), None)
        if target_mem is None:
            lowered = ref.lower()
            matches = [m for m in memories if lowered in m["content"].lower()]
            if len(matches) == 1:
                target_mem = matches[0]
            elif len(matches) > 1:
                raise ValueError(f"More than one note matches '{ref}'. Be more specific.")
        if target_mem is None:
            raise ValueError(f"No saved note matched '{ref}'.")
        _app().memory_store.delete_memory(target_mem["id"])
        return (f"Removed note: **{target_mem['content']}**.", "local-memory")

    if _MEMORY_LIST_PATTERN.fullmatch(normalized):
        memories = _app().memory_store.list_memories()
        if not memories:
            return ("You don't have any saved notes yet. Say 'add note: <text>' to save one.", "local-memory")
        lines = [f"- #{m['id']} {m['content']}" for m in memories[:15]]
        return ("Here are your saved notes:\n" + "\n".join(lines), "local-memory")

    return None


_PRONOUN_TARGETS = {
    "it", "that", "this", "this one", "that one", "the one",
    "the task", "the habit", "that task", "that habit", "this task", "this habit",
    "the topic", "that topic", "this topic",
    "first", "the first", "first one", "the first one", "1st", "the 1st",
    "second", "the second", "second one", "the second one", "2nd", "the 2nd",
    "third", "the third", "third one", "the third one", "3rd", "the 3rd",
    "both", "both of them", "them", "all", "all of them", "everything",
    "all tasks", "all my tasks", "all habits", "all my habits",
}


def _extract_context_entities(
    chat_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (mentioned_tasks, mentioned_habits) from the recent assistant messages in chat_id."""
    messages = _app().memory_store.get_messages(chat_id) if chat_id else []
    assistant_msgs = [
        m["content"] for m in reversed(messages) if m.get("role") == "assistant"
    ][:3]
    all_habits = _app().memory_store.list_habits()
    all_tasks = _app().memory_store.list_tasks(include_completed=True)

    for content in assistant_msgs:
        lower_content = content.lower()
        task_ids = [int(tid) for tid in re.findall(r"#(\d+)\b", content)]
        if task_ids and (
            "task" in lower_content
            or "list" in lower_content
            or "still to do" in lower_content
            or "priority" in lower_content
            or "next up" in lower_content
        ):
            matched_tasks = [
                t for tid in task_ids for t in all_tasks if t["id"] == tid
            ]
            if matched_tasks:
                return matched_tasks, []

        mentioned_habits: list[tuple[int, dict[str, Any]]] = []
        for habit in all_habits:
            h_name = habit["name"].strip().lower()
            pos = lower_content.find(h_name)
            if pos != -1:
                mentioned_habits.append((pos, habit))
        if mentioned_habits and (
            "habit" in lower_content
            or "streak" in lower_content
            or "tackle" in lower_content
            or "list today" in lower_content
            or "checked off" in lower_content
            or "unchecked" in lower_content
            or "unmarked" in lower_content
        ):
            mentioned_habits.sort(key=lambda pair: pair[0])
            return [], [h for _, h in mentioned_habits]

        mentioned_tasks: list[tuple[int, dict[str, Any]]] = []
        for task in all_tasks:
            t_title = task["title"].strip().lower()
            pos = lower_content.find(t_title)
            if pos != -1:
                mentioned_tasks.append((pos, task))
        if mentioned_tasks:
            mentioned_tasks.sort(key=lambda pair: pair[0])
            return [t for _, t in mentioned_tasks], []

    return [], []


def _resolve_contextual_completion(
    target: str, chat_id: str, name: str = ""
) -> tuple[str, str] | None:
    """Resolve pronouns ('it', 'that', 'the first one', 'both', 'all') using recent chat history."""
    cleaned = re.sub(r"\s+", " ", target.strip().lower())
    if cleaned not in _PRONOUN_TARGETS:
        return None

    # Check if the most recent assistant message was about learning topics
    ctx_topics, _, is_recent_learning = _app()._extract_learning_context(chat_id)
    if (is_recent_learning or "topic" in cleaned) and ctx_topics and "task" not in cleaned and "habit" not in cleaned:
        return _app()._learning_complete_reply(cleaned, name=name, chat_id=chat_id)

    all_habits = _app().memory_store.list_habits()
    pending_tasks = _app().memory_store.list_tasks(include_completed=False)
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    pending_habits = [h for h in all_habits if today not in h["completed_dates"]]

    # Handle explicit batch targets ("all tasks", "all habits")
    if cleaned in {"all tasks", "all my tasks"}:
        all_tasks_list = _app().memory_store.list_tasks(include_completed=True)
        if not all_tasks_list:
            return ("You don't have any tasks set up yet.", "local-task-manager")
        if not pending_tasks:
            return ("All your tasks are already completed!", "local-task-manager")
        titles = [t["title"] for t in pending_tasks]
        for t in pending_tasks:
            _app()._complete_task(t, name=name)
        if len(titles) == len(all_tasks_list):
            return (
                f"Marked all {len(titles)} pending tasks completed: "
                + ", ".join(f"**{title}**" for title in titles) + ".",
                "local-task-manager",
            )
        return (
            f"Marked the remaining {len(titles)} pending task{'s' if len(titles) != 1 else ''} completed: "
            + ", ".join(f"**{title}**" for title in titles)
            + f" (all {len(all_tasks_list)} tasks are now completed!).",
            "local-task-manager",
        )
    if cleaned in {"all habits", "all my habits"}:
        if not all_habits:
            return ("You don't have any habits set up yet.", "local-habit-manager")
        if not pending_habits:
            return ("All your habits are already checked off for today!", "local-habit-manager")
        names = [h["name"] for h in pending_habits]
        for h in pending_habits:
            _app()._complete_habit(h, name=name)
        if len(names) == len(all_habits):
            return (
                f"Checked off all {len(names)} habits for today: "
                + ", ".join(f"**{n}**" for n in names) + ".",
                "local-habit-manager",
            )
        return (
            f"Checked off the remaining {len(names)} habit{'s' if len(names) != 1 else ''} for today: "
            + ", ".join(f"**{n}**" for n in names)
            + f" (all {len(all_habits)} habits are now completed!).",
            "local-habit-manager",
        )

    ctx_tasks, ctx_habits = _extract_context_entities(chat_id)
    is_batch = cleaned in {"both", "both of them", "them", "all", "all of them", "everything"}

    if is_batch:
        if ctx_tasks:
            open_ctx = [t for t in ctx_tasks if not t["completed"]] or ctx_tasks
            for t in open_ctx:
                _app()._complete_task(t, name=name)
            return (
                "Completed: " + ", ".join(f"**{t['title']}**" for t in open_ctx) + ".",
                "local-task-manager",
            )
        if ctx_habits:
            for h in ctx_habits:
                _app()._complete_habit(h, name=name)
            return (
                "Checked off: " + ", ".join(f"**{h['name']}**" for h in ctx_habits) + ".",
                "local-habit-manager",
            )
        if ctx_topics:
            return _app()._learning_complete_reply(cleaned, name=name, chat_id=chat_id)

    ordinal = 0
    if "second" in cleaned or "2nd" in cleaned:
        ordinal = 1
    elif "third" in cleaned or "3rd" in cleaned:
        ordinal = 2

    if ctx_tasks and "habit" not in cleaned:
        chosen = ctx_tasks[ordinal] if ordinal < len(ctx_tasks) else ctx_tasks[0]
        return (_app()._complete_task(chosen, name=name), "local-task-manager")

    if ctx_habits and "task" not in cleaned:
        chosen = ctx_habits[ordinal] if ordinal < len(ctx_habits) else ctx_habits[0]
        return (_app()._complete_habit(chosen, name=name), "local-habit-manager")

    if ctx_topics and "task" not in cleaned and "habit" not in cleaned:
        return _app()._learning_complete_reply(cleaned, name=name, chat_id=chat_id)

    # Fallback: if there is globally only 1 pending task, complete it
    if len(pending_tasks) == 1 and ("habit" not in cleaned) and ("topic" not in cleaned):
        return (_app()._complete_task(pending_tasks[0], name=name), "local-task-manager")

    if len(pending_habits) == 1 and ("task" not in cleaned) and ("topic" not in cleaned):
        return (_app()._complete_habit(pending_habits[0], name=name), "local-habit-manager")

    return None


def _resolve_contextual_mutation(
    prompt: str, chat_id: str, name: str = ""
) -> tuple[str, str] | None:
    """Handle contextual 'delete it', 'make it high priority', 'undo it', or 'reopen it'."""
    normalized = _app()._normalize_command(prompt).lower()
    ctx_topics, _, is_recent_learning = _app()._extract_learning_context(chat_id)

    # 1. Contextual Delete: "delete it", "remove that", "delete the first one"
    del_match = re.fullmatch(
        r"(?:delete|remove|drop|cancel)\s+"
        r"(it|that|this|that\s+one|this\s+one|the\s+task|the\s+habit|the\s+topic|that\s+topic|"
        r"(?:the\s+)?(?:first|second|third|1st|2nd|3rd)(?:\s+one)?)",
        normalized,
        re.IGNORECASE,
    )
    if del_match:
        target_ref = del_match.group(1)
        ordinal = 1 if ("second" in target_ref or "2nd" in target_ref) else (2 if ("third" in target_ref or "3rd" in target_ref) else 0)
        if (is_recent_learning or "topic" in target_ref) and ctx_topics and "task" not in target_ref and "habit" not in target_ref:
            chosen_t = ctx_topics[ordinal] if ordinal < len(ctx_topics) else ctx_topics[0]
            _app().learning_progress.delete_topic(chosen_t["id"])
            return (f"Removed topic **{chosen_t['name']}**.", "local-learning")
        ctx_tasks, ctx_habits = _extract_context_entities(chat_id)
        if ctx_tasks and "habit" not in target_ref:
            chosen = ctx_tasks[ordinal] if ordinal < len(ctx_tasks) else ctx_tasks[0]
            _app().memory_store.delete_task(chosen["id"])
            remaining = len(_app().memory_store.list_tasks(include_completed=False))
            return (_app().assistant_tone.task_deleted(chosen["title"], remaining), "local-task-manager")
        if ctx_habits and "task" not in target_ref:
            chosen = ctx_habits[ordinal] if ordinal < len(ctx_habits) else ctx_habits[0]
            _app().memory_store.delete_habit(chosen["id"])
            return (_app().assistant_tone.habit_deleted(chosen["name"]), "local-habit-manager")

    # 2. Contextual Priority Update: "make it high priority", "set its priority to low"
    prio_match = re.fullmatch(
        r"(?:make|set|change|update)\s+"
        r"(?:it|that|this|its\s+priority|the\s+priority|the\s+task|the\s+topic)\s+"
        r"(?:to\s+)?(?:be\s+)?(?:priority\s+)?(low|medium|high)(?:\s+priority)?",
        normalized,
        re.IGNORECASE,
    )
    if prio_match:
        new_prio = prio_match.group(1).lower()
        if (is_recent_learning or "topic" in normalized) and ctx_topics and "task" not in normalized:
            prio_val = {"low": 1, "medium": 2, "high": 3}[new_prio]
            updated_t = _app().learning_progress.update_topic(ctx_topics[0]["id"], priority=prio_val)
            return (f"Updated **{updated_t['name']}** priority to **{new_prio}**.", "local-learning")
        ctx_tasks, _ = _extract_context_entities(chat_id)
        if ctx_tasks:
            chosen = ctx_tasks[0]
            updated = _app().memory_store.update_task(chosen["id"], priority=new_prio)
            return (_app().assistant_tone.task_priority(updated["title"], updated["priority"]), "local-task-manager")

    # 3. Contextual Undo / Reopen / Uncheck / Unmark: "undo it", "uncheck it", "unmark all", "reopen it", "mark it not done"
    undo_match = re.fullmatch(
        r"(?:undo|uncheck|unmark|untick|reopen|uncomplete|reset)\s+"
        r"(it|that|this|that\s+one|this\s+one|the\s+task|the\s+habit|the\s+topic|that\s+topic|"
        r"(?:the\s+)?(?:first|second|third|1st|2nd|3rd)(?:\s+one)?|"
        r"all|all\s+of\s+them|them|both|both\s+of\s+them|everything)"
        r"|mark\s+(it|that|this|all|all\s+of\s+them|them|both|both\s+of\s+them|everything)\s+(?:as\s+)?"
        r"(?:not\s+done|not\s+completed|not\s+complete|not\s+started|incomplete|unchecked|unmarked|open|pending)",
        normalized,
        re.IGNORECASE,
    )
    if undo_match:
        target_ref = (undo_match.group(1) or undo_match.group(2) or "it").lower()
        is_batch_undo = target_ref in {"all", "all of them", "them", "both", "both of them", "everything"}
        ordinal = 1 if ("second" in target_ref or "2nd" in target_ref) else (2 if ("third" in target_ref or "3rd" in target_ref) else 0)
        if (is_recent_learning or "topic" in normalized) and ctx_topics and "task" not in normalized and "habit" not in normalized:
            return _app()._learning_reopen_reply(target_ref, chat_id=chat_id)
        ctx_tasks, ctx_habits = _extract_context_entities(chat_id)
        if ctx_tasks and "habit" not in target_ref:
            if is_batch_undo:
                return _app()._reopen_all_tasks()
            chosen = ctx_tasks[ordinal] if ordinal < len(ctx_tasks) else ctx_tasks[0]
            updated = _app().memory_store.update_task(chosen["id"], completed=False)
            return (_app().assistant_tone.task_reopened(updated["title"], name=name), "local-task-manager")
        if ctx_habits and "task" not in target_ref:
            if is_batch_undo:
                return _app()._uncomplete_all_habits()
            chosen = ctx_habits[ordinal] if ordinal < len(ctx_habits) else ctx_habits[0]
            return (_app()._uncomplete_habit(chosen, name=name), "local-habit-manager")

    # 4. Follow-up batch correction: "i mean all", "all of them", "both of them"
    raw_clean = re.sub(r"\s+", " ", prompt.strip().lower()).rstrip(".!?")
    followup_all_match = re.fullmatch(
        r"(?:(?:no|wait|sorry|actually)[,\s]+)*(?:(?:i\s+mean|i\s+meant)\s+(?:all|all\s+of\s+them|both|both\s+of\s+them|everything|them)"
        r"|(?:all\s+of\s+them|both\s+of\s+them))",
        raw_clean,
        re.IGNORECASE,
    )
    if followup_all_match:
        messages = _app().memory_store.get_messages(chat_id) if chat_id else []
        last_assistant = next(
            (m["content"].lower() for m in reversed(messages) if m.get("role") == "assistant"),
            "",
        )
        ctx_tasks, ctx_habits = _extract_context_entities(chat_id)
        if any(w in last_assistant for w in ("unchecked", "unmarked", "wasn't checked off")) and (
            "habit" in last_assistant or ctx_habits
        ):
            return _app()._uncomplete_all_habits()
        if any(w in last_assistant for w in ("reopened", "still open")) and (
            "task" in last_assistant or ctx_tasks
        ):
            return _app()._reopen_all_tasks()
        if ctx_habits or "habit" in last_assistant:
            return _resolve_contextual_completion("all habits", chat_id, name=name)
        if ctx_tasks or "task" in last_assistant:
            return _resolve_contextual_completion("all tasks", chat_id, name=name)

    return None


_BRIEFING_PATTERN = re.compile(
    r"^(?:(?:show|give|tell|check|what(?:'s| is))\s+(?:me\s+)?)?"
    r"(?:(?:my|the|today'?s|daily|morning|evening|current)\s+)*"
    r"(?:briefing|daily\s+summary|summary|status|overview|day\s+summary|"
    r"dashboard\s+status|main\s+page\s+status|plate|on\s+my\s+plate)"
    r"|^how\s+am\s+i\s+doing(?:\s+today)?$"
    r"|^what(?:'s| is)\s+on\s+my\s+plate(?:\s+today)?$",
    re.IGNORECASE,
)

_XP_STATUS_PATTERN = re.compile(
    r"^(?:(?:show|check|what(?:'s| is| are))\s+(?:me\s+)?)?"
    r"(?:(?:my|the|current)\s+)*"
    r"(?:xp|level|gamification|achievements?|streaks?|global\s+streak|score|points)$",
    re.IGNORECASE,
)


def _xp_status_command(prompt: str) -> tuple[str, str] | None:
    normalized = _app()._normalize_command(prompt)
    if not _XP_STATUS_PATTERN.fullmatch(normalized):
        return None
    stats = _app().memory_store.get_gamification()
    xp = stats.get("xp", 0)
    level = (xp // 100) + 1
    streak = stats.get("global_streak", 0)
    habits = _app().memory_store.list_habits()
    top_habit = max(habits, key=lambda h: h.get("streak", 0)) if habits else None
    lines = [
        f"⚡ **Level {level}** ({xp} XP) — 🔥 **{streak}-day global streak**"
    ]
    if top_habit and top_habit.get("streak", 0) > 0:
        lines.append(f"- Top habit streak: **{top_habit['name']}** ({top_habit['streak']} days)")
    achievements = stats.get("achievements") or []
    if achievements:
        unlocked = [a.get("title") or a.get("name") or str(a) for a in achievements if isinstance(a, dict) and a.get("unlocked", True)]
        if unlocked:
            lines.append(f"- Achievements: {', '.join(unlocked[:5])}")
    return ("\n".join(lines), "local-gamification")


def _daily_briefing_command(prompt: str) -> tuple[str, str] | None:
    normalized = _app()._normalize_command(prompt)
    if not _BRIEFING_PATTERN.fullmatch(normalized):
        return None
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
    open_tasks = _app().memory_store.list_tasks(include_completed=False)
    all_habits = _app().memory_store.list_habits()
    pending_habits = [h for h in all_habits if today not in h["completed_dates"]]
    done_habits = [h for h in all_habits if today in h["completed_dates"]]
    reminders = _app().memory_store.list_reminders()
    stats = _app().memory_store.get_gamification()
    xp = stats.get("xp", 0)
    level = (xp // 100) + 1

    sections = [f"**Daily Briefing** (Level {level} • {xp} XP)"]
    if open_tasks:
        preview = ", ".join(f"#{t['id']} **{t['title']}** ({t['priority']})" for t in open_tasks[:3])
        sections.append(f"- **Tasks ({len(open_tasks)} pending):** {preview}")
    else:
        sections.append("- **Tasks:** All caught up! ✅")

    if all_habits:
        if pending_habits:
            h_preview = ", ".join(f"**{h['name']}**" for h in pending_habits)
            sections.append(
                f"- **Habits ({len(done_habits)}/{len(all_habits)} done today):** Still open: {h_preview}"
            )
        else:
            sections.append(f"- **Habits ({len(all_habits)}/{len(all_habits)}):** All completed today! ✅")
    else:
        sections.append("- **Habits:** None tracked yet.")

    if reminders:
        r_preview = ", ".join(f"**{r['text']}** ({_app()._format_due_date(r['run_at'])})" for r in reminders[:2])
        sections.append(f"- **Reminders ({len(reminders)} active):** {r_preview}")

    if _app().learning_schema.is_initialized():
        try:
            next_items = _app().learning_progress.next_topics(limit=1)
            if next_items:
                sections.append(
                    f"- **Next Learning Topic:** **{next_items[0]['name']}** ({next_items[0]['roadmap_name']})"
                )
        except Exception:
            _app().LOGGER.debug("Suppressed error (app.py site 4)", exc_info=True)


    return ("\n".join(sections), "local-briefing")


def _resolve_generic_delete(
    target: str, chat_id: str, name: str = ""
) -> tuple[str, str] | None:
    """Resolve 'remove <name>' across recent chat context first, then across tasks/habits/reminders/topics."""
    a = _app()
    cleaned = a._strip_delete_filler(target)
    if not cleaned:
        return None
    lowered = re.sub(r"\s+", " ", cleaned.lower())
    tech_norm = a._normalize_tech_text(lowered)

    def _matches_item(label: str) -> bool:
        lab_low = re.sub(r"\s+", " ", str(label or "").strip().lower())
        lab_tech = a._normalize_tech_text(lab_low)
        if not lab_low:
            return False
        if lowered == lab_low or lowered in lab_low:
            return True
        if tech_norm and (tech_norm == lab_tech or tech_norm in lab_tech):
            return True
        req_words = set(tech_norm.split()) if tech_norm else set(re.findall(r"[a-z0-9]+", lowered))
        cand_words = set(lab_tech.split()) if lab_tech else set(re.findall(r"[a-z0-9]+", lab_low))
        return bool(req_words and req_words.issubset(cand_words))

    # 1. Recent conversation context has highest priority so "remove the oops I just added"
    #    right after listing tasks always picks the task instead of a learning topic.
    ctx_tasks, ctx_habits = _extract_context_entities(chat_id)
    if ctx_tasks:
        ctx_t_matches = [t for t in ctx_tasks if _matches_item(t["title"])]
        if len(ctx_t_matches) == 1:
            chosen = ctx_t_matches[0]
            a.memory_store.delete_task(chosen["id"])
            remaining = len(a.memory_store.list_tasks(include_completed=False))
            return (a.assistant_tone.task_deleted(chosen["title"], remaining), "local-task-manager")
    if ctx_habits:
        ctx_h_matches = [h for h in ctx_habits if _matches_item(h["name"])]
        if len(ctx_h_matches) == 1:
            chosen = ctx_h_matches[0]
            a.memory_store.delete_habit(chosen["id"])
            return (a.assistant_tone.habit_deleted(chosen["name"]), "local-habit-manager")
    ctx_topics, _, is_recent_learning = a._extract_learning_context(chat_id)
    if is_recent_learning and ctx_topics:
        ctx_top_matches = [t for t in ctx_topics if _matches_item(t["name"])]
        if len(ctx_top_matches) == 1:
            chosen = ctx_top_matches[0]
            a.learning_progress.delete_topic(chosen["id"])
            return (f"Removed topic **{chosen['name']}**.", "local-learning")

    # 2. Global resolution across tasks, habits, and active reminders
    matched_task = None
    try:
        matched_task = a._find_task_reference(cleaned, include_completed=True)
    except ValueError:
        raise

    matched_habit = None
    try:
        matched_habit = a._find_habit(cleaned)
    except ValueError:
        raise

    matched_reminder = None
    try:
        matched_reminder = a._find_reminder(cleaned)
    except ValueError:
        matched_reminder = None

    found_domains: list[tuple[str, Any]] = []
    if matched_task is not None:
        found_domains.append(("task", matched_task))
    if matched_habit is not None:
        found_domains.append(("habit", matched_habit))
    if matched_reminder is not None:
        found_domains.append(("reminder", matched_reminder))

    if len(found_domains) > 1:
        labels = " and a ".join(kind for kind, _ in found_domains[:2])
        hints = " or ".join(f"'delete {kind} {cleaned}'" for kind, _ in found_domains[:2])
        raise ValueError(f"I found both a {labels} matching '{cleaned}'. Say {hints}.")

    if len(found_domains) == 1:
        kind, item = found_domains[0]
        if kind == "task":
            a.memory_store.delete_task(item["id"])
            remaining = len(a.memory_store.list_tasks(include_completed=False))
            return (a.assistant_tone.task_deleted(item["title"], remaining), "local-task-manager")
        if kind == "habit":
            a.memory_store.delete_habit(item["id"])
            return (a.assistant_tone.habit_deleted(item["name"]), "local-habit-manager")
        if kind == "reminder":
            a._cancel_reminder_unified(item["id"])
            return (a.assistant_tone.reminder_cancelled(item["text"], name=name), "local-scheduler")

    return None


def _handle_local_command(prompt: str, chat_id: str) -> tuple[str, str] | None:
    """Answer tasks, habits, reminders, notes, greetings, and identity locally."""
    page = _app()._parse_navigation(prompt)
    if page:
        return (f"Opening {page}.", f"local-navigate:{page}")

    briefing = _daily_briefing_command(prompt)
    if briefing is not None:
        return briefing

    proactive = _app()._proactive_coach_command(prompt, chat_id)
    if proactive is not None:
        return proactive

    xp_status = _xp_status_command(prompt)
    if xp_status is not None:
        return xp_status

    profile = _app()._profile_answer(prompt)
    if profile is not None:
        return (profile, "local-profile")

    greeting = _app()._greeting_answer(prompt)
    if greeting is not None:
        return (greeting, "local-greeting")

    intro = _app()._assistant_intro_answer(prompt)
    if intro is not None:
        return (intro, "local-identity")

    identity = _app()._identity_answer(prompt)
    if identity is not None:
        return (identity, "local-identity")

    memory_cmd = _memory_command(prompt)
    if memory_cmd is not None:
        return memory_cmd

    # Entity commands address the user by name when a name was saved.
    name = _app()._user_name(_app()._user_fact_memories())

    ctx_mutation = _resolve_contextual_mutation(prompt, chat_id, name=name)
    if ctx_mutation is not None:
        return ctx_mutation

    reminder_request = _app()._parse_chat_reminder(prompt)
    if reminder_request:
        reminder_text, run_at, recurrence = reminder_request
        _app()._validate_recurrence(recurrence)
        reminder = _app().memory_store.create_reminder(
            reminder_text, run_at, recurrence, chat_id
        )
        _app()._schedule_reminder(reminder)
        return (
            _app().assistant_tone.reminder_scheduled(
                reminder["text"],
                reminder["run_at"],
                recurrence=reminder.get("recurrence"),
                name=name,
            ),
            "local-scheduler",
        )

    clarification = _app()._reminder_clarification(prompt)
    if clarification is not None:
        return (clarification, "local-scheduler")

    reminder_reschedule = _app()._parse_reminder_reschedule(prompt)
    if reminder_reschedule:
        reference, when = reminder_reschedule
        reminder = _app()._find_reminder(reference)
        run_at = _app()._parse_reminder_time(when)
        if run_at is None:
            raise ValueError(f"I could not understand the reminder time: {when}.")
        try:
            _app().reminder_scheduler.remove_job(reminder["id"])
        except Exception:
            _app().LOGGER.debug("Suppressed error (app.py site 5)", exc_info=True)

        _app().memory_store.cancel_reminder(reminder["id"])
        updated = _app().memory_store.create_reminder(
            reminder["text"],
            run_at.isoformat(),
            reminder["recurrence"],
            reminder["chat_id"] or chat_id,
        )
        _app()._schedule_reminder(updated)
        return (
            _app().assistant_tone.reminder_moved(
                updated["text"], updated["run_at"], name=name
            ),
            "local-scheduler",
        )

    reminder_reference = _app()._parse_reminder_cancel(prompt)
    if reminder_reference is not None:
        reminder = _app()._find_reminder(reminder_reference)
        try:
            _app().reminder_scheduler.remove_job(reminder["id"])
        except Exception:
            _app().LOGGER.debug("Suppressed error (app.py site 6)", exc_info=True)

        _app().memory_store.cancel_reminder(reminder["id"])
        return (
            _app().assistant_tone.reminder_cancelled(reminder["text"], name=name),
            "local-scheduler",
        )

    if _app()._is_reminder_list_request(prompt):
        return (
            _app()._format_reminder_list(_app().memory_store.list_reminders()),
            "local-scheduler",
        )

    # Explicit learning queries (mentioning learn/study/roadmap/topic/lesson/code folder)
    # run BEFORE task/habit/generic completion fallbacks so nothing can hijack them.
    if re.search(
        r"\b(?:learn\w*|stud(?:y|ying|ied)|roadmaps?|topics?|lessons?|modules?|code\s+folder|coding\s+folder|practice\s+folder|learning\s+links?|learning\s+nudges?)\b",
        prompt,
        re.IGNORECASE,
    ):
        early_learning = _app()._learning_command(prompt, name=name, chat_id=chat_id)
        if early_learning is not None:
            return early_learning

    task_request = _app()._parse_task_create(prompt)
    if task_request:
        raw_title, priority = task_request
        title, due_at = _app()._extract_task_due_date(raw_title)
        task = _app().memory_store.create_task(title, priority, due_at=due_at)
        _app()._run_learning_hook(lambda: _app()._learning_suggest_for_task(task["id"]))
        open_count = len(_app().memory_store.list_tasks(include_completed=False))
        reply = _app().assistant_tone.task_created(
            task["title"], task["priority"], open_count, name=name
        )
        if task.get("due_at"):
            try:
                due_label = datetime.fromisoformat(task["due_at"]).strftime("%d %b %Y")
            except ValueError:
                due_label = str(task["due_at"])[:10]
            reply = f"{reply} (Due **{due_label}**.)"
        return (reply, "local-task-manager")

    if _app()._is_task_list_request(prompt):
        normalized_prompt = _app()._normalize_command(prompt).lower()
        wants_completed = bool(
            re.search(r"\b(?:completed|done|finished|closed)\b", normalized_prompt)
        ) and not re.search(
            r"\b(?:pending|open|remaining|left|incomplete|unfinished|need to complete|to complete|need to finish)\b"
            r"|\bnot\s+(?:done|completed|finished)\b",
            normalized_prompt,
        )
        tasks = [
            task for task in _app().memory_store.list_tasks(include_completed=True)
            if bool(task["completed"]) == wants_completed
        ]
        return (
            _app()._format_task_list(tasks, completed=wants_completed),
            "local-task-manager",
        )

    task_update = _app()._parse_task_update(prompt)
    if task_update:
        field, reference, value = task_update
        task = _app()._find_task_reference(reference)
        if task is None:
            raise ValueError(f"No task matched '{reference}'.")
        if field == "priority":
            updated = _app().memory_store.update_task(task["id"], priority=value)
            return (
                _app().assistant_tone.task_priority(updated["title"], updated["priority"]),
                "local-task-manager",
            )
        if field == "title":
            updated = _app().memory_store.update_task(task["id"], title=value)
            return (
                _app().assistant_tone.task_renamed(updated["title"]),
                "local-task-manager",
            )
        parsed_due_iso = _app()._parse_task_due_date(value)
        if parsed_due_iso is None:
            raise ValueError(f"I could not understand the due date: {value}.")
        updated = _app().memory_store.update_task(
            task["id"], due_at=parsed_due_iso
        )
        return (
            _app().assistant_tone.task_due(updated["title"], updated["due_at"]),
            "local-task-manager",
        )

    task_delete = _app()._parse_task_delete(prompt)
    if task_delete is not None:
        task = _app()._find_task_reference(task_delete)
        if task is None:
            raise ValueError(f"No task matched '{task_delete}'.")
        _app().memory_store.delete_task(task["id"])
        remaining = len(_app().memory_store.list_tasks(include_completed=False))
        return (
            _app().assistant_tone.task_deleted(task["title"], remaining),
            "local-task-manager",
        )

    task_reopen = _app()._parse_task_reopen(prompt)
    if task_reopen is not None:
        if task_reopen.strip().lower() in {"all tasks", "all my tasks", "all"}:
            return _app()._reopen_all_tasks()
        task = _app()._find_task_reference(task_reopen)
        if task is None:
            raise ValueError(f"No task matched '{task_reopen}'.")
        if not task["completed"]:
            return (
                f"**{task['title']}** was still open — nothing to reopen.",
                "local-task-manager",
            )
        updated = _app().memory_store.update_task(task["id"], completed=False)
        return (
            _app().assistant_tone.task_reopened(updated["title"], name=name),
            "local-task-manager",
        )

    habit_request = _app()._parse_chat_habit(prompt)
    if habit_request:
        habit_name, icon = habit_request
        habit = _app().memory_store.create_habit(habit_name, icon)
        total_habits = len(_app().memory_store.list_habits())
        return (
            _app().assistant_tone.habit_created(habit["name"], total_habits),
            "local-habit-manager",
        )

    if _app()._is_habit_list_request(prompt) and re.search(
        r"\b(?:have|having|all|my habits)\b", _app()._normalize_command(prompt).lower()
    ) and not re.search(
        r"\b(?:pending|left|remaining|incomplete)\b", prompt.lower()
    ):
        habits = _app().memory_store.list_habits()
        if not habits:
            return ("You don't have any habits set up yet.", "local-habit-manager")
        today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
        rows = "\n".join(
            f"- **{h['name']}** — streak {h['streak']}"
            f"{' ✅' if today in h['completed_dates'] else ''}"
            for h in habits
        )
        return (f"Here are your habits:\n{rows}", "local-habit-manager")

    if _app()._is_habit_list_request(prompt):
        today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
        all_habits = _app().memory_store.list_habits()
        pending_habits = [
            habit for habit in all_habits if today not in habit["completed_dates"]
        ]
        return (
            _app()._format_habit_list(all_habits, pending_habits),
            "local-habit-manager",
        )

    if _app()._is_habit_follow_up(prompt, _app().memory_store.get_messages(chat_id)):
        today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()
        habits = _app().memory_store.list_habits()
        pending_habits = [
            habit for habit in habits if today not in habit["completed_dates"]
        ]
        if not habits:
            response = (
                "I don't see any habits set up yet. "
                "What would you like your first one to be?"
            )
        elif not pending_habits:
            response = "You're all set for today. What else would you like to tackle?"
        else:
            response = (
                f"Let's take them one at a time. **{pending_habits[0]['name']}** "
                "feels like a good place to start."
            )
        return (response, "local-habit-manager")

    habit_rename = _app()._parse_habit_rename(prompt)
    if habit_rename:
        reference, new_name = habit_rename
        habit = _app()._find_habit(reference)
        if habit is None:
            raise ValueError(f"No habit matched '{reference}'.")
        updated = _app().memory_store.update_habit(habit["id"], name=new_name)
        return (_app().assistant_tone.habit_renamed(updated["name"]), "local-habit-manager")

    habit_delete = _app()._parse_habit_delete(prompt)
    if habit_delete is not None:
        habit = _app()._find_habit(habit_delete)
        if habit is None:
            raise ValueError(f"No habit matched '{habit_delete}'.")
        _app().memory_store.delete_habit(habit["id"])
        return (_app().assistant_tone.habit_deleted(habit["name"]), "local-habit-manager")

    habit_uncomplete = _app()._parse_habit_uncomplete(prompt)
    if habit_uncomplete is not None:
        if habit_uncomplete.strip().lower() in {"all habits", "all my habits", "all"}:
            return _app()._uncomplete_all_habits()
        habit = _app()._find_habit(habit_uncomplete)
        if habit is None:
            raise ValueError(f"No habit matched '{habit_uncomplete}'.")
        return (_app()._uncomplete_habit(habit, name=name), "local-habit-manager")

    habit_completion = _app()._parse_habit_completion(prompt)
    if habit_completion is not None:
        contextual = _resolve_contextual_completion(habit_completion, chat_id, name=name)
        if contextual is not None:
            return contextual
        habit = _app()._find_habit(habit_completion)
        if habit is None:
            raise ValueError(f"No habit matched '{habit_completion}'.")
        return (_app()._complete_habit(habit, name=name), "local-habit-manager")

    task_completion = _app()._parse_task_completion(prompt)
    if task_completion is not None:
        contextual = _resolve_contextual_completion(task_completion, chat_id, name=name)
        if contextual is not None:
            return contextual
        task = _app()._find_task_reference(task_completion)
        if task is None:
            raise ValueError(f"No task matched '{task_completion}'.")
        return (_app()._complete_task(task, name=name), "local-task-manager")

    completion_target = _app()._parse_completion_target(prompt)
    if completion_target is not None:
        contextual = _resolve_contextual_completion(completion_target, chat_id, name=name)
        if contextual is not None:
            return contextual
        pending_task = _app()._find_task_reference(
            completion_target, include_completed=False
        )
        habit = _app()._find_habit(completion_target)
        if pending_task and habit:
            raise ValueError(
                f"I found both a task and a habit called '{completion_target}'. "
                f"Say 'complete task {completion_target}' or "
                f"'complete habit {completion_target}'."
            )
        if pending_task:
            return (_app()._complete_task(pending_task, name=name), "local-task-manager")
        if habit:
            return (_app()._complete_habit(habit, name=name), "local-habit-manager")
        completed_task = _app()._find_task_reference(completion_target)
        if completed_task is not None:
            return (_app()._complete_task(completed_task, name=name), "local-task-manager")
        # No task or habit matched — let learning commands have a look.

    learning_command = _app()._learning_command(prompt, name=name, chat_id=chat_id)
    if learning_command is not None:
        return learning_command

    if completion_target is not None and _app().learning_schema.is_initialized():
        matched_topic = _app().learning_progress.find_topic(
            _app()._clean_topic_reference(completion_target)
        )
        if matched_topic is not None:
            return _app()._learning_complete_reply(
                completion_target, name=name, chat_id=chat_id
            )

    generic_delete = _app()._parse_generic_delete(prompt)
    if generic_delete is not None:
        resolved_del = _resolve_generic_delete(generic_delete, chat_id, name=name)
        if resolved_del is not None:
            return resolved_del

    web_query = _app()._parse_web_search_query(prompt)
    if web_query:
        return _app()._web_search_reply(web_query)

    return None


