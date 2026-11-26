"""Native tool registry, JSON schemas, argument validation, and executors for S.P.I.D.E.Y.

Every tool interacts directly with the existing data layer through AgentDeps.
Schemas are strictly constrained (<40 words per description) to preserve token budget.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import rapidfuzz.fuzz

from agent.confirm import ConfirmationManager
from agent.deps import AgentDeps

log = logging.getLogger("orbit007.tools")


@dataclass
class ToolContext:
    """Turn-scoped execution context passed to tool executors."""

    deps: AgentDeps
    chat_id: str
    channel: str = "web"
    confirm_mgr: ConfirmationManager = field(default_factory=ConfirmationManager)
    ui_actions: list[dict[str, Any]] = field(default_factory=list)
    has_called_web_search: bool = False
    tools_called: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """Tool metadata and execution specification."""

    name: str
    description: str
    parameters: dict[str, Any]
    destructive: bool
    executor: Callable[[dict[str, Any], ToolContext], dict[str, Any]]

    def to_ollama_tool(self) -> dict[str, Any]:
        """Convert to the OpenAI / Ollama tool definition JSON format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# --- Entity Resolution Helper ---

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


def _normalize_tech_text(value: str) -> str:
    """Normalize programming-language symbols and common spoken aliases for fuzzy matching."""
    text = str(value or "").strip().lower()
    for pattern, repl in _TECH_TEXT_REPLACEMENTS:
        text = pattern.sub(repl, text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_entity(
    query: str | int,
    candidates: list[dict[str, Any]],
    title_key: str = "title",
    entity_name: str = "item",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve an entity reference (id or title) using rapidfuzz against live candidates.

    Returns:
        (resolved_item, error_dict)
        If resolved_item is present, resolution succeeded.
        If error_dict is present, resolution failed (not_found or ambiguous).
    """
    if not candidates:
        return None, {"status": "not_found", "message": f"No {entity_name}s exist."}

    # 1. Exact ID check (integer or string UUID)
    raw_str = str(query).strip().lstrip("#")
    for item in candidates:
        item_id = item.get("id")
        if item_id is not None:
            if str(item_id) == raw_str or (raw_str.isdigit() and item_id == int(raw_str)):
                return item, None

    # 2. String query check against title / name / text / content
    query_str = str(query).strip().lower()
    query_norm = _normalize_tech_text(query_str)
    if not query_str:
        return None, {"status": "not_found", "message": f"Empty reference for {entity_name}."}

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        candidate_text = str(
            item.get(title_key)
            or item.get("title")
            or item.get("name")
            or item.get("text")
            or item.get("content")
            or ""
        ).strip()
        if not candidate_text:
            continue
        cand_lower = candidate_text.lower()
        cand_norm = _normalize_tech_text(cand_lower)
        # Check exact case-insensitive or tech-normalized match
        if cand_lower == query_str or (query_norm and cand_norm == query_norm):
            return item, None
        raw_score = float(rapidfuzz.fuzz.token_set_ratio(query_str, cand_lower))
        norm_score = (
            float(rapidfuzz.fuzz.token_set_ratio(query_norm, cand_norm))
            if (query_norm and cand_norm)
            else 0.0
        )
        score = max(raw_score, norm_score)
        scored.append((score, item))

    if not scored:
        return None, {"status": "not_found", "message": f"No {entity_name} found matching '{query}'."}

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_item = scored[0]

    # Weak match refusal
    if top_score < 70.0:
        return None, {"status": "not_found", "message": f"No {entity_name} found matching '{query}' (best match {top_score:.0f}% < 70%)."}

    # Check ambiguity: second candidate >= 70 and gap < 10
    if len(scored) > 1:
        second_score, second_item = scored[1]
        if second_score >= 70.0 and (top_score - second_score) < 10.0:
            cands = []
            for s, itm in scored[:3]:
                if s >= 70.0:
                    cands.append({
                        "id": itm.get("id"),
                        "title": itm.get(title_key) or itm.get("name") or itm.get("text") or itm.get("content"),
                        "score": round(s, 1),
                    })
            return None, {
                "status": "ambiguous",
                "message": f"Multiple {entity_name}s matched '{query}'. Please specify which one.",
                "candidates": cands,
            }

    return top_item, None


# --- Tool Executors ---

# 1. Reminders
def _exec_create_reminder(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    when = str(args.get("when", "")).strip()
    recurrence = args.get("recurrence")
    if not title or not when:
        return {"status": "error", "message": "'title' and 'when' are required."}

    try:
        reminder = ctx.deps.create_reminder_unified(
            title=title, when=when, recurrence=recurrence, chat_id=ctx.chat_id
        )
        ctx.ui_actions.append({"type": "refresh", "sections": ["reminders"]})
        ctx.ui_actions.append({"type": "navigate", "page": "reminders", "route": "/reminders"})
        return {
            "status": "ok",
            "reminder": {
                "id": reminder["id"],
                "title": reminder["title"],
                "remind_at": reminder["remind_at"],
                "recurrence": reminder.get("recurrence"),
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _exec_list_reminders(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    rows = ctx.deps.live_reminders()[:15]
    ctx.ui_actions.append({"type": "navigate", "page": "reminders", "route": "/reminders"})
    return {
        "status": "ok",
        "reminders": [
            {
                "id": r["id"],
                "title": r["title"],
                "remind_at": r["remind_at"],
                "recurrence": r.get("recurrence"),
            }
            for r in rows
        ],
    }


def _exec_update_reminder(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    rem_ref = args.get("reminder")
    new_when = args.get("when")
    new_title = args.get("title")
    if not new_when and not new_title:
        return {"status": "error", "message": "At least one of 'when' or 'title' must be provided."}

    live = ctx.deps.live_reminders()
    item, err = resolve_entity(rem_ref, live, title_key="title", entity_name="reminder")
    if err:
        return err

    rem_id = str(item["id"])
    target_iso = None
    if new_when:
        parsed = ctx.deps.parse_reminder_time(str(new_when))
        if parsed is None:
            return {"status": "error", "message": f"Could not parse reminder time: '{new_when}'."}
        target_iso = parsed.isoformat()

    ctx.deps.cancel_reminder_unified(rem_id)
    title_to_use = new_title.strip() if new_title else item["title"]
    updated = ctx.deps.memory_store.create_reminder(
        title_to_use,
        target_iso or item["remind_at"],
        item.get("recurrence"),
        item.get("chat_id") or ctx.chat_id,
    )
    from app import _schedule_reminder
    _schedule_reminder(updated)

    ctx.ui_actions.append({"type": "refresh", "sections": ["reminders"]})
    ctx.ui_actions.append({"type": "navigate", "page": "reminders", "route": "/reminders"})
    return {
        "status": "ok",
        "reminder": {
            "id": updated["id"],
            "title": updated["text"],
            "remind_at": updated["run_at"],
            "recurrence": updated.get("recurrence"),
        },
    }


def _exec_delete_reminder(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    rem_ref = args.get("reminder")
    live = ctx.deps.live_reminders()
    item, err = resolve_entity(rem_ref, live, title_key="title", entity_name="reminder")
    if err:
        return err

    summary = f"Delete the reminder '{item['title']}' (scheduled for {item['remind_at']})?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_reminder",
        target=item,
        summary=summary,
    )


# 2. Tasks
def _parse_due_value(raw_due: Any, ctx: ToolContext) -> str | None:
    if not raw_due:
        return None
    raw_str = str(raw_due).strip()
    if not raw_str:
        return None
    try:
        from services.productivity_parsers import _parse_task_due_date
        parsed_iso = _parse_task_due_date(raw_str)
        if parsed_iso:
            return parsed_iso
    except Exception:
        pass
    parsed = ctx.deps.parse_reminder_time(raw_str)
    return parsed.isoformat() if parsed else None


def _exec_create_task(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"status": "error", "message": "'title' is required."}
    priority = str(args.get("priority", "medium")).lower()
    if priority not in ("low", "medium", "high"):
        priority = "medium"

    due = args.get("due")
    due_iso = _parse_due_value(due, ctx)
    if due_iso is None:
        try:
            from services.productivity_parsers import _extract_task_due_date
            extracted_title, extracted_due = _extract_task_due_date(title)
            if extracted_due and extracted_title:
                title, due_iso = extracted_title, extracted_due
        except Exception:
            pass

    task = ctx.deps.memory_store.create_task(title, priority=priority, due_at=due_iso)
    ctx.deps.run_learning_hook(lambda: ctx.deps.suggest_learning_for_task(task["id"]))

    ctx.ui_actions.append({"type": "refresh", "sections": ["tasks", "gamification"]})
    ctx.ui_actions.append({"type": "navigate", "page": "todos", "route": "/todos"})
    return {
        "status": "ok",
        "task": {
            "id": task["id"],
            "title": task["title"],
            "priority": task["priority"],
            "due_at": task.get("due_at"),
            "completed": bool(task.get("completed")),
        },
    }


def _exec_list_tasks(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    status_filter = str(args.get("status", "pending")).lower()
    include_completed = status_filter in ("completed", "all")
    all_tasks = ctx.deps.memory_store.list_tasks(include_completed=include_completed)

    if status_filter == "completed":
        filtered = [t for t in all_tasks if bool(t.get("completed"))]
    elif status_filter == "pending":
        filtered = [t for t in all_tasks if not bool(t.get("completed"))]
    else:
        filtered = all_tasks

    capped = filtered[:15]
    ctx.ui_actions.append({"type": "navigate", "page": "todos", "route": "/todos"})
    return {
        "status": "ok",
        "tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "priority": t["priority"],
                "due_at": t.get("due_at"),
                "completed": bool(t.get("completed")),
            }
            for t in capped
        ],
    }


def _exec_update_task(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    task_ref = args.get("task")
    tasks = ctx.deps.memory_store.list_tasks(include_completed=True)
    title = args.get("title")
    priority = args.get("priority")
    completed = args.get("completed")
    due = args.get("due")
    due_iso = _parse_due_value(due, ctx) if due else None

    if str(task_ref).strip().lower() in ("all", "all tasks", "all my tasks", "everything", "*") and (
        completed is not None or priority is not None or due_iso is not None
    ):
        if not tasks:
            return {"status": "ok", "message": "No tasks set up yet.", "tasks": [], "count": 0}
        updated_list = []
        for t in tasks:
            u = ctx.deps.memory_store.update_task(
                task_id=t["id"],
                priority=str(priority).lower() if priority else None,
                due_at=due_iso,
                completed=bool(completed) if completed is not None else None,
            )
            updated_list.append({
                "id": u["id"],
                "title": u["title"],
                "priority": u["priority"],
                "due_at": u.get("due_at"),
                "completed": bool(u.get("completed")),
            })
        ctx.ui_actions.append({"type": "refresh", "sections": ["tasks", "gamification"]})
        ctx.ui_actions.append({"type": "navigate", "page": "todos", "route": "/todos"})
        return {"status": "ok", "tasks": updated_list, "count": len(updated_list)}

    item, err = resolve_entity(task_ref, tasks, title_key="title", entity_name="task")
    if err:
        return err

    was_completed = bool(item.get("completed"))
    updated = ctx.deps.memory_store.update_task(
        task_id=item["id"],
        title=str(title).strip() if title else None,
        priority=str(priority).lower() if priority else None,
        due_at=due_iso,
        completed=bool(completed) if completed is not None else None,
    )
    if completed and not was_completed:
        try:
            import app as _app_mod
            ctx.deps.run_learning_hook(lambda: _app_mod._learning_on_task_completed(item["id"]))
        except Exception:
            pass

    ctx.ui_actions.append({"type": "refresh", "sections": ["tasks", "gamification"]})
    ctx.ui_actions.append({"type": "navigate", "page": "todos", "route": "/todos"})
    return {
        "status": "ok",
        "task": {
            "id": updated["id"],
            "title": updated["title"],
            "priority": updated["priority"],
            "due_at": updated.get("due_at"),
            "completed": bool(updated.get("completed")),
        },
    }


def _exec_delete_task(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    task_ref = args.get("task")
    tasks = ctx.deps.memory_store.list_tasks(include_completed=True)
    item, err = resolve_entity(task_ref, tasks, title_key="title", entity_name="task")
    if err:
        if err.get("status") == "not_found":
            habits = ctx.deps.memory_store.list_habits()
            h_item, _ = resolve_entity(task_ref, habits, title_key="name", entity_name="habit")
            if h_item:
                err = {
                    **err,
                    "message": f"{err['message']} Note: a habit named '{h_item['name']}' exists — use delete_habit if the user meant that habit.",
                }
        return err

    summary = f"Delete the task '{item['title']}'?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_task",
        target=item,
        summary=summary,
    )


# 3. Habits
def _exec_create_habit(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"status": "error", "message": "'name' is required."}
    daily_goal = int(args.get("daily_goal", 1))

    habit = ctx.deps.memory_store.create_habit(name=name, daily_goal=daily_goal)
    ctx.ui_actions.append({"type": "refresh", "sections": ["habits", "gamification"]})
    ctx.ui_actions.append({"type": "navigate", "page": "habits", "route": "/habits"})
    return {
        "status": "ok",
        "habit": {
            "id": habit["id"],
            "name": habit["name"],
            "streak": habit.get("streak", 0),
            "daily_goal": habit.get("daily_goal", 1),
        },
    }


def _exec_list_habits(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    habits = ctx.deps.memory_store.list_habits()[:15]
    today = datetime.now(ctx.deps.local_timezone).date().isoformat()
    ctx.ui_actions.append({"type": "navigate", "page": "habits", "route": "/habits"})
    return {
        "status": "ok",
        "habits": [
            {
                "id": h["id"],
                "name": h["name"],
                "streak": h.get("streak", 0),
                "completed_today": today in h.get("completed_dates", []),
            }
            for h in habits
        ],
    }


def _exec_complete_habit(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    habit_ref = args.get("habit")
    habits = ctx.deps.memory_store.list_habits()
    today = datetime.now(ctx.deps.local_timezone).date().isoformat()
    date_str = str(args.get("date", today))
    completed = bool(args.get("completed", True))

    if str(habit_ref).strip().lower() in ("all", "all habits", "all my habits", "everything", "*"):
        if not habits:
            return {"status": "ok", "message": "No habits set up yet.", "habits": [], "count": 0}
        updated_list = []
        for h in habits:
            u = ctx.deps.memory_store.set_habit_completion(h["id"], date_str, completed)
            updated_list.append({
                "id": u["id"],
                "name": u["name"],
                "streak": u.get("streak", 0),
                "completed": completed,
                "date": date_str,
            })
        ctx.ui_actions.append({"type": "refresh", "sections": ["habits", "gamification"]})
        ctx.ui_actions.append({"type": "navigate", "page": "habits", "route": "/habits"})
        return {"status": "ok", "habits": updated_list, "count": len(updated_list)}

    item, err = resolve_entity(habit_ref, habits, title_key="name", entity_name="habit")
    if err:
        return err

    updated = ctx.deps.memory_store.set_habit_completion(item["id"], date_str, completed)
    ctx.ui_actions.append({"type": "refresh", "sections": ["habits", "gamification"]})
    ctx.ui_actions.append({"type": "navigate", "page": "habits", "route": "/habits"})
    return {
        "status": "ok",
        "habit": {
            "id": updated["id"],
            "name": updated["name"],
            "streak": updated.get("streak", 0),
            "completed": completed,
            "date": date_str,
        },
    }


def _exec_delete_habit(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    habit_ref = args.get("habit")
    habits = ctx.deps.memory_store.list_habits()
    item, err = resolve_entity(habit_ref, habits, title_key="name", entity_name="habit")
    if err:
        return err

    summary = f"Delete the habit '{item['name']}'?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_habit",
        target=item,
        summary=summary,
    )


# 4. Memory and Knowledge
def _exec_save_memory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    content = str(args.get("content", "")).strip()
    if not content:
        return {"status": "error", "message": "'content' is required."}

    try:
        mem = ctx.deps.memory_store.add_memory(content)
        ctx.ui_actions.append({"type": "refresh", "sections": ["memories"]})
        ctx.ui_actions.append({"type": "navigate", "page": "reminders", "route": "/reminders"})
        return {
            "status": "ok",
            "memory": {
                "id": mem["id"],
                "content": mem["content"],
            },
        }
    except ValueError as exc:
        if "already exists" in str(exc).lower():
            # Treat idempotently as success rather than throwing error
            existing = [m for m in ctx.deps.memory_store.list_memories() if m["content"].strip().lower() == content.lower()]
            mem_id = existing[0]["id"] if existing else None
            return {
                "status": "ok",
                "message": "Memory already saved.",
                "memory": {"id": mem_id, "content": content},
            }
        return {"status": "error", "message": str(exc)}


def _exec_search_memory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"status": "error", "message": "'query' is required."}

    results = ctx.deps.memory_store.search_memories(query, limit=5)
    ctx.ui_actions.append({"type": "navigate", "page": "reminders", "route": "/reminders"})
    return {
        "status": "ok",
        "results": [
            {"id": m["id"], "content": m["content"], "score": round(m.get("score", 0.0), 3)}
            for m in results
        ],
    }


def _exec_delete_memory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    mem_ref = args.get("memory")
    memories = ctx.deps.memory_store.list_memories()
    item, err = resolve_entity(mem_ref, memories, title_key="content", entity_name="memory")
    if err:
        return err

    summary = f"Delete saved memory: '{item['content'][:60]}'?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_memory",
        target=item,
        summary=summary,
    )


# 5. Insight
def _exec_get_overview(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    tasks = ctx.deps.memory_store.list_tasks(include_completed=False)[:10]
    habits = ctx.deps.memory_store.list_habits()[:10]
    reminders = ctx.deps.live_reminders()[:5]
    gamification = ctx.deps.memory_store.get_gamification()

    today = datetime.now(ctx.deps.local_timezone).date().isoformat()
    learning = {}
    if ctx.deps.learning_schema_initialized():
        try:
            overview = ctx.deps.learning_overall_progress()
            next_t = ctx.deps.learning_next_topics(3)
            learning = {
                "progress": f"{overview.get('completed_topics', 0)}/{overview.get('topic_count', 0)} topics ({overview.get('completion_percent', 0)}%)",
                "next_topics": [t.get("name") for t in next_t],
            }
        except Exception:
            pass

    return {
        "status": "ok",
        "pending_tasks": [{"id": t["id"], "title": t["title"], "priority": t["priority"]} for t in tasks],
        "habits": [{"name": h["name"], "streak": h.get("streak", 0), "done_today": today in h.get("completed_dates", [])} for h in habits],
        "active_reminders": [{"id": r["id"], "title": r["title"], "remind_at": r["remind_at"]} for r in reminders],
        "gamification": {"xp": gamification.get("xp", 0), "global_streak": gamification.get("global_streak", 0)},
        "learning": learning,
    }


# 6. Web and UI
def _exec_web_search(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"status": "error", "message": "'query' is required."}

    ctx.has_called_web_search = True

    try:
        raw_results = ctx.deps.web_search(query, max_results=5)
        formatted = []
        for r in raw_results[:5]:
            snippet = r.get("content") or ""
            formatted.append({
                "title": r.get("title", ""),
                "domain": r.get("domain", ""),
                "snippet": snippet[:200],
                "url": r.get("url", ""),
            })
        return {"status": "ok", "results": formatted}
    except Exception as exc:
        err_msg = str(exc)
        if "not configured" in err_msg.lower() or "missing" in err_msg.lower() or "searchnotconfigured" in type(exc).__name__.lower():
            return {"status": "error", "message": "Web search is not configured."}
        return {"status": "error", "message": f"Search failed: {err_msg}"}


def _exec_navigate(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.channel not in ("web", "agent"):
        return {"status": "error", "message": "Navigation is only available in the web app."}

    page = str(args.get("page", "")).strip().lower()
    valid_pages = ("dashboard", "habits", "todos", "reminders", "learning", "analytics", "settings")

    # Map aliases like "tasks" -> "todos"
    if page in ("task", "tasks", "todo"):
        page = "todos"
    elif page in ("habit",):
        page = "habits"
    elif page in ("reminder", "notes", "memory", "memories"):
        page = "reminders"
    elif page in ("home", "overview"):
        page = "dashboard"

    if page not in valid_pages:
        return {"status": "error", "message": f"Unknown page '{page}'. Valid pages: {', '.join(valid_pages)}."}

    route = f"/{page}"
    ctx.ui_actions.append({"type": "navigate", "page": page, "route": route})
    return {"status": "ok", "page": page, "route": route}


# 7. Learning and Analytics Management
def _exec_create_learning_roadmap(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"status": "error", "message": "'name' is required."}

    category = str(args.get("category", "technical")).lower()
    if category not in ("academic", "technical", "personal"):
        category = "technical"

    description = str(args.get("description", "")).strip()

    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import progress
    try:
        rm = progress.create_roadmap(name=name, category=category, description=description)
        ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
        ctx.ui_actions.append({"type": "navigate", "page": "learning", "route": "/learning"})
        return {
            "status": "ok",
            "roadmap": {
                "id": rm["id"],
                "name": rm["name"],
                "category": rm["category"],
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _parse_iso_dt(raw: Any, default_tz: Any) -> datetime | None:
    """Parse an ISO timestamp string into a timezone-aware datetime."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz)
        return dt.astimezone(default_tz)
    except Exception:
        return None


_ACRONYMS = {"sql", "dbms", "ai", "ml", "dl", "nlp", "ui", "ux", "dsa", "oop", "api", "rest", "css", "html", "js", "ts", "aws", "gcp", "ci", "cd", "jwt", "llm", "rag", "os", "cn"}


def _clean_roadmap_title(raw_topic: str) -> str:
    """Infer a clean subject roadmap title without mangling acronyms."""
    cleaned = re.sub(
        r"^(?:intro(?:duction)?\s+to|basics?\s+of|fundamentals?\s+of|getting\s+started\s+with|learn(?:ing)?)\s+",
        "",
        raw_topic.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:basics?|fundamentals?|advanced|intro(?:duction)?|course|tutorial|guide|roadmap|essentials?)$",
        "",
        cleaned.strip(),
        flags=re.IGNORECASE,
    ).strip(" -_:")
    if not cleaned:
        cleaned = raw_topic.strip()
    words = []
    for w in cleaned.split():
        low = w.lower().strip(".,()")
        if low in _ACRONYMS:
            words.append(w.upper())
        elif w.isupper() and len(w) > 1:
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _exec_create_learning_Topic_or_match(name: str, summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find best matching existing roadmap by roadmap name or existing topics inside it."""
    from learning import schema
    from rapidfuzz import fuzz

    topic_lower = name.lower()
    best_match = None
    best_score = 0.0

    for s in summaries:
        s_name = s["name"].lower()
        ratio = float(fuzz.partial_ratio(s_name, topic_lower))
        if ratio > best_score:
            best_score = ratio
            best_match = s

    if best_match and best_score >= 65.0:
        return best_match

    # Also check topics inside each roadmap for domain overlap
    try:
        with schema.connect() as conn:
            topic_rows = conn.execute("SELECT roadmap_id, name FROM topics").fetchall()
        by_rm: dict[int, list[str]] = {}
        for r in topic_rows:
            by_rm.setdefault(int(r["roadmap_id"]), []).append(str(r["name"]).lower())
        for s in summaries:
            rm_topics = by_rm.get(int(s["id"]), [])
            for t_name in rm_topics:
                score = float(fuzz.token_set_ratio(topic_lower, t_name))
                if score >= 80.0 and score > best_score:
                    best_score = score
                    best_match = s
    except Exception:
        pass

    return best_match if (best_match and best_score >= 75.0) else None


def _exec_create_learning_topic(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"status": "error", "message": "'name' is required."}

    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import progress
    roadmap_name = args.get("roadmap")
    roadmap_id = None
    target_roadmap_name = None

    summaries = progress.roadmap_summaries()

    # 1. If explicit roadmap specified, find or create it
    if roadmap_name:
        rm = progress.find_roadmap(str(roadmap_name))
        if rm:
            roadmap_id = rm["id"]
            target_roadmap_name = rm["name"]
        else:
            clean_rm = _clean_roadmap_title(str(roadmap_name))
            existing_rm = next((s for s in summaries if s["name"].lower() == clean_rm.lower()), None)
            if existing_rm:
                roadmap_id = existing_rm["id"]
                target_roadmap_name = existing_rm["name"]
            else:
                new_rm = progress.create_roadmap(clean_rm, category="technical")
                roadmap_id = new_rm["id"]
                target_roadmap_name = new_rm["name"]

    # 2. If no roadmap specified, check if existing roadmaps or their topics match
    if roadmap_id is None and summaries:
        matched_rm = _exec_create_learning_Topic_or_match(name, summaries)
        if matched_rm:
            roadmap_id = matched_rm["id"]
            target_roadmap_name = matched_rm["name"]

    # 3. Otherwise, create a dedicated roadmap matching the topic domain
    if roadmap_id is None:
        clean_title = _clean_roadmap_title(name)
        existing_rm = next((s for s in summaries if s["name"].lower() == clean_title.lower()), None)
        if existing_rm:
            roadmap_id = existing_rm["id"]
            target_roadmap_name = existing_rm["name"]
        else:
            new_rm = progress.create_roadmap(clean_title, category="technical")
            roadmap_id = new_rm["id"]
            target_roadmap_name = new_rm["name"]

    prio = int(args.get("priority", 2))
    prio = max(1, min(3, prio))

    try:
        topic = progress.create_topic(
            roadmap_id=roadmap_id,
            name=name,
            description=str(args.get("description", "")).strip(),
            priority=prio,
        )
        ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
        ctx.ui_actions.append({"type": "navigate", "page": "learning", "route": "/learning"})
        return {
            "status": "ok",
            "topic": {
                "id": topic["id"],
                "name": topic["name"],
                "roadmap_id": topic["roadmap_id"],
                "roadmap_name": target_roadmap_name,
                "priority": prio,
                "status": topic["status"],
            },
        }
    except ValueError as exc:
        if "already exists" in str(exc).lower():
            ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
            return {
                "status": "ok",
                "message": "Topic already exists in roadmap.",
                "topic": {"name": name, "roadmap_id": roadmap_id, "roadmap_name": target_roadmap_name},
            }
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _exec_complete_learning_topic(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    topic_ref = args.get("topic")
    if not topic_ref:
        return {"status": "error", "message": "'topic' is required."}

    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import progress, schema
    with schema.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, name, status, roadmap_id FROM topics").fetchall()]

    item, err = resolve_entity(topic_ref, rows, title_key="name", entity_name="topic")
    if err:
        if err.get("status") == "not_found":
            tasks = ctx.deps.memory_store.list_tasks(include_completed=True)
            t_item, _ = resolve_entity(topic_ref, tasks, title_key="title", entity_name="task")
            if t_item:
                err = {
                    **err,
                    "message": (
                        f"{err['message']} However, a TASK exists matching this: "
                        f"#{t_item['id']} '{t_item['title']}' — call update_task with completed=true if the user meant that task."
                    ),
                }
        return err

    if item.get("status") == "completed":
        return {
            "status": "ok",
            "message": f"Topic '{item['name']}' is already marked completed.",
            "topic": {"id": item["id"], "name": item["name"], "status": "completed", "xp_awarded": 0},
        }

    unmet = progress.unavailable_prerequisite_names(item["id"])
    if unmet:
        return {
            "status": "error",
            "message": f"Cannot complete '{item['name']}' yet — complete prerequisites first: {', '.join(unmet)}.",
        }

    try:
        progress.set_topic_status(item["id"], "completed")
        xp_awarded = 0
        if hasattr(ctx.deps.memory_store, "award_xp"):
            ctx.deps.memory_store.award_xp(25, reason=f"Completed learning topic: {item['name']}")
            xp_awarded = 25

        ctx.ui_actions.append({"type": "refresh", "sections": ["learning", "gamification"]})
        ctx.ui_actions.append({"type": "navigate", "page": "learning", "route": "/learning"})
        return {
            "status": "ok",
            "topic": {
                "id": item["id"],
                "name": item["name"],
                "status": "completed",
                "xp_awarded": xp_awarded,
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _exec_delete_learning_roadmap(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    rm_ref = args.get("roadmap")
    if not rm_ref:
        return {"status": "error", "message": "'roadmap' is required."}

    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import progress
    summaries = progress.roadmap_summaries()
    item, err = resolve_entity(rm_ref, summaries, title_key="name", entity_name="roadmap")
    if err:
        return err

    summary = f"Delete the learning roadmap '{item['name']}' and all its topics?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_learning_roadmap",
        target=item,
        summary=summary,
    )


def _exec_delete_learning_topic(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.has_called_web_search:
        return {"status": "error", "message": "Destructive operations are forbidden in the same turn as web search."}

    topic_ref = args.get("topic")
    if not topic_ref:
        return {"status": "error", "message": "'topic' is required."}

    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import schema
    with schema.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, name, status, roadmap_id FROM topics").fetchall()]

    item, err = resolve_entity(topic_ref, rows, title_key="name", entity_name="topic")
    if err:
        if err.get("status") == "not_found":
            tasks = ctx.deps.memory_store.list_tasks(include_completed=True)
            t_item, _ = resolve_entity(topic_ref, tasks, title_key="title", entity_name="task")
            if t_item:
                err = {
                    **err,
                    "message": (
                        f"{err['message']} However, a TASK exists matching this: "
                        f"#{t_item['id']} '{t_item['title']}' — call delete_task instead if the user meant that task."
                    ),
                }
        return err

    summary = f"Delete the learning topic '{item['name']}'?"
    return ctx.confirm_mgr.request_confirmation(
        chat_id=ctx.chat_id,
        tool_name="delete_learning_topic",
        target=item,
        summary=summary,
    )


def _exec_link_learning_folder(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    folder_path = str(args.get("folder_path", "")).strip()
    roadmap_ref = str(args.get("roadmap", "")).strip()
    if not folder_path or not roadmap_ref:
        return {"status": "error", "message": "'folder_path' and 'roadmap' are required."}
    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import code_rag, progress
    summaries = progress.roadmap_summaries()
    rm = progress.find_roadmap(roadmap_ref)
    if rm is None:
        rm, err = resolve_entity(roadmap_ref, summaries, title_key="name", entity_name="roadmap")
        if err:
            return err

    try:
        res = code_rag.link_folder_to_roadmap(
            int(rm["id"]),
            folder_path,
            sync_now=True,
            embed=getattr(ctx.deps.memory_store, "embed", None),
        )
        ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
        sync_info = res.get("sync") or {}
        return {
            "status": "ok",
            "roadmap_name": rm["name"],
            "folder_path": (res.get("folder") or {}).get("folder_path", folder_path),
            "total_files": sync_info.get("total_files", 0),
            "practiced_files": sync_info.get("practiced_files", 0),
            "empty_files": sync_info.get("empty_files", 0),
            "pending_suggestions": sync_info.get("pending_suggestions", 0),
            "friendly_summary": sync_info.get("friendly_summary", ""),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _exec_sync_learning_folder(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import code_rag, progress
    roadmap_ref = str(args.get("roadmap") or "").strip()
    embed = getattr(ctx.deps.memory_store, "embed", None)

    if roadmap_ref:
        rm = progress.find_roadmap(roadmap_ref)
        if rm is None:
            rm, err = resolve_entity(
                roadmap_ref, progress.roadmap_summaries(), title_key="name", entity_name="roadmap"
            )
            if err:
                return err
        try:
            res = code_rag.sync_roadmap_folder(int(rm["id"]), embed=embed)
            insights = code_rag.get_roadmap_code_insights(int(rm["id"]))
            ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
            return {
                "status": "ok",
                "roadmap_name": res["roadmap_name"],
                "practiced_files": res["practiced_files"],
                "empty_files": insights["empty_files"],
                "pending_suggestions": [
                    {"id": s["id"], "topic": s["topic_name"], "reason": s["reason"]}
                    for s in insights["pending_suggestions"]
                ],
                "next_topics": [t["name"] for t in insights["next_topics"]],
                "friendly_summary": res["friendly_summary"],
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    results = code_rag.sync_all_linked_folders(embed=embed)
    if not results:
        return {
            "status": "ok",
            "message": "No learning folders are linked yet. Tell me a folder path and roadmap to link.",
        }
    ctx.ui_actions.append({"type": "refresh", "sections": ["learning"]})
    ctx.ui_actions.append({"type": "navigate", "page": "learning", "route": "/learning"})
    return {
        "status": "ok",
        "synced": [
            {
                "roadmap_name": r.get("roadmap_name"),
                "practiced_files": r.get("practiced_files", 0),
                "empty_files": r.get("empty_files", 0),
                "pending_suggestions": r.get("pending_suggestions", 0),
                "friendly_summary": r.get("friendly_summary", ""),
                "error": r.get("error"),
            }
            for r in results
        ],
    }


def _exec_search_learning_code(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"status": "error", "message": "'query' is required."}
    if not ctx.deps.learning_schema_initialized():
        return {"status": "error", "message": "Learning schema is not initialized."}

    from learning import code_rag, progress
    roadmap_id = None
    roadmap_ref = str(args.get("roadmap") or "").strip()
    if roadmap_ref:
        rm = progress.find_roadmap(roadmap_ref)
        if rm:
            roadmap_id = int(rm["id"])

    hits = code_rag.search_code_rag(
        query,
        roadmap_id=roadmap_id,
        limit=4,
        embed=getattr(ctx.deps.memory_store, "embed", None),
    )
    ctx.ui_actions.append({"type": "navigate", "page": "learning", "route": "/learning"})
    return {
        "status": "ok",
        "query": query,
        "results": [
            {
                "file": h["rel_path"],
                "lines": f"L{h['start_line']}-L{h['end_line']}",
                "state": h["file_state"],
                "roadmap": h["roadmap_name"],
                "snippet": h["snippet"][:450],
            }
            for h in hits
        ],
    }


def _exec_get_analytics(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    period = str(args.get("period", "week")).lower()
    category = str(args.get("category", "all")).lower()

    from datetime import timedelta
    tz = ctx.deps.local_timezone
    now = datetime.now(tz)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # week
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    result: dict[str, Any] = {"status": "ok", "period": period}

    if category in ("tasks", "all"):
        all_tasks = ctx.deps.memory_store.list_tasks(include_completed=True)
        completed = [
            t for t in all_tasks
            if t.get("completed") and (_parse_iso_dt(t.get("completed_at"), tz) or start) >= start
        ]
        created = [
            t for t in all_tasks
            if (_parse_iso_dt(t.get("created_at"), tz) or start) >= start
        ]
        result["tasks"] = {
            "completed": len(completed),
            "created": len(created),
            "pending": len([t for t in all_tasks if not t.get("completed")]),
        }

    if category in ("habits", "all"):
        habits = ctx.deps.memory_store.list_habits()
        today_str = now.date().isoformat()
        done_today = sum(1 for h in habits if today_str in h.get("completed_dates", []))
        result["habits"] = {
            "total": len(habits),
            "done_today": done_today,
            "streaks": [{"name": h["name"], "streak": h.get("streak", 0)} for h in habits[:5]],
        }

    gamification = ctx.deps.memory_store.get_gamification()
    result["gamification"] = {
        "xp": gamification.get("xp", 0),
        "global_streak": gamification.get("global_streak", 0),
    }

    ctx.ui_actions.append({"type": "navigate", "page": "analytics", "route": "/analytics"})
    return result


def _exec_batch_update_tasks(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    action = str(args.get("action", "")).lower()
    filter_type = str(args.get("filter", "all_completed" if action in ("reopen", "uncomplete") else "all_pending")).lower()
    new_due = args.get("new_due")

    if action not in ("reschedule", "complete", "reopen", "uncomplete"):
        return {"status": "error", "message": "Action must be 'reschedule', 'complete', 'reopen', or 'uncomplete'."}

    include_completed = action in ("reopen", "uncomplete") or filter_type in ("all_completed", "all")
    tasks = ctx.deps.memory_store.list_tasks(include_completed=include_completed)
    tz = ctx.deps.local_timezone
    now = datetime.now(tz)

    if filter_type == "overdue":
        targets = []
        for t in tasks:
            due_dt = _parse_iso_dt(t.get("due_at"), tz)
            if due_dt is not None and due_dt < now and not t.get("completed"):
                targets.append(t)
    elif filter_type == "high_priority":
        targets = [t for t in tasks if str(t.get("priority", "")).lower() == "high"]
    elif filter_type == "all_completed":
        targets = [t for t in tasks if bool(t.get("completed"))]
    elif filter_type == "all_pending":
        targets = [t for t in tasks if not bool(t.get("completed"))]
    else:
        targets = tasks

    if not targets:
        return {"status": "ok", "message": f"No tasks found matching filter '{filter_type}'.", "count": 0}

    due_iso = None
    if action == "reschedule":
        if not new_due:
            return {"status": "error", "message": "'new_due' is required when action is 'reschedule'."}
        parsed = ctx.deps.parse_reminder_time(str(new_due))
        if not parsed:
            return {"status": "error", "message": f"Could not parse new due time '{new_due}'."}
        due_iso = parsed.isoformat()

    updated_count = 0
    for t in targets:
        if action == "reschedule":
            ctx.deps.memory_store.update_task(t["id"], due_at=due_iso)
            updated_count += 1
        elif action == "complete":
            ctx.deps.memory_store.update_task(t["id"], completed=True)
            updated_count += 1
        elif action in ("reopen", "uncomplete"):
            ctx.deps.memory_store.update_task(t["id"], completed=False)
            updated_count += 1

    ctx.ui_actions.append({"type": "refresh", "sections": ["tasks", "gamification"]})
    ctx.ui_actions.append({"type": "navigate", "page": "todos", "route": "/todos"})
    return {
        "status": "ok",
        "action": action,
        "filter": filter_type,
        "count": updated_count,
    }


def _exec_control_ui(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    action_type = str(args.get("action_type", "")).strip().lower()
    valid_actions = ("apply_filter", "highlight_item", "open_modal", "show_toast")
    if action_type not in valid_actions:
        return {"status": "error", "message": f"Action type must be one of: {', '.join(valid_actions)}."}

    target = args.get("target")
    value = args.get("value")
    message = args.get("message")

    payload: dict[str, Any] = {"type": action_type}
    if target:
        payload["target"] = target
    if value is not None:
        payload["value"] = value
    if message:
        payload["message"] = message

    ctx.ui_actions.append(payload)
    return {"status": "ok", "action": payload}


# --- Tool Registry Definition ---

def _exec_check_email(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Read-only, spam-filtered Gmail inbox digest."""
    from services import gmail_reader

    if not gmail_reader.is_connected():
        return {"status": "error", "message": gmail_reader.email_digest_text()}
    try:
        result = gmail_reader.fetch_inbox(
            max_results=int(args.get("max_results") or 6),
            include_read=bool(args.get("include_read", False)),
        )
    except Exception as exc:
        return {"status": "error", "message": f"Could not reach Gmail: {exc}"}
    emails = [
        {
            "from": e.get("from_name"),
            "subject": e.get("subject"),
            "snippet": (e.get("snippet") or "")[:160],
            "received": e.get("received"),
            "important": "IMPORTANT" in (e.get("labels") or []),
        }
        for e in result.get("emails") or []
    ]
    return {
        "status": "ok",
        "emails": emails,
        "filtered_spam_count": result.get("filtered_count", 0),
        "summary": gmail_reader.format_email_summary(result),
    }


TOOLS: list[ToolDefinition] = [
    # Reminders
    ToolDefinition(
        name="create_reminder",
        description="Schedule a reminder using natural language time (e.g. in 10 minutes, tomorrow at 9am).",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What to be reminded about."},
                "when": {"type": "string", "description": "Natural language time (e.g. 'in 5 minutes', 'tomorrow 3pm')."},
                "recurrence": {"type": "string", "description": "Optional recurring pattern (e.g. 'every day', 'every 2 hours')."},
            },
            "required": ["title", "when"],
        },
        destructive=False,
        executor=_exec_create_reminder,
    ),
    ToolDefinition(
        name="list_reminders",
        description="List active scheduled reminders with their times.",
        parameters={"type": "object", "properties": {}},
        destructive=False,
        executor=_exec_list_reminders,
    ),
    ToolDefinition(
        name="update_reminder",
        description="Reschedule or rename an existing reminder by ID or title.",
        parameters={
            "type": "object",
            "properties": {
                "reminder": {"type": "string", "description": "Reminder ID or title."},
                "when": {"type": "string", "description": "New natural language time."},
                "title": {"type": "string", "description": "New title."},
            },
            "required": ["reminder"],
        },
        destructive=False,
        executor=_exec_update_reminder,
    ),
    ToolDefinition(
        name="delete_reminder",
        description="Delete a reminder by ID or title (requires user confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "reminder": {"type": "string", "description": "Reminder ID or title to delete."},
            },
            "required": ["reminder"],
        },
        destructive=True,
        executor=_exec_delete_reminder,
    ),
    # Tasks
    ToolDefinition(
        name="create_task",
        description="Create a new task with optional priority and due time.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task description or title."},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "description": "Priority level."},
                "due": {"type": "string", "description": "Optional natural language due date/time."},
            },
            "required": ["title"],
        },
        destructive=False,
        executor=_exec_create_task,
    ),
    ToolDefinition(
        name="list_tasks",
        description="List tasks filtered by status (pending, completed, or all).",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "completed", "all"], "description": "Task status filter."},
            },
        },
        destructive=False,
        executor=_exec_list_tasks,
    ),
    ToolDefinition(
        name="update_task",
        description="Update a task's title, priority, due date, or completion status (pass task='all' to update all tasks).",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task ID, title, or 'all' for all tasks."},
                "title": {"type": "string", "description": "New task title."},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "description": "New priority."},
                "due": {"type": "string", "description": "New due date/time (e.g. '20-11-2026', 'tomorrow')."},
                "completed": {"type": "boolean", "description": "Set task completed status (true for completed, false to reopen/unmark)."},
            },
            "required": ["task"],
        },
        destructive=False,
        executor=_exec_update_task,
    ),
    ToolDefinition(
        name="delete_task",
        description="Delete a task by ID or title (requires user confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task ID or title to delete."},
            },
            "required": ["task"],
        },
        destructive=True,
        executor=_exec_delete_task,
    ),
    # Habits
    ToolDefinition(
        name="create_habit",
        description="Create a new daily habit to track.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the habit."},
                "daily_goal": {"type": "integer", "description": "Daily target count."},
            },
            "required": ["name"],
        },
        destructive=False,
        executor=_exec_create_habit,
    ),
    ToolDefinition(
        name="list_habits",
        description="List all habits with their streaks and today's completion status.",
        parameters={"type": "object", "properties": {}},
        destructive=False,
        executor=_exec_list_habits,
    ),
    ToolDefinition(
        name="complete_habit",
        description="Mark a habit (or 'all' for all habits) completed or uncompleted for today or a specific date.",
        parameters={
            "type": "object",
            "properties": {
                "habit": {"type": "string", "description": "Habit ID, name, or 'all' for all habits."},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format (defaults to today)."},
                "completed": {"type": "boolean", "description": "True to mark complete, false to unmark."},
            },
            "required": ["habit"],
        },
        destructive=False,
        executor=_exec_complete_habit,
    ),
    ToolDefinition(
        name="delete_habit",
        description="Delete a habit by ID or name (requires user confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "habit": {"type": "string", "description": "Habit ID or name to delete."},
            },
            "required": ["habit"],
        },
        destructive=True,
        executor=_exec_delete_habit,
    ),
    # Memory and Knowledge
    ToolDefinition(
        name="save_memory",
        description="Save durable facts or preferences the user states about themselves.",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact or preference to remember."},
            },
            "required": ["content"],
        },
        destructive=False,
        executor=_exec_save_memory,
    ),
    ToolDefinition(
        name="search_memory",
        description="Search saved memories. ONLY source for facts about the user.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords or question to search memory."},
            },
            "required": ["query"],
        },
        destructive=False,
        executor=_exec_search_memory,
    ),
    ToolDefinition(
        name="delete_memory",
        description="Delete a saved memory by ID or content excerpt (requires confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "memory": {"type": "string", "description": "Memory ID or text excerpt."},
            },
            "required": ["memory"],
        },
        destructive=True,
        executor=_exec_delete_memory,
    ),
    # Insight
    ToolDefinition(
        name="get_overview",
        description="Get a compact snapshot of pending tasks, habits, reminders, XP, and learning.",
        parameters={"type": "object", "properties": {}},
        destructive=False,
        executor=_exec_get_overview,
    ),
    # Web and UI
    ToolDefinition(
        name="web_search",
        description="Search the web for up-to-date information, news, or articles.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string."},
            },
            "required": ["query"],
        },
        destructive=False,
        executor=_exec_web_search,
    ),
    ToolDefinition(
        name="navigate",
        description="Open a section in the web app (dashboard, habits, todos, reminders, learning, analytics, settings).",
        parameters={
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "enum": ["dashboard", "habits", "todos", "reminders", "learning", "analytics", "settings"],
                    "description": "Page to open.",
                },
            },
            "required": ["page"],
        },
        destructive=False,
        executor=_exec_navigate,
    ),
    # Learning & Progress Management
    ToolDefinition(
        name="create_learning_roadmap",
        description="Create a new dedicated study roadmap (e.g. Machine Learning, Python).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Roadmap title."},
                "category": {"type": "string", "enum": ["academic", "technical", "personal"], "description": "Roadmap category."},
                "description": {"type": "string", "description": "Optional roadmap goal or description."},
            },
            "required": ["name"],
        },
        destructive=False,
        executor=_exec_create_learning_roadmap,
    ),
    ToolDefinition(
        name="create_learning_topic",
        description="Add a new topic to study under a learning roadmap or as a new subject.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Topic name to learn."},
                "roadmap": {"type": "string", "description": "Optional name or ID of roadmap."},
                "description": {"type": "string", "description": "Optional description of topic."},
                "priority": {"type": "integer", "description": "Priority: 1 (low), 2 (medium), or 3 (high)."},
            },
            "required": ["name"],
        },
        destructive=False,
        executor=_exec_create_learning_topic,
    ),
    ToolDefinition(
        name="complete_learning_topic",
        description="Mark a learning topic as completed and earn XP.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name or ID to mark completed."},
            },
            "required": ["topic"],
        },
        destructive=False,
        executor=_exec_complete_learning_topic,
    ),
    ToolDefinition(
        name="delete_learning_roadmap",
        description="Delete a learning roadmap by ID or title (requires user confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "roadmap": {"type": "string", "description": "Roadmap ID or name to delete."},
            },
            "required": ["roadmap"],
        },
        destructive=True,
        executor=_exec_delete_learning_roadmap,
    ),
    ToolDefinition(
        name="delete_learning_topic",
        description="Delete a learning topic by ID or name (requires user confirmation).",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic ID or name to delete."},
            },
            "required": ["topic"],
        },
        destructive=True,
        executor=_exec_delete_learning_topic,
    ),
    ToolDefinition(
        name="link_learning_folder",
        description="Link a local code folder to a learning roadmap and analyze/index its code files.",
        parameters={
            "type": "object",
            "properties": {
                "folder_path": {"type": "string", "description": "Absolute path to local learning folder."},
                "roadmap": {"type": "string", "description": "Target roadmap name or ID."},
            },
            "required": ["folder_path", "roadmap"],
        },
        destructive=False,
        executor=_exec_link_learning_folder,
    ),
    ToolDefinition(
        name="sync_learning_folder",
        description="Analyze linked learning code folder(s) to track progress, unfinished files, and what to learn next.",
        parameters={
            "type": "object",
            "properties": {
                "roadmap": {"type": "string", "description": "Optional roadmap name or ID to sync."},
            },
        },
        destructive=False,
        executor=_exec_sync_learning_folder,
    ),
    ToolDefinition(
        name="search_learning_code",
        description="Search the user's indexed practice code files (RAG) by concept, filename, or code snippet.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Concept, topic, or code question to search."},
                "roadmap": {"type": "string", "description": "Optional roadmap name to scope search."},
            },
            "required": ["query"],
        },
        destructive=False,
        executor=_exec_search_learning_code,
    ),
    # Analytics & Batch Operations
    ToolDefinition(
        name="get_analytics",
        description="Get productivity statistics and summaries across tasks and habits.",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["today", "week", "month"], "description": "Time window."},
                "category": {"type": "string", "enum": ["tasks", "habits", "all"], "description": "Category to filter."},
            },
        },
        destructive=False,
        executor=_exec_get_analytics,
    ),
    ToolDefinition(
        name="batch_update_tasks",
        description="Batch reschedule, complete, or reopen/uncomplete multiple tasks matching a filter (overdue, high_priority, all_pending, all_completed, all).",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["reschedule", "complete", "reopen", "uncomplete"], "description": "Batch operation."},
                "filter": {"type": "string", "enum": ["overdue", "high_priority", "all_pending", "all_completed", "all"], "description": "Filter criteria."},
                "new_due": {"type": "string", "description": "New due time if action is reschedule."},
            },
            "required": ["action"],
        },
        destructive=False,
        executor=_exec_batch_update_tasks,
    ),
    # UI Control
    ToolDefinition(
        name="control_ui",
        description="Trigger frontend UI interactions like filtering lists, highlighting elements, or showing toasts.",
        parameters={
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": ["apply_filter", "highlight_item", "open_modal", "show_toast"], "description": "UI action to invoke."},
                "target": {"type": "string", "description": "Target UI section or element identifier."},
                "value": {"type": "string", "description": "Value or parameter for the UI action."},
                "message": {"type": "string", "description": "Notification message if showing toast."},
            },
            "required": ["action_type"],
        },
        destructive=False,
        executor=_exec_control_ui,
    ),
    # Email (read-only)
    ToolDefinition(
        name="check_email",
        description="Read the user's recent unread Gmail inbox (read-only), with spam and promotions filtered out.",
        parameters={
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "How many emails to return (1-20)."},
                "include_read": {"type": "boolean", "description": "Also include already-read emails from today."},
            },
        },
        destructive=False,
        executor=_exec_check_email,
    ),
]

