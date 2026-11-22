"""Productivity, memory, chat history, reminder, and notification CRUD routes."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["productivity"])


class ReminderCreatePayload(BaseModel):
    title: Optional[str] = None
    remind_at: Optional[str] = None
    text: Optional[str] = None
    run_at: Optional[str] = None
    recurrence: Optional[str] = None
    chat_id: Optional[str] = None


class ReminderUpdatePayload(BaseModel):
    completed: bool = True
    remind_at: Optional[str] = None
    run_at: Optional[str] = None


def _app():
    import app

    return app


@router.get("/api/chats")
def list_chats():
    return {"chats": _app().memory_store.list_chats()}


@router.post("/api/chats")
def create_chat():
    return JSONResponse(status_code=201, content=_app().memory_store.create_chat())


@router.get("/api/history/{chat_id}")
def history(chat_id: str):
    a = _app()
    if not a.memory_store.chat_exists(chat_id):
        raise HTTPException(404, "Conversation not found.")
    return {"messages": a.memory_store.get_messages(chat_id)}


@router.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    if not _app().memory_store.delete_chat(chat_id):
        raise HTTPException(404, "Conversation not found.")
    return {"status": "deleted"}


@router.delete("/api/chats")
def clear_chats():
    _app().memory_store.clear_chats()
    return {"status": "deleted"}


@router.get("/api/history")
async def api_get_history(session_id: str = "default"):
    a = _app()
    a._ensure_chat_exists(session_id)
    return {"messages": a.memory_store.get_messages(session_id)[-50:]}


@router.get("/api/memories")
def list_memories():
    return {"memories": _app().memory_store.list_memories()}


@router.post("/api/memories")
def create_memory(payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        raise HTTPException(400, "'content' must be a string.")
    try:
        return JSONResponse(status_code=201, content=_app().memory_store.add_memory(payload["content"]))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.put("/api/memories/{memory_id}")
def update_memory(memory_id: int, payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        raise HTTPException(400, "'content' must be a string.")
    try:
        memory = _app().memory_store.update_memory(memory_id, payload["content"])
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if memory is None:
        raise HTTPException(404, "Memory not found.")
    return memory


@router.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int):
    if not _app().memory_store.delete_memory(memory_id):
        raise HTTPException(404, "Memory not found.")
    return {"status": "deleted"}


@router.get("/api/tasks")
def list_tasks(include_completed: int = Query(0)):
    return {"tasks": _app().memory_store.list_tasks(include_completed == 1)}


@router.post("/api/tasks")
def create_task(payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict) or not isinstance(payload.get("title"), str):
        raise HTTPException(400, "'title' must be a string.")
    a = _app()
    try:
        task = a.memory_store.create_task(
            payload["title"],
            payload.get("priority", "medium"),
            payload.get("due_at"),
            payload.get("description", ""),
        )
        a._run_learning_hook(lambda: a._learning_suggest_for_task(task["id"]))
        return JSONResponse(status_code=201, content=task)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: int, payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object.")
    a = _app()
    chat_id = payload.get("chat_id")
    was_completed = any(
        item["id"] == task_id and item["completed"]
        for item in a.memory_store.list_tasks(include_completed=True)
    )
    try:
        task = a.memory_store.update_task(
            task_id,
            payload.get("title"),
            payload.get("priority"),
            payload.get("due_at"),
            payload.get("completed"),
            payload.get("description"),
            clear_due_at=("due_at" in payload and payload.get("due_at") in (None, "")),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if task is None:
        raise HTTPException(404, "Task not found.")
    if payload.get("completed") and not was_completed:
        a._notify_completion(
            chat_id,
            "task-coach",
            a._task_completion_line(task, name=a._user_name(a._user_fact_memories())),
        )
        a._run_learning_hook(lambda: a._learning_on_task_completed(task_id))
    elif payload.get("title") and not task.get("completed"):
        a._run_learning_hook(lambda: a._learning_suggest_for_task(task_id))
    return task


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    if not _app().memory_store.delete_task(task_id):
        raise HTTPException(404, "Task not found.")
    return {"status": "deleted"}


@router.post("/api/tasks/nudge")
def nudge_task(payload: dict[str, Any] = Body(...)):
    """Proactively suggest the top pending task if the user hasn't been nudged recently."""
    if not isinstance(payload, dict) or not isinstance(payload.get("chat_id"), str):
        raise HTTPException(400, "'chat_id' is required.")
    a = _app()
    chat_id = payload["chat_id"]
    if not a.memory_store.chat_exists(chat_id):
        raise HTTPException(404, "Chat not found.")
    tasks = a.memory_store.list_tasks(include_completed=False)
    if not tasks:
        return {"nudge": False, "reason": "no_pending_tasks"}
    if a.memory_store.has_recent_coach_notification(chat_id, minutes=30):
        return {"nudge": False, "reason": "already_nudged_recently"}
    threading.Thread(
        target=a._recommend_next_task,
        args=(chat_id,),
        daemon=True,
    ).start()
    return {"nudge": True, "task_count": len(tasks)}


