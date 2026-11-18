"""Reminder scheduling, parsing, formatting, and alert delivery."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import dateparser
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

def _app():
    import app

    return app


def _push_reminder_alert(reminder: dict[str, Any], content: str) -> None:
    if _app().MAIN_LOOP is None or not _app().ws_manager.active:
        return
    async def _go() -> None:
        try:
            audio_url = await _app().generate_tts_url(content)
            await _app().ws_manager.broadcast({
                "type": "reminder_alert",
                "reminder_id": reminder["id"],
                "text": content,
                "audio_url": audio_url,
                "reminders": _app()._live_reminders(),
                "chat_id": reminder.get("chat_id"),
            })
        except Exception as exc:
            logging.getLogger("orbit007").warning("Failed in _push_reminder_alert: %s", exc)
    try:
        asyncio.run_coroutine_threadsafe(_go(), _app().MAIN_LOOP)
    except Exception as exc:
        logging.getLogger("orbit007").warning("Failed to schedule _push_reminder_alert: %s", exc)


def _run_reminder(reminder_id: str) -> None:
    reminder = _app().memory_store.get_reminder(reminder_id)
    if not reminder or not reminder["active"] or not reminder["chat_id"]:
        return
    # Written locally so web and Discord both get the same warm, instant nudge.
    content = _app().assistant_tone.reminder_fired(
        reminder["text"], name=_app()._user_name(_app()._user_fact_memories())
    )
    _app().memory_store.add_notification(reminder["chat_id"], reminder_id, content)
    try:
        _app()._push_reminder_alert(reminder, content)
    except Exception as exc:
        logging.getLogger("orbit007").warning("Push reminder alert error: %s", exc)
    if not reminder.get("recurrence"):
        _app().memory_store.cancel_reminder(reminder_id)


def _recommend_next_task(
    chat_id: str, completed_task_title: str | None = None
) -> None:
    """Use the LLM to recommend the next task, delivered as a notification."""
    if not chat_id:
        return
    tasks = _app().memory_store.list_tasks(include_completed=False)
    current_time = datetime.now(_app().LOCAL_TIMEZONE).strftime("%d %B %Y, %I:%M %p")

    if not tasks:
        if completed_task_title:
            llm_prompt = (
                "Write one short, celebratory message as S.P.I.D.E.Y, a warm personal "
                "assistant. The user just finished their last remaining task. "
                "Congratulate them and suggest they relax or plan new goals. "
                "Do not mention AI, prompts, or instructions. Return only the "
                "message text, no quotes.\n"
                f"Completed task: {completed_task_title}\n"
                f"Current time: {current_time}"
            )
        else:
            return
    else:
        task_list = "\n".join(
            f"- [{t['priority']}] {t['title']}" for t in tasks[:5]
        )
        if completed_task_title:
            llm_prompt = (
                "Write one short, encouraging message as S.P.I.D.E.Y, a warm personal "
                "assistant. The user just completed a task. Acknowledge it briefly, "
                "then recommend the next task they should focus on — mention its "
                "name and priority. Be specific, motivating, and concise. "
                "Do not mention AI, prompts, or instructions. Return only the "
                "message text, no quotes.\n"
                f"Just completed: {completed_task_title}\n"
                f"Remaining tasks (highest priority first):\n{task_list}\n"
                f"Current time: {current_time}"
            )
        else:
            llm_prompt = (
                "Write one short, friendly message as S.P.I.D.E.Y, a warm personal "
                "assistant. The user has pending tasks. Gently suggest the "
                "top-priority task they should focus on — mention its name and "
                "priority level. Be motivating and brief. "
                "Do not mention AI, prompts, or instructions. Return only the "
                "message text, no quotes.\n"
                f"Pending tasks (highest priority first):\n{task_list}\n"
                f"Current time: {current_time}"
            )

    try:
        content = _app().generate_response(llm_prompt, 64).strip()
        if not content:
            raise ValueError("Empty task recommendation.")
    except Exception as error:
        _app().LOGGER.warning("Task recommendation generation failed: %s", error)
        if not tasks:
            content = (
                f"You've completed \"{completed_task_title}\" and cleared all "
                f"your tasks. Well done!"
            )
        else:
            next_task = tasks[0]
            if completed_task_title:
                content = (
                    f"Done with \"{completed_task_title}\"! "
                    f"Next up: {next_task['title']} "
                    f"({next_task['priority']} priority)."
                )
            else:
                content = (
                    f"Your top task right now is: {next_task['title']} "
                    f"({next_task['priority']} priority). Ready when you are!"
                )

    coach_id = f"task-coach-{uuid.uuid4()}"
    _app().memory_store.add_notification(chat_id, coach_id, content)


def _schedule_reminder(reminder: dict[str, Any]) -> None:
    run_at: datetime | None = None
    try:
        run_at = datetime.fromisoformat(reminder["run_at"])
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=_app().LOCAL_TIMEZONE)
    except (TypeError, ValueError):
        run_at = dateparser.parse(
            reminder["run_at"],
            settings={"RETURN_AS_TIMEZONE_AWARE": True, "TIMEZONE": _app().LOCAL_TIMEZONE_NAME},
        )
    if run_at is None:
        _app().LOGGER.warning("Skipping reminder %s: invalid run time.", reminder["id"])
        return
    recurrence = (reminder.get("recurrence") or "").lower().strip()
    if recurrence:
        match = re.fullmatch(
            r"every\s+(?:(\d+)\s+)?(minute|hour|day|week)s?", recurrence
        )
        if not match:
            raise ValueError(
                "Recurrence must look like 'every day' or 'every 2 hours'."
            )
        amount, unit = int(match.group(1) or 1), match.group(2)
        _app().reminder_scheduler.add_job(
            _app()._run_reminder,
            IntervalTrigger(**{f"{unit}s": amount}, start_date=run_at, timezone=_app().LOCAL_TIMEZONE),
            args=[reminder["id"]],
            id=reminder["id"],
            replace_existing=True,
        )
        return
    now = datetime.now(run_at.tzinfo)
    if run_at <= now:
        if now - run_at > timedelta(minutes=30):
            _app().memory_store.cancel_reminder(reminder["id"])
            return
        _app().LOGGER.info("Delivering missed reminder %s.", reminder["id"])
        run_at = now + timedelta(seconds=5)
    _app().reminder_scheduler.add_job(
        _app()._run_reminder,
        DateTrigger(run_date=run_at, timezone=_app().LOCAL_TIMEZONE),
        args=[reminder["id"]],
        id=reminder["id"],
        replace_existing=True,
    )


def _validate_recurrence(recurrence: str | None) -> None:
    if recurrence is None or not recurrence.strip():
        return
    if not re.fullmatch(
        r"every\s+(?:(\d+)\s+)?(minute|hour|day|week)s?",
        recurrence.strip().lower(),
    ):
        raise ValueError(
            "Recurrence must look like 'every day' or 'every 2 hours'."
        )


def _restore_reminders(provider: str = "local") -> None:
    """Schedule saved reminders for one chat provider."""
    for reminder in _app().memory_store.list_reminders():
        session = _app().memory_store.get_external_session(reminder["chat_id"])
        chat_provider = session["provider"] if session else "local"
        if chat_provider != provider:
            continue
        try:
            _app()._schedule_reminder(reminder)
        except Exception as error:
            _app().LOGGER.warning("Skipping reminder %s: %s", reminder["id"], error)
    if not _app().reminder_scheduler.running:
        _app().reminder_scheduler.start()


DEFAULT_CHAT_ID = "default"


def _ensure_chat_exists(chat_id: str) -> None:
    if not _app().memory_store.chat_exists(chat_id):
        now_iso = datetime.now(timezone.utc).isoformat()
        with _app().memory_store.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (chat_id, "Default Chat", now_iso, now_iso),
            )


def _reminder_view(r: dict[str, Any]) -> dict[str, Any]:
    """MemoryStore row -> the shape the frontend already expects (legacy keys kept)."""
    return {
        "id": r["id"],
        "title": r["text"],
        "text": r["text"],
        "remind_at": r["run_at"],
        "run_at": r["run_at"],
        "recurrence": r.get("recurrence"),
        "completed": 0 if r.get("active", 1) else 1,
        "chat_id": r.get("chat_id"),
    }


def _live_reminders() -> list[dict[str, Any]]:
    return [_app()._reminder_view(r) for r in _app().memory_store.list_reminders()]


def _create_reminder_unified(
    title: str,
    when: str,
    recurrence: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    _app()._validate_recurrence(recurrence)
    parsed = _app()._parse_reminder_time(when)
    if parsed is None:
        raise ValueError(f"I could not understand the reminder time: {when!r}.")
    target_chat = chat_id or _app().DEFAULT_CHAT_ID
    _app()._ensure_chat_exists(target_chat)
    row = _app().memory_store.create_reminder(
        title, parsed.isoformat(), recurrence, target_chat
    )
    _app()._schedule_reminder(row)
    return _app()._reminder_view(row)


def _cancel_reminder_unified(reminder_id: str) -> bool:
    ok = _app().memory_store.cancel_reminder(reminder_id)
    try:
        _app().reminder_scheduler.remove_job(reminder_id)
    except Exception:  # job already fired or never existed
        pass
    return ok





def _parse_reminder_time(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=_app().LOCAL_TIMEZONE)
        return dt.astimezone(_app().LOCAL_TIMEZONE)
    except (ValueError, TypeError):
        pass

    rel_match = re.fullmatch(
        r"in\s+(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)",
        value.strip(),
        re.IGNORECASE,
    )
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        now = datetime.now(_app().LOCAL_TIMEZONE)
        if unit.startswith("sec"):
            return now + timedelta(seconds=amount)
        if unit.startswith("min"):
            return now + timedelta(minutes=amount)
        if unit.startswith("h"):
            return now + timedelta(hours=amount)
        if unit.startswith("d"):
            return now + timedelta(days=amount)
        if unit.startswith("w"):
            return now + timedelta(weeks=amount)

    day_part_times = {
        "morning": (6, 30),
        "afternoon": (12, 30),
        "evening": (18, 30),
        "night": (21, 0),
    }
    day_part_match = re.search(
        r"\b(morning|afternoon|evening|night)\b", value, re.IGNORECASE
    )
    settings = {
        "TIMEZONE": _app().LOCAL_TIMEZONE_NAME,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
    }
    if not day_part_match:
        parsed_base = dateparser.parse(value, settings=settings)
        if parsed_base is None:
            return None
        now = datetime.now(parsed_base.tzinfo)
        has_explicit_date = bool(
            re.search(
                r"\b(tomorrow|tmrw|today|tonight|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}[/-]\d{1,2})\b",
                value,
                re.IGNORECASE,
            )
        )
        if not has_explicit_date and parsed_base <= now:
            parsed_base += timedelta(days=1)
        return parsed_base

    day_part = day_part_match.group(1).lower()
    date_text = re.sub(
        r"\b(morning|afternoon|evening|night)\b", "", value,
        count=1, flags=re.IGNORECASE,
    ).strip()
    if date_text.lower() == "next":
        date_text = "tomorrow"
    if not date_text:
        date_text = "today"
    settings_with_future = {**settings, "PREFER_DATES_FROM": "future"}
    parsed_date = dateparser.parse(date_text, settings=settings_with_future)
    if parsed_date is None:
        return None
    hour, minute = day_part_times[day_part]
    parsed = parsed_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if parsed <= datetime.now(parsed.tzinfo) and date_text == "today":
        parsed += timedelta(days=1)
    return parsed


_REMINDER_CREATE_PATTERN = (
    r"(?:set|create|add|make|schedule)\s+"
    r"(?:(?:a|an|another|one\s+more|new)\s+)?reminder"
)


def _reminder_result(
    text: str, when: str, recurrence: str | None, *, relative: bool = False
) -> tuple[str, str, str | None]:
    """Resolve the time part of a reminder request, or explain what is unclear."""
    parsed = _app()._parse_reminder_time(f"in {when}" if relative else when)
    if parsed is None:
        raise ValueError(f"I could not understand the reminder time: {when}.")
    return text.strip(), parsed.isoformat(), recurrence.strip() if recurrence else None


def _parse_chat_reminder(prompt: str) -> tuple[str, str, str | None] | None:
    normalized_prompt = _app()._normalize_command(prompt)
    create = _REMINDER_CREATE_PATTERN

    # "remind me in 10 minutes to stretch"
    match = re.fullmatch(
        r"remind me in (.+?) to (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "set another reminder in 10 minutes for tea"
    match = re.fullmatch(
        rf"{create} in "
        r"(\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?))\s+"
        r"(?:(?:for|to)\s+)?(.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "set reminder 10 minutes for tea"
    match = re.fullmatch(
        rf"{create}\s+"
        r"(\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?))"
        r"\s+(?:for|to)\s+(.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "remind me 20 minutes to stretch"
    match = re.fullmatch(
        r"remind me (.+?) to (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence)

    # "remind me to stretch in 20 minutes"
    match = re.fullmatch(
        r"remind me to (.+?) in (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        text, when, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "set a reminder in 20 minutes for tea"
    match = re.fullmatch(
        rf"{create} in (.+?) (?:for|to) (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "add a reminder for water in 30 minutes"
    match = re.fullmatch(
        rf"{create} (?:for|about) (.+?) in (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        text, when, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence, relative=True)

    # "remind me to sleep at 11pm" / "remind me about dinner at 8pm"
    match = re.fullmatch(
        r"remind me (?:to|about) (.+?) at (.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        text, when, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence)

    # "set another reminder at 23:10 for sleeping" — time first, then topic.
    match = re.fullmatch(
        rf"{create} (?:at|on|for|by) (.+?) (?:for|to) "
        r"(.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence)

    # "set a reminder for sleeping at 11pm" — topic first, then time.
    match = re.fullmatch(
        rf"{create} (?:for|about) (.+?) (?:at|by) "
        r"(.+?)(?:,\s*(every .+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        text, when, recurrence = match.groups()
        return _app()._reminder_result(text, when, recurrence)

    # "set a timer for 10 minutes [for pasta]" / "timer for 5 mins"
    match = re.fullmatch(
        r"(?:(?:set|start|create|add)\s+(?:a\s+)?)?timer\s+(?:for\s+)?"
        r"(\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?))"
        r"(?:\s+(?:for|to|about)\s+(.+))?",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text = match.groups()
        label = text.strip() if text else f"Timer ({when.strip()})"
        return _app()._reminder_result(label, when, None, relative=True)

    # "set an alarm for 7am [to wake up]" / "wake me up at 6:30am"
    match = re.fullmatch(
        r"(?:(?:set|create|add)\s+(?:an?\s+)?alarm\s+(?:for|at)\s+(.+?)"
        r"(?:\s+(?:for|to|about)\s+(.+))?"
        r"|wake\s+me(?:\s+up)?\s+(?:at|in)\s+(.+?)(?:\s+to\s+(.+))?)",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        g1, g2, g3, g4 = match.groups()
        when = (g1 or g3).strip()
        label = (g2 or g4 or ("Wake up" if g3 else "Alarm")).strip()
        is_rel = bool(re.match(r"^\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", when, re.IGNORECASE))
        return _app()._reminder_result(label, when, None, relative=is_rel)

    # "ping me in 15 minutes to check the build"
    match = re.fullmatch(
        r"(?:ping|notify|alert|nudge)\s+me\s+in\s+(.+?)\s+(?:to|about|for)\s+(.+)",
        normalized_prompt,
        re.IGNORECASE,
    )
    if match:
        when, text = match.groups()
        return _app()._reminder_result(text, when, None, relative=True)

    return None



def _reminder_clarification(prompt: str) -> str | None:
    """Ask for the missing detail instead of letting the LLM invent a reminder."""
    normalized = _app()._normalize_command(prompt)
    if re.search(r"^remind\s+me\s+(?:what|why|who|how|where|when|which|whether|if)\b", normalized, re.IGNORECASE):
        return None
    create_pattern = rf"^(?:{_REMINDER_CREATE_PATTERN}|remind\s+me)\b"
    if not re.match(create_pattern, normalized, re.IGNORECASE):
        return None
    has_time = bool(
        re.search(
            r"\b(?:in\s+\d|at\s+\d|tomorrow|tonight|today|noon|midnight|"
            r"next\s+\w+|morning|afternoon|evening|night|every\s+\w+|"
            r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
            r"\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?))\b",
            normalized,
            re.IGNORECASE,
        )
    )
    if has_time:
        return "What should I remind you about?"
    topic = re.sub(
        rf"^(?:{_REMINDER_CREATE_PATTERN}|remind\s+me)\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if not topic:
        return "What should I remind you about, and when?"
    if re.match(r"^(?:to|about)\s+", topic, re.IGNORECASE):
        return f"When should I remind you {topic}?"
    topic = re.sub(r"^for\s+", "", topic, flags=re.IGNORECASE).strip()
    return f"When should I remind you about {topic}?"



def _parse_reminder_cancel(prompt: str) -> str | None:
    match = re.fullmatch(
        r"(?:cancel|delete|remove|stop|forget)\s+(?:(?:the|my)\s+)?reminder\s+"
        r"(?:to\s+|for\s+|about\s+)?(.+)",
        _app()._normalize_command(prompt),
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _parse_reminder_reschedule(prompt: str) -> tuple[str, str] | None:
    """Return (reference, when) for 'reschedule reminder X to Y'."""
    match = re.fullmatch(
        r"(?:reschedule|move|postpone|delay|change|update)\s+"
        r"(?:(?:the|my)\s+)?reminder\s+(.+?)\s+to\s+(.+)",
        _app()._normalize_command(prompt),
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _find_reminder(reference: str) -> dict[str, Any]:
    """Resolve a unique active reminder by a substring of its text."""
    normalized = re.sub(r"\s+", " ", reference.strip().lower())
    if not normalized:
        raise ValueError("Tell me which reminder you mean.")
    matches = [
        reminder for reminder in _app().memory_store.list_reminders()
        if normalized in reminder["text"].strip().lower()
    ]
    if not matches:
        raise ValueError(f"No active reminder matched '{reference}'.")
    if len(matches) > 1:
        options = "\n".join(f"- {reminder['text']}" for reminder in matches)
        raise ValueError(
            f"More than one reminder matches '{reference}':\n{options}"
        )
    return matches[0]


def _is_reminder_list_request(prompt: str) -> bool:
    normalized = _app()._normalize_command(prompt).lower()
    if not re.search(r"\b(?:reminders?|alarms?|timers?)\b", normalized):
        return False
    if _app()._is_advice_question(normalized):
        return False
    if re.match(
        r"^(?:cancel|delete|remove|stop|forget|set|create|add|remind|"
        r"reschedule|move|postpone|delay|change|update)\b",
        normalized,
    ):
        return False
    if re.fullmatch(
        r"(?:(?:my|the|all|active|upcoming|pending|current)\s+)*"
        r"(?:reminders?|alarms?|timers?)(?:\s+list)?",
        normalized,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:show|list|check|what|which|tell me|do i have|any|upcoming|active|pending)\b",
            normalized,
        )
    )


def _format_reminder_list(reminders: list[dict[str, Any]]) -> str:
    if not reminders:
        return "You don't have any active reminders right now."
    lines = []
    for reminder in reminders:
        recurrence = reminder.get("recurrence")
        suffix = f", repeating {recurrence}" if recurrence else ""
        lines.append(
            f"- **{reminder['text']}** at "
            f"{_app()._format_due_date(reminder['run_at'])}{suffix}"
        )
    return "Here's what I'm keeping track of:\n" + "\n".join(lines)



def _format_due_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return value


def _notify_completion(chat_id: str, prefix: str, content: str) -> None:
    """Drop a completion follow-up into the conversation the web panel polls."""
    if not chat_id or not content:
        return
    _app().memory_store.add_notification(chat_id, f"{prefix}-{uuid.uuid4()}", content)


