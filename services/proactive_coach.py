"""Proactive coach: automatic suggestions and regular check-ins for tasks, habits, and learning."""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any

from apscheduler.triggers.interval import IntervalTrigger
from voice.text_clean import summarize_for_speech

PROACTIVE_COACH_JOB_ID = "spidey-proactive-coach"
DEFAULT_COACH_INTERVAL_MINUTES = int(os.environ.get("ORBIT_COACH_INTERVAL_MINUTES", "45").strip() or "45")
QUIET_HOURS_START = int(os.environ.get("ORBIT_QUIET_HOURS_START", "23").strip() or "23")  # 11:00 PM
QUIET_HOURS_END = int(os.environ.get("ORBIT_QUIET_HOURS_END", "7").strip() or "7")        # 7:00 AM
EVENING_WRAPUP_HOUR = int(os.environ.get("ORBIT_EVENING_WRAPUP_HOUR", "20").strip() or "20")  # 8:00 PM


def _app():
    import app

    return app


def is_quiet_hours(now: datetime | None = None) -> bool:
    """Return True during late-night quiet hours (default 11:00 PM – 7:00 AM local time)."""
    a = _app()
    now_local = (now or datetime.now(a.LOCAL_TIMEZONE)).astimezone(a.LOCAL_TIMEZONE)
    hour = now_local.hour
    if QUIET_HOURS_START > QUIET_HOURS_END:
        return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END
    return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def is_evening_wrapup(now: datetime | None = None) -> bool:
    """Return True during the evening wind-down window (default 8:00 PM – 11:00 PM)."""
    a = _app()
    now_local = (now or datetime.now(a.LOCAL_TIMEZONE)).astimezone(a.LOCAL_TIMEZONE)
    hour = now_local.hour
    return EVENING_WRAPUP_HOUR <= hour < QUIET_HOURS_START


def get_proactive_snapshot() -> dict[str, Any]:
    """Gather pending tasks, today's unchecked habits, and active/next learning topics."""
    a = _app()
    today_iso = datetime.now(a.LOCAL_TIMEZONE).date().isoformat()

    pending_tasks = a.memory_store.list_tasks(include_completed=False)
    all_habits = a.memory_store.list_habits()
    pending_habits = [h for h in all_habits if today_iso not in (h.get("completed_dates") or [])]

    learning_topics: list[dict[str, Any]] = []
    learning_overview: dict[str, Any] = {}
    if a.learning_schema.is_initialized():
        try:
            learning_topics = a.learning_progress.next_topics(limit=5)
            learning_overview = a.learning_progress.overall_progress()
        except Exception as err:
            a.LOGGER.debug("Proactive snapshot learning lookup skipped: %s", err)

    return {
        "today": today_iso,
        "pending_tasks": pending_tasks,
        "pending_habits": pending_habits,
        "all_habits_count": len(all_habits),
        "learning_topics": learning_topics,
        "learning_overview": learning_overview,
    }