@router.get("/api/habits")
def list_habits():
    return {"habits": _app().memory_store.list_habits()}


@router.post("/api/habits")
def create_habit(payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
        raise HTTPException(400, "'name' must be a string.")
    try:
        return JSONResponse(
            status_code=201,
            content=_app().memory_store.create_habit(
                payload["name"],
                payload.get("icon", "Activity"),
                payload.get("daily_goal", 1),
            ),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.delete("/api/habits/{habit_id}")
def delete_habit(habit_id: int):
    if not _app().memory_store.delete_habit(habit_id):
        raise HTTPException(404, "Habit not found.")
    return {"status": "deleted"}


@router.patch("/api/habits/{habit_id}")
def update_habit(habit_id: int, payload: dict[str, Any] = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object.")
    try:
        habit = _app().memory_store.update_habit(
            habit_id,
            payload.get("name"),
            payload.get("icon"),
            payload.get("daily_goal"),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if habit is None:
        raise HTTPException(404, "Habit not found.")
    return habit


@router.put("/api/habits/{habit_id}/completions/{completion_date}")
def set_habit_completion(
    habit_id: int, completion_date: str, payload: dict[str, Any] = Body(...)
):
    if not isinstance(payload, dict) or not isinstance(payload.get("completed"), bool):
        raise HTTPException(400, "'completed' must be a boolean.")
    a = _app()
    was_done = any(
        item["id"] == habit_id and completion_date in item["completed_dates"]
        for item in a.memory_store.list_habits()
    )
    try:
        habit = a.memory_store.set_habit_completion(
            habit_id, completion_date, payload["completed"]
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if habit is None:
        raise HTTPException(404, "Habit not found.")
    if payload["completed"] and not was_done:
        a._notify_completion(
            payload.get("chat_id"),
            "habit-coach",
            a._habit_completion_line(habit, name=a._user_name(a._user_fact_memories())),
        )
    return habit


@router.get("/api/gamification")
def get_gamification():
    return _app().memory_store.get_gamification()


@router.get("/api/reminders")
async def api_get_reminders(include_completed: bool = False):
    a = _app()
    if not include_completed:
        return {"reminders": a._live_reminders()}
    all_rows = a.memory_store.list_reminders(active_only=False)
    sorted_rows = sorted(
        all_rows,
        key=lambda r: (0 if r.get("active", 1) else 1, r.get("run_at", "")),
    )
    return {"reminders": [a._reminder_view(r) for r in sorted_rows]}


@router.post("/api/reminders")
async def api_create_reminder(payload: ReminderCreatePayload):
    title = (payload.title or payload.text or "").strip()
    remind_at = (payload.remind_at or payload.run_at or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Reminder title is required")
    if not remind_at:
        raise HTTPException(status_code=400, detail="Reminder time is required")
    a = _app()
    try:
        reminder = a._create_reminder_unified(
            title, remind_at, recurrence=payload.recurrence, chat_id=payload.chat_id
        )
        return {"reminder": reminder, "reminders": a._live_reminders()}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.patch("/api/reminders/{reminder_id}")
async def api_update_reminder(reminder_id: str, payload: ReminderUpdatePayload):
    a = _app()
    existing = a.memory_store.get_reminder(reminder_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if payload.completed:
        ok = a._cancel_reminder_unified(reminder_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Reminder not found")
        updated_row = a.memory_store.get_reminder(reminder_id)
        return {
            "status": "success",
            "reminder": a._reminder_view(updated_row) if updated_row else None,
            "reminders": a._live_reminders(),
        }

    new_when = (payload.remind_at or payload.run_at or "").strip()
    target_iso: str | None = None
    if new_when:
        parsed = a._parse_reminder_time(new_when)
        if parsed is None:
            raise HTTPException(
                status_code=400,
                detail=f"I could not understand the reminder time: {new_when!r}.",
            )
        target_iso = parsed.isoformat()
    else:
        is_recurring = bool(existing.get("recurrence"))
        if not is_recurring:
            stored_run_at = existing.get("run_at", "")
            try:
                stored_dt = datetime.fromisoformat(stored_run_at)
                if stored_dt.tzinfo is None:
                    stored_dt = stored_dt.replace(tzinfo=a.LOCAL_TIMEZONE)
                now_dt = datetime.now(a.LOCAL_TIMEZONE)
                if stored_dt <= now_dt:
                    raise HTTPException(
                        status_code=400,
                        detail="That time has passed — send a new remind_at",
                    )
            except HTTPException:
                raise
            except Exception as err:
                logging.getLogger("orbit007").warning("Error checking stored_run_at: %s", err)

    updated_row = a.memory_store.set_reminder_active(reminder_id, True, target_iso)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Reminder not found")

    a._schedule_reminder(updated_row)
    return {
        "status": "success",
        "reminder": a._reminder_view(updated_row),
        "reminders": a._live_reminders(),
    }


@router.delete("/api/reminders/{reminder_id}")
async def api_delete_reminder(reminder_id: str):
    a = _app()
    ok = a._cancel_reminder_unified(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"deleted": True, "reminders": a._live_reminders()}


@router.get("/api/notifications/{chat_id}")
def list_notifications(chat_id: str, after_id: int = Query(0)):
    a = _app()
    if not a.memory_store.chat_exists(chat_id):
        raise HTTPException(404, "Conversation not found.")
    return {"notifications": a.memory_store.list_notifications(chat_id, after_id)}


@router.get("/notifications/{chat_id}")
def compat_list_notifications(chat_id: str, after_id: int = Query(0)):
    return list_notifications(chat_id, after_id)


@router.get("/api/proactive/suggestions")
def get_proactive_suggestions(chat_id: str = Query("default")):
    """Return current automatic suggestions across tasks, habits, and learning."""
    a = _app()
    checkin = a.build_proactive_checkin(chat_id=chat_id, preferred_category="combined")
    snap = a.get_proactive_snapshot()
    return {
        "has_suggestions": checkin is not None,
        "checkin": checkin,
        "pending_counts": {
            "tasks": len(snap["pending_tasks"]),
            "habits": len(snap["pending_habits"]),
            "learning": len(snap["learning_topics"]),
        },
        "suggestions": {
            "top_task": snap["pending_tasks"][0] if snap["pending_tasks"] else None,
            "top_habit": snap["pending_habits"][0] if snap["pending_habits"] else None,
            "top_learning": snap["learning_topics"][0] if snap["learning_topics"] else None,
        },
    }


@router.post("/api/proactive/check-in")
def trigger_proactive_checkin(payload: dict[str, Any] = Body(default=None)):
    """Trigger a regular or on-demand proactive check-in for tasks, habits, and learning."""
    a = _app()
    payload = payload if isinstance(payload, dict) else {}
    chat_id = str(payload.get("chat_id") or a.DEFAULT_CHAT_ID)
    force = bool(payload.get("force", False))
    cooldown_minutes = int(payload.get("cooldown_minutes", 30))
    preferred_category = payload.get("category")
    return a.deliver_proactive_checkin(
        chat_id=chat_id,
        force=force,
        cooldown_minutes=cooldown_minutes,
        preferred_category=preferred_category,
    )


@router.delete("/api/database")
@router.post("/api/database/reset")
def reset_all_database_data():
    """Permanently delete all user data (chats, memories, tasks, habits, reminders, learning, XP) from SQLite."""
    a = _app()
    system_jobs = {
        "spidey-temp-audio-cleanup",
        getattr(a, "WEEKLY_LEARNING_NUDGE_JOB", "weekly-learning-nudge"),
        getattr(a, "PROACTIVE_COACH_JOB_ID", "spidey-proactive-coach"),
    }
    try:
        if hasattr(a, "reminder_scheduler") and a.reminder_scheduler.running:
            for job in list(a.reminder_scheduler.get_jobs()):
                job_id = str(getattr(job, "id", ""))
                if job_id and job_id not in system_jobs and not job_id.startswith("weekly-learning-nudge"):
                    try:
                        a.reminder_scheduler.remove_job(job_id)
                    except Exception:
                        pass
    except Exception:
        pass

    deleted = a.memory_store.clear_all_data()
    if hasattr(a, "confirmation_mgr") and hasattr(a.confirmation_mgr, "_pending"):
        a.confirmation_mgr._pending.clear()
    a._ensure_chat_exists(a.DEFAULT_CHAT_ID)
    return {
        "status": "cleared",
        "deleted": deleted,
        "default_chat_id": a.DEFAULT_CHAT_ID,
    }