TOOL_REGISTRY: dict[str, ToolDefinition] = {t.name: t for t in TOOLS}


# --- Argument Validation and Execution Dispatch ---

def validate_and_execute_tool(
    tool_name: str,
    raw_args: Any,
    ctx: ToolContext,
) -> dict[str, Any]:
    """Validate tool arguments against JSON schema and execute the tool.

    Returns a small result dict:
        {"status": "ok" | "error" | "not_found" | "ambiguous" | "needs_confirmation", ...}
    """
    tool_def = TOOL_REGISTRY.get(tool_name)
    if not tool_def:
        return {"status": "error", "message": f"Unknown tool '{tool_name}'."}

    if not isinstance(raw_args, dict):
        return {"status": "error", "message": "Tool arguments must be a JSON object."}

    schema = tool_def.parameters
    props = schema.get("properties", {})
    required = schema.get("required", [])

    # Check required keys
    for req_key in required:
        if req_key not in raw_args or raw_args[req_key] is None or (isinstance(raw_args[req_key], str) and not raw_args[req_key].strip()):
            return {"status": "error", "message": f"Missing required parameter '{req_key}' for tool '{tool_name}'."}

    # Strip unknown keys and validate types / enums
    cleaned_args: dict[str, Any] = {}
    for key, val in raw_args.items():
        if key not in props:
            continue  # Strip unknown keys silently

        expected_type = props[key].get("type")
        if expected_type == "string" and not isinstance(val, (str, int, float)):
            return {"status": "error", "message": f"Parameter '{key}' must be a string."}
        elif expected_type == "integer" and not (isinstance(val, int) and not isinstance(val, bool)):
            if isinstance(val, str) and val.isdigit():
                val = int(val)
            else:
                return {"status": "error", "message": f"Parameter '{key}' must be an integer."}
        elif expected_type == "boolean" and not isinstance(val, bool):
            if isinstance(val, str):
                val = val.lower() in ("true", "1", "yes")
            else:
                return {"status": "error", "message": f"Parameter '{key}' must be a boolean."}

        # Check enums
        enums = props[key].get("enum")
        if enums and str(val).lower() not in [e.lower() for e in enums]:
            return {"status": "error", "message": f"Parameter '{key}' must be one of: {', '.join(enums)}."}

        cleaned_args[key] = val

    try:
        return tool_def.executor(cleaned_args, ctx)
    except Exception as exc:
        log.exception("Tool %s execution failed", tool_name)
        return {"status": "error", "message": f"Execution error in {tool_name}: {exc}"}