def _last_coach_category(chat_id: str) -> str | None:
    """Inspect the most recent task-coach-* notification key to rotate categories."""
    a = _app()
    try:
        with a.memory_store.connect() as conn:
            row = conn.execute(
                "SELECT reminder_id FROM notifications "
                "WHERE chat_id = ? AND reminder_id LIKE 'task-coach-%' "
                "ORDER BY id DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
        if not row:
            return None
        rem_id = str(row["reminder_id"] or "")
        for cat in ("task", "habit", "learning", "combined"):
            if rem_id.startswith(f"task-coach-{cat}-"):
                return cat
    except Exception:
        pass
    return None


def build_proactive_checkin(
    chat_id: str | None = None,
    preferred_category: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build a motivating check-in or suggestion across tasks, habits, and learning."""
    a = _app()
    snap = get_proactive_snapshot()
    pending_tasks = snap["pending_tasks"]
    pending_habits = snap["pending_habits"]
    learning_topics = snap["learning_topics"]

    if not pending_tasks and not pending_habits and not learning_topics:
        return None

    name = a._user_name(a._user_fact_memories())
    name_part = f" {name}" if name else ""
    evening_mode = is_evening_wrapup(now)
    late_night_mode = is_quiet_hours(now)

    available_categories: list[str] = []
    if pending_tasks:
        available_categories.append("task")
    if pending_habits:
        available_categories.append("habit")
    if learning_topics:
        available_categories.append("learning")

    # Determine which category to highlight
    if preferred_category in ("task", "habit", "learning", "combined"):
        if preferred_category == "combined" or preferred_category in available_categories:
            category = preferred_category
        else:
            category = available_categories[0]
    elif evening_mode and "habit" in available_categories and _last_coach_category(chat_id or "") != "habit":
        # In the evening wind-down window (8 PM - 11 PM), prioritize unchecked daily habits before midnight
        category = "habit"
    else:
        last_cat = _last_coach_category(chat_id) if chat_id else None
        rotation = ["task", "habit", "learning", "combined"]
        if len(available_categories) == 1:
            category = available_categories[0]
        elif last_cat in rotation:
            start_idx = (rotation.index(last_cat) + 1) % len(rotation)
            chosen = None
            for offset in range(len(rotation)):
                cand = rotation[(start_idx + offset) % len(rotation)]
                if cand == "combined" or cand in available_categories:
                    chosen = cand
                    break
            category = chosen or available_categories[0]
        else:
            category = available_categories[0]

    top_task = pending_tasks[0] if pending_tasks else None
    top_habit = pending_habits[0] if pending_habits else None
    top_topic = learning_topics[0] if learning_topics else None

    target_type: str | None = None
    target_title: str | None = None

    if category == "task" and top_task:
        target_type = "task"
        target_title = top_task["title"]
        priority = top_task.get("priority", "medium")
        due_at = top_task.get("due_at")
        if evening_mode or late_night_mode:
            message = (
                f"Evening wrap-up{name_part}: did you finish **{top_task['title']}** ({priority} priority) today? "
                f"Say 'mark it done' to log it before bed, or we can roll it to tomorrow."
            )
        elif due_at:
            due_str = a._format_due_date(due_at)
            message = (
                f"Quick check-in{name_part}: your {priority}-priority task "
                f"**{top_task['title']}** (due {due_str}) is still open. "
                f"Have you completed it yet, or should we knock it out now?"
            )
        else:
            extra = f" (plus {len(pending_tasks) - 1} more open)" if len(pending_tasks) > 1 else ""
            message = (
                f"Hey{name_part}, task check-in — have you finished "
                f"**{top_task['title']}** ({priority} priority){extra} yet? "
                f"Tell me 'mark it done' if you finished it, or let's tackle it next."
            )

    elif category == "habit" and top_habit:
        target_type = "habit"
        target_title = top_habit["name"]
        if evening_mode or late_night_mode:
            other_note = (
                f" (and {len(pending_habits) - 1} other habit{'s' if len(pending_habits) - 1 != 1 else ''})"
                if len(pending_habits) > 1
                else ""
            )
            message = (
                f"Night habit wrap-up{name_part}: before the day ends, did you complete "
                f"**{top_habit['name']}**{other_note}? Let's check it off so your streak stays alive!"
            )
        elif len(pending_habits) == 1:
            message = (
                f"Daily habit check-in{name_part}: **{top_habit['name']}** is your "
                f"last unchecked habit for today. Did you get a chance to complete it yet?"
            )
        else:
            other_count = len(pending_habits) - 1
            message = (
                f"Habit push{name_part}: **{top_habit['name']}** and {other_count} other "
                f"daily habit{'s' if other_count != 1 else ''} are still unchecked today. "
                f"Have you done **{top_habit['name']}** yet?"
            )

    elif category == "learning" and top_topic:
        target_type = "learning"
        target_title = top_topic["name"]
        roadmap_name = top_topic.get("roadmap_name", "your roadmap")
        status = top_topic.get("status", "not_started")
        if evening_mode or late_night_mode:
            message = (
                f"Evening study check{name_part}: did you make progress on "
                f"**{top_topic['name']}** in **{roadmap_name}** today? "
                f"Let me know if we can mark it complete before you rest."
            )
        elif status == "in_progress":
            message = (
                f"Learning check-in{name_part}: you're currently working on "
                f"**{top_topic['name']}** in **{roadmap_name}**. "
                f"Did you finish it today, or want to keep pushing on it?"
            )
        else:
            message = (
                f"Study push{name_part}: **{top_topic['name']}** in **{roadmap_name}** "
                f"is queued up next. Want to start it now, or have you already covered it?"
            )

    else:
        category = "combined"
        bullets: list[str] = []
        if top_task:
            target_type = target_type or "task"
            target_title = target_title or top_task["title"]
            bullets.append(
                f"- Top Task: **{top_task['title']}** — {top_task.get('priority', 'medium')} priority ({len(pending_tasks)} open)"
            )
        if top_habit:
            target_type = target_type or "habit"
            target_title = target_title or top_habit["name"]
            bullets.append(
                f"- Daily Habit: **{top_habit['name']}** — {len(pending_habits)} left today"
            )
        if top_topic:
            target_type = target_type or "learning"
            target_title = target_title or top_topic["name"]
            bullets.append(
                f"- Learning Next: **{top_topic['name']}** — {top_topic.get('roadmap_name', 'Roadmap')}"
            )
        if late_night_mode:
            lead = f"It's late{name_part} — here's a quick wrap-up before you get some rest:"
            closing = "Did you finish any of these today so I can mark them done before you sleep?"
        elif evening_mode:
            lead = f"Evening wrap-up{name_part} — here's what's still open for today:"
            closing = "Have you completed any of these today, or want to knock out your daily habit before bed?"
        else:
            lead = f"Here's your quick accountability check-in{name_part}:"
            closing = "Have you completed any of these yet, or which one are we tackling right now?"

        message = f"{lead}\n\n" + "\n".join(bullets) + f"\n\n{closing}"

    return {
        "category": category,
        "message": message,
        "spoken_response": summarize_for_speech(message),
        "target_type": target_type,
        "target_title": target_title,
        "pending_counts": {
            "tasks": len(pending_tasks),
            "habits": len(pending_habits),
            "learning": len(learning_topics),
        },
        "suggestions": {
            "top_task": top_task,
            "top_habit": top_habit,
            "top_learning": top_topic,
        },
    }


def deliver_proactive_checkin(
    chat_id: str | None = None,
    *,
    force: bool = False,
    cooldown_minutes: int = 30,
    preferred_category: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deliver a proactive check-in notification (and WebSocket alert) if due."""
    a = _app()
    target_chat = chat_id or a.DEFAULT_CHAT_ID
    a._ensure_chat_exists(target_chat)

    # Silence automatic background check-ins during late-night quiet hours (11 PM - 7 AM)
    if not force and is_quiet_hours(now):
        return {
            "nudge": False,
            "reason": "quiet_hours",
            "chat_id": target_chat,
        }

    if not force and a.memory_store.has_recent_coach_notification(target_chat, minutes=cooldown_minutes):
        return {
            "nudge": False,
            "reason": "already_nudged_recently",
            "chat_id": target_chat,
        }

    checkin = build_proactive_checkin(target_chat, preferred_category=preferred_category, now=now)
    if checkin is None:
        return {
            "nudge": False,
            "reason": "nothing_pending",
            "chat_id": target_chat,
        }

    notif_key = f"task-coach-{checkin['category']}-{uuid.uuid4()}"
    a.memory_store.add_notification(target_chat, notif_key, checkin["message"])

    try:
        a._push_reminder_alert(
            {"id": notif_key, "chat_id": target_chat, "text": checkin["message"]},
            checkin["message"],
        )
    except Exception as exc:
        logging.getLogger("orbit007").debug("Proactive WS alert skipped: %s", exc)

    return {
        "nudge": True,
        "chat_id": target_chat,
        "notification_key": notif_key,
        **checkin,
    }


def run_scheduled_proactive_checkins(provider: str = "local") -> int:
    """Periodic background job that checks in on active chats with pending items."""
    a = _app()
    try:
        if provider == "discord":
            chat_ids = [c["id"] for c in a.memory_store.list_external_chats("discord")]
        else:
            chat_ids = a.memory_store.list_local_chat_ids()
            if not chat_ids:
                a._ensure_chat_exists(a.DEFAULT_CHAT_ID)
                chat_ids = [a.DEFAULT_CHAT_ID]

        sent = 0
        for cid in chat_ids[:3]:  # Cap to most recent active chats
            res = deliver_proactive_checkin(
                cid,
                force=False,
                cooldown_minutes=max(15, DEFAULT_COACH_INTERVAL_MINUTES - 5),
            )
            if res.get("nudge"):
                sent += 1
        return sent
    except Exception as err:
        a.LOGGER.debug("Scheduled proactive check-in skipped: %s", err)
        return 0


def schedule_proactive_coach(provider: str = "local") -> None:
    """Register the recurring proactive coach job on APScheduler."""
    a = _app()
    if DEFAULT_COACH_INTERVAL_MINUTES <= 0:
        return
    try:
        if not a.reminder_scheduler.running:
            a.reminder_scheduler.start()
        job_id = PROACTIVE_COACH_JOB_ID if provider == "local" else f"{PROACTIVE_COACH_JOB_ID}-{provider}"
        a.reminder_scheduler.add_job(
            run_scheduled_proactive_checkins,
            IntervalTrigger(minutes=DEFAULT_COACH_INTERVAL_MINUTES, timezone=a.LOCAL_TIMEZONE),
            args=[provider],
            id=job_id,
            replace_existing=True,
        )
    except Exception as err:
        a.LOGGER.debug("Proactive coach schedule skipped: %s", err)


_PROACTIVE_COMMAND_PATTERN = re.compile(
    r"^(?:(?:hey|hi|ok|okay)\s+)?"
    r"(?:"
    r"push\s+me(?:\s+to\s+do\s+something)?"
    r"|motivate\s+me"
    r"|check\s+(?:in\s+)?on\s+me"
    r"|nudge\s+me"
    r"|what\s+should\s+i\s+(?:do|work\s+on|focus\s+on|tackle)(?:\s+(?:now|next|today))?"
    r"|suggest\s+something(?:\s+to\s+do|\s+for\s+me)?"
    r"|give\s+me\s+(?:a\s+)?(?:suggestion|push|nudge|check[\s\-]?in)"
    r"|(?:any|check)\s+updates?(?:\s+for\s+me)?"
    r"|what(?:'s|\s+is)\s+(?:pending|left(?:\s+for\s+today)?|unfinished|remaining)"
    r"|am\s+i\s+forgetting\s+anything"
    r")$",
    re.IGNORECASE,
)


def proactive_coach_command(prompt: str, chat_id: str) -> tuple[str, str] | None:
    """Handle explicit 'what should I do now / push me / check on me' commands."""
    a = _app()
    normalized = a._normalize_command(prompt)
    if not _PROACTIVE_COMMAND_PATTERN.fullmatch(normalized):
        return None

    checkin = build_proactive_checkin(chat_id, preferred_category="combined")
    if checkin is None:
        name = a._user_name(a._user_fact_memories())
        name_part = f", {name}" if name else ""
        return (
            f"You're completely caught up{name_part}! All tasks and daily habits are clear, "
            "and nothing is waiting in your learning queue. Want to set a new goal or take a breather?",
            "local-proactive-coach",
        )
    return (checkin["message"], "local-proactive-coach")
