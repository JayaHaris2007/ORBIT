"""Proactive coach: automatic suggestions and regular check-ins for tasks, habits, and learning."""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from apscheduler.triggers.interval import IntervalTrigger
from voice.text_clean import summarize_for_speech

_DELIVERY_LOCK = threading.Lock()
_PRESENCE_LOCK = threading.Lock()
_FRONTEND_CLIENTS: dict[str, float] = {}
_ACTIVE_FRONTEND_CHAT_ID: str | None = None

PROACTIVE_COACH_JOB_ID = "spidey-proactive-coach"
DEFAULT_COACH_INTERVAL_MINUTES = int(os.environ.get("ORBIT_COACH_INTERVAL_MINUTES", "45").strip() or "45")
QUIET_HOURS_START = int(os.environ.get("ORBIT_QUIET_HOURS_START", "23").strip() or "23")  # 11:00 PM
QUIET_HOURS_END = int(os.environ.get("ORBIT_QUIET_HOURS_END", "7").strip() or "7")        # 7:00 AM
EVENING_WRAPUP_HOUR = int(os.environ.get("ORBIT_EVENING_WRAPUP_HOUR", "20").strip() or "20")  # 8:00 PM
try:
    FRONTEND_ACTIVE_TTL_SECONDS = max(
        5.0, float(os.environ.get("ORBIT_FRONTEND_ACTIVE_TTL_SECONDS", "90").strip() or "90")
    )
except ValueError:
    FRONTEND_ACTIVE_TTL_SECONDS = 90.0

PROACTIVE_NOTIFICATION_PREFIXES = (
    "task-coach-",
    "code-sugg-",
    "weekly-learning-nudge",
    "learning-weekly-nudge",
)


def _app():
    import app

    return app


def mark_frontend_active(client_id: str = "default", chat_id: str | None = None) -> None:
    """Record that a browser tab running the web frontend is currently open."""
    global _ACTIVE_FRONTEND_CHAT_ID
    key = (client_id or "default").strip() or "default"
    with _PRESENCE_LOCK:
        _FRONTEND_CLIENTS[key] = time.monotonic()
        if chat_id:
            _ACTIVE_FRONTEND_CHAT_ID = str(chat_id)


def mark_frontend_inactive(client_id: str | None = None) -> None:
    """Mark one frontend tab (or all tabs when client_id is None) as closed."""
    global _ACTIVE_FRONTEND_CHAT_ID
    with _PRESENCE_LOCK:
        if client_id is None:
            _FRONTEND_CLIENTS.clear()
            _ACTIVE_FRONTEND_CHAT_ID = None
        else:
            key = client_id.strip() or "default"
            _FRONTEND_CLIENTS.pop(key, None)
            if not _FRONTEND_CLIENTS:
                _ACTIVE_FRONTEND_CHAT_ID = None


def get_active_frontend_chat_id() -> str | None:
    """Return the most recently polled local frontend chat ID, if any tab is active."""
    if not is_frontend_active():
        return None
    with _PRESENCE_LOCK:
        return _ACTIVE_FRONTEND_CHAT_ID


def is_frontend_active(ttl_seconds: float | None = None) -> bool:
    """Return True if at least one web frontend tab has checked in within the TTL window."""
    ttl = FRONTEND_ACTIVE_TTL_SECONDS if ttl_seconds is None else max(0.0, float(ttl_seconds))
    now = time.monotonic()
    with _PRESENCE_LOCK:
        expired = [cid for cid, ts in _FRONTEND_CLIENTS.items() if (now - ts) > ttl]
        for cid in expired:
            _FRONTEND_CLIENTS.pop(cid, None)
        if _FRONTEND_CLIENTS:
            return True

    try:
        a = _app()
        ws_mgr = getattr(a, "ws_manager", None)
        if ws_mgr is not None and bool(getattr(ws_mgr, "active", None)):
            return True
    except Exception:
        pass
    return False


def is_proactive_notification_key(reminder_id: str | None) -> bool:
    """Return True when a notification belongs to proactive coaching/learning nudges (not user reminders)."""
    if not reminder_id:
        return False
    key = str(reminder_id)
    if key.startswith(PROACTIVE_NOTIFICATION_PREFIXES):
        return True
    try:
        nudge_key = getattr(_app().learning_nudges, "NUDGE_NOTIFICATION_KEY", "")
        if nudge_key and key.startswith(str(nudge_key)):
            return True
    except Exception:
        pass
    return False


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
    folder_insights: list[dict[str, Any]] = []
    if a.learning_schema.is_initialized():
        try:
            from learning import code_rag

            # Keep linked learning folders fresh (incremental hash check is sub-5ms when unchanged)
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                try:
                    code_rag.sync_all_linked_folders(embed=None)
                except Exception:
                    pass
            learning_topics = a.learning_progress.next_topics(limit=5)
            learning_overview = a.learning_progress.overall_progress()
            for link in code_rag.list_folder_links():
                if not link.get("enabled", True):
                    continue
                try:
                    folder_insights.append(code_rag.get_roadmap_code_insights(int(link["roadmap_id"])))
                except Exception:
                    continue
        except Exception as err:
            a.LOGGER.debug("Proactive snapshot learning lookup skipped: %s", err)

    return {
        "today": today_iso,
        "pending_tasks": pending_tasks,
        "pending_habits": pending_habits,
        "all_habits_count": len(all_habits),
        "learning_topics": learning_topics,
        "learning_overview": learning_overview,
        "folder_insights": folder_insights,
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


def _recent_coach_messages(chat_id: str, limit: int = 4) -> list[str]:
    """Return the last few proactive coach messages sent to chat_id to avoid repetition."""
    if not chat_id:
        return []
    a = _app()
    try:
        with a.memory_store.connect() as conn:
            rows = conn.execute(
                "SELECT content FROM notifications "
                "WHERE chat_id = ? AND reminder_id LIKE 'task-coach-%' "
                "ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return [str(r["content"] or "") for r in rows if r["content"]]
    except Exception:
        return []


_FRIEND_STYLES: tuple[tuple[str, str], ...] = (
    (
        "chill-short",
        "Super short and chill — just one casual sentence like a quick text from a friend. Do NOT start with 'Hey'.",
    ),
    (
        "playful",
        "Light, playful friend energy — gentle friendly humor without being cheesy or pushy. Start directly with a thought or observation.",
    ),
    (
        "curious",
        "Curious friend vibe — ask what they're up to or how their flow is going, and weave the item in naturally.",
    ),
    (
        "co-pilot",
        "Study-partner / teammate vibe — offer to tackle it together or help unblock them if they're stuck.",
    ),
    (
        "low-pressure",
        "Easygoing, zero-pressure tone — suggest even a tiny 10-minute start if they're not feeling a full session.",
    ),
    (
        "hype",
        "Upbeat, encouraging friend rooting for their momentum and progress — keep it natural, never corny.",
    ),
    (
        "direct",
        "Ultra-direct one-liner — skip small talk and greetings completely, just ask casually.",
    ),
    (
        "thoughtful",
        "Warm, attentive friend checking in on their energy first and tying it smoothly to the item.",
    ),
)

_RECENT_STYLES: list[str] = []


def _pick_fresh_variant(variants: list[str], recent_messages: list[str], seed: int = 0) -> str:
    """Choose a conversational phrasing that wasn't just used in recent check-ins."""
    if not variants:
        return ""
    recent_lower = [m.lower() for m in recent_messages]
    recent_starts = {" ".join(m.split()[:2]) for m in recent_lower if m.strip()}
    fresh = [
        v for v in variants
        if v[:24].lower() not in " ".join(recent_lower)
        and " ".join(v.lower().split()[:2]) not in recent_starts
    ]
    pool = fresh or variants
    return random.choice(pool)


def _humanize_checkin_with_llm(
    *,
    category: str,
    facts: list[str],
    required_terms: list[str],
    time_of_day: str,
    user_name: str,
    recent_messages: list[str],
    evening_mode: bool,
    late_night_mode: bool,
) -> str | None:
    """Optionally ask the active LLM to write a fresh, unscripted friend-style check-in (non-blocking)."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ORBIT_PROACTIVE_LLM", "1").strip() == "0":
        return None
    a = _app()
    if not a._llm_available():
        return None
    # Never block an interactive chat or voice turn
    if not a.generation_lock.acquire(blocking=False):
        return None
    try:
        available_styles = [s for s in _FRIEND_STYLES if s[0] not in _RECENT_STYLES[-4:]]
        style_id, style_guide = random.choice(available_styles or list(_FRIEND_STYLES))
        _RECENT_STYLES.append(style_id)
        if len(_RECENT_STYLES) > 8:
            del _RECENT_STYLES[:-8]

        banned_openers = []
        for prev in recent_messages[:4]:
            words = prev.strip().split()[:3]
            if words:
                banned_openers.append(" ".join(words))

        avoid_block = ""
        if recent_messages:
            snippets = "\n".join(f'- "{m[:140]}"' for m in recent_messages[:3])
            avoid_block = f"\nRecent messages you ALREADY sent (use a completely different opening and sentence structure):\n{snippets}"
        if banned_openers:
            avoid_block += "\nDo NOT start with any of these openings: " + ", ".join(f'"{o}"' for o in banned_openers)

        mood_hint = (
            "It's late at night — keep it gentle and brief before sleep."
            if late_night_mode
            else (
                "It's evening — casual end-of-day wind-down vibe, lightly encourage keeping their streak alive before the day ends."
                if evening_mode
                else f"It's {time_of_day}."
            )
        )
        name_line = (
            f"Their name is {user_name} (optional — only use it occasionally, don't force it into every message)."
            if user_name
            else "Do NOT call them 'buddy' or 'friend' — just talk naturally like someone you text every day."
        )
        system_msg = (
            "You are ORBIT, texting your close friend casually. "
            "Write ONE fresh, natural message (1-2 short sentences, max 40 words). "
            "Vary your openings, rhythm, and tone every time — NEVER use a formulaic 'Hey buddy, remember...' opener. "
            "Rules: plain conversational English with contractions; NO bullet lists, NO headings, "
            "NO robotic labels like 'Habit push:', 'Study push:', 'Task check-in:', or 'Accountability check-in:', "
            "NO quotes around the message, NO emojis. Include the exact item name(s) naturally."
        )
        user_msg = (
            f"{name_line}\n"
            f"Time: {mood_hint}\n"
            f"Style for THIS message: {style_guide}\n"
            f"Context ({category}):\n" + "\n".join(f"- {f}" for f in facts)
            + avoid_block
            + "\nWrite the message now."
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
        gemini_key, gemini_model = a.get_active_gemini_config()
        if gemini_key:
            resp = a.gemini_chat_request(
                messages,
                api_key=gemini_key,
                model=gemini_model,
                max_tokens=110,
                timeout=12.0,
            )
            text = ((resp.get("message") or {}).get("content") or "").strip()
        else:
            import json
            import urllib.request

            payload = {
                "model": a.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "think": False,
                "keep_alive": a.OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.9,
                    "top_p": 0.92,
                    "repeat_penalty": 1.15,
                    "num_predict": 110,
                    "num_ctx": min(2048, a.OLLAMA_NUM_CTX),
                },
            }
            req = urllib.request.Request(
                f"{a.OLLAMA_URL}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = ((data.get("message") or {}).get("content") or "").strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        text = text.strip(" \"'")
        if not text or len(text) < 18 or len(text) > 320:
            return None
        # Reject robotic labels or bullet lists if the model slipped
        if re.match(r"^(?:habit push|study push|task check-?in|accountability|reminder)\s*[:—-]", text, re.IGNORECASE):
            return None
        if "\n- " in text or "\n* " in text:
            return None
        # Ensure every required item title/name actually appears so the LLM never hallucinates items
        low = text.lower()
        if not all(term.lower() in low for term in required_terms if term):
            return None
        return text
    except Exception as exc:
        a.LOGGER.debug("LLM proactive humanizer fallback: %s", exc)
        return None
    finally:
        a.generation_lock.release()


def build_proactive_checkin(
    chat_id: str | None = None,
    preferred_category: str | None = None,
    *,
    now: datetime | None = None,
    use_llm: bool = True,
) -> dict[str, Any] | None:
    """Build a warm, friend-like check-in or suggestion across tasks, habits, and learning."""
    a = _app()
    snap = get_proactive_snapshot()
    pending_tasks = snap["pending_tasks"]
    pending_habits = snap["pending_habits"]
    learning_topics = snap["learning_topics"]

    if not pending_tasks and not pending_habits and not learning_topics:
        return None

    now_local = (now or datetime.now(a.LOCAL_TIMEZONE)).astimezone(a.LOCAL_TIMEZONE)
    hour = now_local.hour
    time_of_day = (
        "morning" if 5 <= hour < 12
        else ("afternoon" if 12 <= hour < 17 else ("evening" if 17 <= hour < 22 else "late night"))
    )

    name = a._user_name(a._user_fact_memories())
    name_comma = f" {name}" if name else ""
    name_end = f", {name}" if name else ""
    evening_mode = is_evening_wrapup(now_local)
    late_night_mode = is_quiet_hours(now_local)
    recent_msgs = _recent_coach_messages(chat_id or "", limit=4)
    seed = now_local.hour + now_local.minute

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
    facts: list[str] = []
    required_terms: list[str] = []

    if category == "task" and top_task:
        target_type = "task"
        target_title = top_task["title"]
        priority = top_task.get("priority", "medium")
        due_at = top_task.get("due_at")
        extra_count = len(pending_tasks) - 1
        extra_note = f" (along with {extra_count} other open task{'s' if extra_count != 1 else ''})" if extra_count > 0 else ""
        required_terms = [top_task["title"]]
        if due_at:
            due_str = a._format_due_date(due_at)
            facts.append(f"Open task: {top_task['title']} ({priority} priority, due {due_str})")
        else:
            facts.append(f"Open task: {top_task['title']} ({priority} priority{extra_note})")

        if evening_mode or late_night_mode:
            variants = [
                f"Hey{name_comma}, winding down for the night — did you manage to finish **{top_task['title']}** today, or should we roll it to tomorrow?",
                f"Before you call it a day{name_end}, how did **{top_task['title']}** go? Just say the word if you finished it and I'll tick it off.",
                f"Almost bedtime{name_end} — any luck wrapping up **{top_task['title']}** today, or want to save it for tomorrow?",
            ]
        elif due_at:
            due_str = a._format_due_date(due_at)
            variants = [
                f"Hey{name_comma}, just a heads-up — **{top_task['title']}** is due {due_str}. Already knocked it out, or feel like getting into it now?",
                f"Checking in{name_end} — how's **{top_task['title']}** coming along before {due_str}? Let me know if you want to chip away at it together.",
                f"Yo{name_comma}, saw **{top_task['title']}** coming up for {due_str}. Did you wrap it up already, or should we tackle it next?",
            ]
        else:
            variants = [
                f"Hey{name_comma}, just checking in — how's **{top_task['title']}** going? Let me know if you already knocked it out or feel like tackling it next.",
                f"Yo{name_comma}, any progress on **{top_task['title']}**{extra_note}? Tell me if it's done so I can check it off for you.",
                f"Hey{name_comma}, **{top_task['title']}** is still hanging out on your list{extra_note}. Want to knock it out now, or already done with it?",
                f"Quick check-in{name_end} — did you get around to **{top_task['title']}** yet, or want to dive into it for a bit?",
            ]
        fallback_message = _pick_fresh_variant(variants, recent_msgs, seed)

    elif category == "habit" and top_habit:
        target_type = "habit"
        target_title = top_habit["name"]
        other_count = len(pending_habits) - 1
        other_note = (
            f" (plus {other_count} other habit{'s' if other_count != 1 else ''})"
            if other_count > 0
            else ""
        )
        required_terms = [top_habit["name"]]
        facts.append(f"Unchecked daily habit today: {top_habit['name']}{other_note}")

        if evening_mode or late_night_mode:
            variants = [
                f"Hey{name_comma}, before the day ends, did you get **{top_habit['name']}**{other_note} done? Let's tick it off so your streak stays alive!",
                f"Winding down for the evening{name_end} — just looking out for your streak! Did you finish **{top_habit['name']}**{other_note} today?",
                f"Quick night check{name_end} — **{top_habit['name']}**{other_note} is still open before the day ends. Already did it, or want to squeeze it in to keep the streak going?",
            ]
        elif len(pending_habits) == 1:
            variants = [
                f"Hey{name_comma}, **{top_habit['name']}** is the last habit left on your list today — did you get a chance to knock it out yet?",
                f"You're super close to a clean sweep today{name_end}! Just **{top_habit['name']}** left — already done with it, or planning to do it soon?",
                f"Yo{name_comma}, checking in on **{top_habit['name']}** since it's your last habit for today. Feel like knocking it out?",
            ]
        else:
            variants = [
                f"Hey{name_comma}, did you get a chance to squeeze in **{top_habit['name']}** today{other_note}? Even a quick session keeps the momentum rolling.",
                f"Just checking in{name_end} — haven't checked off **{top_habit['name']}** yet today{other_note}. Did you already do it, or planning to soon?",
                f"Yo{name_comma}, how's today going? Want to knock out **{top_habit['name']}**{other_note} so it's out of the way?",
                f"Friendly poke{name_end} — **{top_habit['name']}** is still waiting on today's habit list{other_note}. Already done with it?",
            ]
        fallback_message = _pick_fresh_variant(variants, recent_msgs, seed)

    elif category == "learning" and top_topic:
        target_type = "learning"
        target_title = top_topic["name"]
        roadmap_name = top_topic.get("roadmap_name", "your roadmap")
        status = top_topic.get("status", "not_started")
        required_terms = [top_topic["name"]]
        facts.append(f"Learning topic: {top_topic['name']} in {roadmap_name} (status: {status})")

        # Pull real code-folder context for this roadmap (or any linked roadmap)
        folder_insights = snap.get("folder_insights") or []
        rm_insight = next(
            (ins for ins in folder_insights if ins.get("roadmap_id") == top_topic.get("roadmap_id")),
            folder_insights[0] if folder_insights else None,
        )
        empty_files = (rm_insight or {}).get("empty_files") or []
        raw_pending_sugg = (rm_insight or {}).get("pending_suggestions") or []
        recent_blob = " ".join(recent_msgs).lower()
        # Do not nag repeatedly about the exact same code-completion suggestion already asked recently
        pending_code_sugg = [
            s for s in raw_pending_sugg
            if str(s.get("topic_name") or "").lower() not in recent_blob
        ]
        recent_files = (rm_insight or {}).get("recent_files") or []

        if pending_code_sugg:
            first_sugg = pending_code_sugg[0]
            s_topic = first_sugg["topic_name"]
            s_files = ", ".join(f["rel_path"] for f in (first_sugg.get("evidence_files") or [])[:2])
            next_after = next(
                (t["name"] for t in learning_topics if t["name"] != s_topic),
                None,
            )
            required_terms = [s_topic]
            target_title = s_topic
            facts.append(
                f"Detected practiced code for '{s_topic}' in {roadmap_name} ({s_files}); awaiting user confirmation to mark completed."
                + (f" Next topic after that: {next_after}." if next_after else "")
            )
            if next_after:
                variants = [
                    f"Hey{name_comma}, I noticed you already coded **{s_topic}** in **{roadmap_name}** ({s_files}) — want me to mark it completed so we can roll into **{next_after}**?",
                    f"Yo{name_comma}, saw your code in `{s_files}` for **{s_topic}**! Ready to confirm it done and jump into **{next_after}** next?",
                    f"Quick check-in{name_end} — looks like you've been practicing **{s_topic}** ({s_files}) in **{roadmap_name}**. Should I tick that one off for you?",
                ]
            else:
                variants = [
                    f"Hey{name_comma}, I noticed you already coded **{s_topic}** in **{roadmap_name}** ({s_files}) — want me to mark it completed for you?",
                    f"Quick check-in{name_end} — looks like you've been practicing **{s_topic}** ({s_files}) in **{roadmap_name}**. Ready to mark it done?",
                ]
        elif empty_files:
            empty_fname = empty_files[0].split("/")[-1]
            facts.append(
                f"User created empty practice file '{empty_fname}' in {roadmap_name} folder and hasn't coded it yet. Next roadmap topic after that is {top_topic['name']}."
            )
            if evening_mode or late_night_mode:
                variants = [
                    f"Hey{name_comma}, saw `{empty_fname}` sitting empty in your **{roadmap_name}** folder — want to knock out a quick practice before resting, or save **{top_topic['name']}** for tomorrow?",
                    f"Evening check-in{name_end} — `{empty_fname}` in **{roadmap_name}** is still waiting for some code! Feel like wrapping it up before moving on to **{top_topic['name']}**?",
                ]
            else:
                variants = [
                    f"Yo{name_comma}, I noticed you started `{empty_fname}` in your **{roadmap_name}** folder but it's still empty — want to knock that out before jumping into **{top_topic['name']}**?",
                    f"Hey{name_comma}, `{empty_fname}` is waiting in your **{roadmap_name}** folder! Feel like filling it in and then rolling straight into **{top_topic['name']}**?",
                    f"Quick study poke{name_end} — once you finish up `{empty_fname}`, **{top_topic['name']}** is right up next in **{roadmap_name}**. Want to code it together?",
                ]
        elif evening_mode or late_night_mode:
            variants = [
                f"Hey{name_comma}, did you get to spend any time on **{top_topic['name']}** in **{roadmap_name}** today? Let me know if we can mark it done before you rest.",
                f"Evening check-in{name_end} — how did **{top_topic['name']}** go in **{roadmap_name}** today?",
            ]
        elif status in ("learning", "in_progress"):
            variants = [
                f"Hey{name_comma}, how's **{top_topic['name']}** in **{roadmap_name}** treating you? Did you wrap it up or still digging into it?",
                f"Checking in on **{top_topic['name']}** ({roadmap_name}){name_end} — making good headway, or ready to mark it done?",
                f"Yo{name_comma}, still working through **{top_topic['name']}** in **{roadmap_name}**? Let me know if you got stuck or already nailed it.",
            ]
        elif recent_files:
            latest_f = recent_files[0].split("/")[-1]
            facts.append(f"Recently practiced file in folder: {latest_f}")
            variants = [
                f"Nice work on `{latest_f}` in **{roadmap_name}**{name_end}! Ready to keep the streak going and tackle **{top_topic['name']}** next?",
                f"Hey{name_comma}, saw you wrapped up `{latest_f}` in **{roadmap_name}** — **{top_topic['name']}** is lined up next whenever you've got a bit of focus.",
                f"Yo{name_comma}, good momentum after `{latest_f}`! Want to dive into **{top_topic['name']}** in **{roadmap_name}** next?",
            ]
        else:
            variants = [
                f"Hey{name_comma}, whenever you've got a bit of focus, **{top_topic['name']}** is up next in **{roadmap_name}** — feel like diving in, or already covered it?",
                f"Yo{name_comma}, in the mood for some **{roadmap_name}**? **{top_topic['name']}** is lined up next whenever you're ready.",
                f"Just checking in{name_end} — **{top_topic['name']}** is waiting next in your **{roadmap_name}** track. Want to start on it now?",
                f"Hey{name_comma}, got a little study energy? We could knock out **{top_topic['name']}** in **{roadmap_name}** next, or tell me if you already went through it.",
            ]
        fallback_message = _pick_fresh_variant(variants, recent_msgs, seed)

    else:
        category = "combined"
        pieces: list[str] = []
        if top_task:
            target_type = target_type or "task"
            target_title = target_title or top_task["title"]
            required_terms.append(top_task["title"])
            facts.append(f"Top open task: {top_task['title']} ({len(pending_tasks)} open)")
            pieces.append(f"**{top_task['title']}** on your tasks")
        if top_habit:
            target_type = target_type or "habit"
            target_title = target_title or top_habit["name"]
            required_terms.append(top_habit["name"])
            facts.append(f"Open daily habit: {top_habit['name']} ({len(pending_habits)} left today)")
            pieces.append(f"**{top_habit['name']}** for today's habit")
        if top_topic:
            target_type = target_type or "learning"
            target_title = target_title or top_topic["name"]
            required_terms.append(top_topic["name"])
            rm_label = top_topic.get("roadmap_name", "your roadmap")
            facts.append(f"Next study topic: {top_topic['name']} ({rm_label})")
            pieces.append(f"**{top_topic['name']}** lined up next in **{rm_label}**")

        if len(pieces) == 1:
            summary_phrase = pieces[0]
            ref_pronoun = "that"
            pick_question = "feel like jumping into it?"
        elif len(pieces) == 2:
            summary_phrase = f"{pieces[0]} and {pieces[1]}"
            ref_pronoun = "either of those"
            pick_question = "which one are you feeling like tackling first?"
        else:
            summary_phrase = f"{pieces[0]}, {pieces[1]}, and {pieces[2]}"
            ref_pronoun = "any of those"
            pick_question = "which one do you feel like jumping into first?"

        if late_night_mode:
            variants = [
                f"Getting late{name_end} — you've still got {summary_phrase}. Did you wrap up {ref_pronoun} before calling it a night?",
                f"Before you crash{name_end}, still seeing {summary_phrase} open. Want me to tick anything off for today?",
            ]
        elif evening_mode:
            variants = [
                f"Winding down for the evening{name_end} — you've still got {summary_phrase}. Did you knock {ref_pronoun} out today?",
                f"How did today treat you{name_end}? Looks like {summary_phrase} still open — anything I should mark done?",
            ]
        else:
            variants = [
                f"Just seeing where things stand{name_end} — you've got {summary_phrase}. Already finished {ref_pronoun}, or {pick_question}",
                f"How's your {time_of_day} flowing{name_end}? You still have {summary_phrase} waiting — {pick_question}",
                f"Not to interrupt your groove{name_end}, just peeking at your list: {summary_phrase}. Want to knock something out together?",
                f"Got a bit of momentum right now{name_end}? Right now you've got {summary_phrase} — {pick_question}",
            ]
        fallback_message = _pick_fresh_variant(variants, recent_msgs, seed)

    message = fallback_message
    if use_llm:
        llm_msg = _humanize_checkin_with_llm(
            category=category,
            facts=facts,
            required_terms=required_terms,
            time_of_day=time_of_day,
            user_name=name,
            recent_messages=recent_msgs,
            evening_mode=evening_mode,
            late_night_mode=late_night_mode,
        )
        if llm_msg:
            message = llm_msg

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
    mirror_to_discord: bool = True,
) -> dict[str, Any]:
    """Deliver a proactive check-in notification.

    Routing rule:
    - When the web frontend is open, proactive check-ins go ONLY to the frontend (never Discord).
    - When the web frontend is closed, automatic proactive check-ins go ONLY to Discord (never piling up in the closed web UI).
    """
    a = _app()
    target_chat = chat_id or a.DEFAULT_CHAT_ID
    a._ensure_chat_exists(target_chat)
    frontend_open = is_frontend_active()
    ext_session = a.memory_store.get_external_session(target_chat)
    target_is_discord = bool(ext_session and ext_session.get("provider") == "discord")

    with _DELIVERY_LOCK:
        # Silence automatic background check-ins during late-night quiet hours (11 PM - 7 AM)
        if not force and is_quiet_hours(now):
            return {
                "nudge": False,
                "reason": "quiet_hours",
                "chat_id": target_chat,
                "discord_delivered": 0,
            }

        # Never send proactive check-ins to Discord while the web frontend is open
        if target_is_discord and frontend_open and not force:
            return {
                "nudge": False,
                "reason": "frontend_active",
                "chat_id": target_chat,
                "discord_delivered": 0,
            }

        if not force and a.memory_store.has_recent_coach_notification(target_chat, minutes=cooldown_minutes):
            return {
                "nudge": False,
                "reason": "already_nudged_recently",
                "chat_id": target_chat,
                "discord_delivered": 0,
            }

        # When the frontend is NOT open, automatic check-ins on a local chat route ONLY to Discord
        if not target_is_discord and not frontend_open and not force:
            discord_chats = a.memory_store.list_external_chats("discord")
            if not discord_chats:
                return {
                    "nudge": False,
                    "reason": "frontend_inactive_no_discord",
                    "chat_id": target_chat,
                    "discord_delivered": 0,
                }
            eligible_discord = [
                d["id"]
                for d in discord_chats
                if not a.memory_store.has_recent_coach_notification(d["id"], minutes=cooldown_minutes)
            ]
            if not eligible_discord:
                return {
                    "nudge": False,
                    "reason": "already_nudged_recently",
                    "chat_id": target_chat,
                    "discord_delivered": 0,
                }
            checkin = build_proactive_checkin(eligible_discord[0], preferred_category=preferred_category, now=now)
            if checkin is None:
                return {
                    "nudge": False,
                    "reason": "nothing_pending",
                    "chat_id": eligible_discord[0],
                    "discord_delivered": 0,
                }
            discord_delivered = 0
            last_key = ""
            for d_cid in eligible_discord:
                last_key = f"task-coach-{checkin['category']}-discord-{uuid.uuid4()}"
                a.memory_store.add_notification(d_cid, last_key, checkin["message"])
                discord_delivered += 1
            return {
                "nudge": True,
                "chat_id": eligible_discord[0],
                "notification_key": last_key,
                "discord_delivered": discord_delivered,
                "channel": "discord",
                **checkin,
            }

        checkin = build_proactive_checkin(target_chat, preferred_category=preferred_category, now=now)
        if checkin is None:
            return {
                "nudge": False,
                "reason": "nothing_pending",
                "chat_id": target_chat,
                "discord_delivered": 0,
            }

        notif_key = f"task-coach-{checkin['category']}-{uuid.uuid4()}"
        a.memory_store.add_notification(target_chat, notif_key, checkin["message"])

        # Only mirror to Discord when the frontend is NOT open and target isn't already Discord
        discord_delivered = 1 if target_is_discord else 0
        effective_mirror = mirror_to_discord and (not frontend_open) and (not target_is_discord)
        if effective_mirror:
            try:
                discord_chats = a.memory_store.list_external_chats("discord")
                for d_chat in discord_chats:
                    d_cid = d_chat["id"]
                    if d_cid == target_chat:
                        continue
                    if not force and a.memory_store.has_recent_coach_notification(d_cid, minutes=cooldown_minutes):
                        continue
                    a.memory_store.add_notification(
                        d_cid, f"task-coach-{checkin['category']}-discord-{uuid.uuid4()}", checkin["message"]
                    )
                    discord_delivered += 1
            except Exception as exc:
                logging.getLogger("orbit007").debug("Discord proactive mirror skipped: %s", exc)

    if not target_is_discord:
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
        "discord_delivered": discord_delivered,
        "channel": "discord" if target_is_discord else "frontend",
        **checkin,
    }


def run_scheduled_proactive_checkins(provider: str = "local", now: datetime | None = None) -> int:
    """Periodic background job that routes check-ins exclusively to frontend (when open) or Discord (when closed)."""
    a = _app()
    try:
        frontend_open = is_frontend_active()
        cooldown = max(15, DEFAULT_COACH_INTERVAL_MINUTES - 5)

        if provider == "discord":
            if frontend_open:
                return 0
            chat_ids = [c["id"] for c in a.memory_store.list_external_chats("discord")]
            sent = 0
            for cid in chat_ids[:3]:
                res = deliver_proactive_checkin(
                    cid,
                    force=False,
                    cooldown_minutes=cooldown,
                    now=now,
                    mirror_to_discord=False,
                )
                if res.get("nudge"):
                    sent += 1
            return sent

        # provider == "local"
        if not frontend_open:
            # Frontend is closed -> deliver ONLY to Discord (never pile up in closed web UI)
            discord_ids = [c["id"] for c in a.memory_store.list_external_chats("discord")]
            sent = 0
            for cid in discord_ids[:3]:
                res = deliver_proactive_checkin(
                    cid,
                    force=False,
                    cooldown_minutes=cooldown,
                    now=now,
                    mirror_to_discord=False,
                )
                if res.get("nudge"):
                    sent += 1
            return sent

        active_cid = get_active_frontend_chat_id()
        if active_cid and a.memory_store.chat_exists(active_cid) and not a.memory_store.get_external_session(active_cid):
            chat_ids = [active_cid]
        else:
            chat_ids = a.memory_store.list_local_chat_ids()
            if not chat_ids:
                a._ensure_chat_exists(a.DEFAULT_CHAT_ID)
                chat_ids = [a.DEFAULT_CHAT_ID]
            chat_ids = chat_ids[:1]

        sent = 0
        for cid in chat_ids:
            res = deliver_proactive_checkin(
                cid,
                force=False,
                cooldown_minutes=cooldown,
                now=now,
                mirror_to_discord=False,
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
