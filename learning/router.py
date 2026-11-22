"""HTTP surface of the learning tracker.

Mounted by ``app.py`` with ``app.include_router``. Follows the conventions of
the rest of the API: JSON bodies validated with Pydantic, errors raised as
HTTPException and shaped into ``{"error": "..."}`` by the global handler.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from . import classifier, code_rag, progress, schema

LOGGER = logging.getLogger("spidey.learning.api")

router = APIRouter(prefix="/api/learning", tags=["learning"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_roadmap(roadmap_id: int) -> dict[str, Any]:
    with schema.connect() as connection:
        row = connection.execute(
            "SELECT * FROM roadmaps WHERE id = ?", (roadmap_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Roadmap not found.")
    return dict(row)


def _get_topic(topic_id: int) -> dict[str, Any]:
    with schema.connect() as connection:
        row = connection.execute(
            "SELECT * FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Topic not found.")
    return dict(row)


def _topic_payload(topic: dict[str, Any]) -> dict[str, Any]:
    payload = dict(topic)
    try:
        payload["aliases"] = json.loads(payload.get("aliases") or "[]")
    except (TypeError, ValueError):
        payload["aliases"] = []
    payload.pop("embedding", None)
    return payload


@router.get("/roadmaps")
def list_roadmaps() -> dict[str, Any]:
    return {"roadmaps": progress.roadmap_summaries()}


@router.post("/roadmaps")
def create_roadmap(payload: schema.RoadmapIn = Body(...)) -> dict[str, Any]:
    with schema.connect() as connection:
        existing = connection.execute(
            "SELECT id FROM roadmaps WHERE name = ?", (payload.name,)
        ).fetchone()
        if existing is not None:
            raise HTTPException(400, "A roadmap with that name already exists.")
        cursor = connection.execute(
            "INSERT INTO roadmaps (name, category, description, created_at) "
            "VALUES (?, ?, ?, ?)",
            (payload.name, payload.category, payload.description, _now()),
        )
        roadmap_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM roadmaps WHERE id = ?", (roadmap_id,)
        ).fetchone()
    result = dict(row)
    if payload.topics or payload.auto_subtopics:
        raw_text = payload.topics if isinstance(payload.topics, str) else None
        topic_list = payload.topics if isinstance(payload.topics, list) else None
        imported = progress.import_learning_path(
            name=payload.name,
            raw_text=raw_text,
            topics=topic_list,
            category=payload.category,
            description=payload.description,
            auto_generate_if_empty=bool(payload.auto_subtopics),
        )
        result["added_topics"] = imported["added_topics"]
        result["topic_count"] = imported["topic_count"]
    return result


@router.post("/roadmaps/import")
def import_roadmap(payload: schema.LearningPathImportIn = Body(...)) -> dict[str, Any]:
    """Create or populate a learning roadmap by automatically splitting pasted sub-topics."""
    try:
        res = progress.import_learning_path(
            name=payload.name,
            raw_text=payload.raw_text,
            topics=payload.topics,
            category=payload.category,
            description=payload.description,
            priority=payload.priority,
            auto_generate_if_empty=payload.auto_subtopics,
        )
        try:
            classifier.suggest_links_for_all_open_tasks()
        except Exception:
            pass
        return res
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@router.post("/roadmaps/{roadmap_id}/topics/bulk")
def bulk_create_topics(
    roadmap_id: int, payload: schema.BulkTopicsIn = Body(...)
) -> dict[str, Any]:
    """Bulk-add multiple sub-topics (from pasted lines or list) into an existing roadmap."""
    roadmap = _get_roadmap(roadmap_id)
    try:
        res = progress.import_learning_path(
            name=roadmap["name"],
            raw_text=payload.raw_text,
            topics=payload.topics,
            category=roadmap["category"],
            priority=payload.priority,
            auto_generate_if_empty=False,
        )
        try:
            classifier.suggest_links_for_all_open_tasks()
        except Exception:
            pass
        return res
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@router.patch("/roadmaps/{roadmap_id}")
def update_roadmap(
    roadmap_id: int, payload: schema.RoadmapPatch = Body(...)
) -> dict[str, Any]:
    roadmap = _get_roadmap(roadmap_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return roadmap
    try:
        with schema.connect() as connection:
            if "name" in updates and updates["name"] != roadmap["name"]:
                clash = connection.execute(
                    "SELECT id FROM roadmaps WHERE name = ? AND id != ?",
                    (updates["name"], roadmap_id),
                ).fetchone()
                if clash is not None:
                    raise HTTPException(
                        400, "A roadmap with that name already exists."
                    )
            fields = []
            values: list[Any] = []
            for field in ("name", "category", "description"):
                if field in updates:
                    fields.append(f"{field} = ?")
                    values.append(updates[field])
            values.append(roadmap_id)
            connection.execute(
                f"UPDATE roadmaps SET {', '.join(fields)} WHERE id = ?",
                values,
            )
    except sqlite3.IntegrityError:  # pragma: no cover - defensive
        raise HTTPException(400, "A roadmap with that name already exists.") from None
    return _get_roadmap(roadmap_id)


@router.delete("/roadmaps/{roadmap_id}")
def delete_roadmap(roadmap_id: int) -> dict[str, str]:
    _get_roadmap(roadmap_id)
    with schema.connect() as connection:
        connection.execute("DELETE FROM roadmaps WHERE id = ?", (roadmap_id,))
    return {"status": "deleted"}


@router.get("/roadmaps/{roadmap_id}")
def get_roadmap(roadmap_id: int) -> dict[str, Any]:
    roadmap = _get_roadmap(roadmap_id)
    with schema.connect() as connection:
        topic_rows = connection.execute(
            "SELECT * FROM topics WHERE roadmap_id = ? ORDER BY position, id",
            (roadmap_id,),
        ).fetchall()
    topics = []
    for row in topic_rows:
        topic = _topic_payload(dict(row))
        unmet = progress.unavailable_prerequisite_names(topic["id"])
        topic["available"] = not unmet
        topic["unmet_prerequisites"] = unmet
        topics.append(topic)
    roadmap["topics"] = topics
    return roadmap


@router.post("/topics")
def create_topic(payload: schema.TopicIn = Body(...)) -> dict[str, Any]:
    _get_roadmap(payload.roadmap_id)
    with schema.connect() as connection:
        clash = connection.execute(
            "SELECT id FROM topics WHERE roadmap_id = ? AND name = ?",
            (payload.roadmap_id, payload.name),
        ).fetchone()
        if clash is not None:
            raise HTTPException(400, "A topic with that name already exists.")
        if payload.position is None:
            last = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM topics "
                "WHERE roadmap_id = ?",
                (payload.roadmap_id,),
            ).fetchone()
            position = last["next"]
        else:
            position = payload.position
        for prerequisite_id in payload.requires_topic_ids:
            prerequisite = connection.execute(
                "SELECT roadmap_id FROM topics WHERE id = ?",
                (prerequisite_id,),
            ).fetchone()
            if prerequisite is None:
                raise HTTPException(404, "Prerequisite topic not found.")
            if prerequisite["roadmap_id"] != payload.roadmap_id:
                raise HTTPException(
                    400, "Prerequisites must belong to the same roadmap."
                )
        cursor = connection.execute(
            "INSERT INTO topics (roadmap_id, name, aliases, description, "
            "position, priority, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload.roadmap_id,
                payload.name,
                json.dumps(payload.aliases),
                payload.description,
                position,
                payload.priority,
                payload.status,
                _now(),
            ),
        )
        topic_id = int(cursor.lastrowid)
        for prerequisite_id in payload.requires_topic_ids:
            connection.execute(
                "INSERT OR IGNORE INTO topic_prerequisites (topic_id, "
                "requires_topic_id) VALUES (?, ?)",
                (topic_id, prerequisite_id),
            )
    topic = _get_topic(topic_id)
    if payload.status == "learning":
        progress.log_activity(topic_id, None, "started")
    elif payload.status == "completed":
        progress.log_activity(topic_id, None, "completed")
    return _topic_payload(topic)


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: schema.TopicPatch = Body(...)) -> dict[str, Any]:
    topic = _get_topic(topic_id)
    updates = payload.model_dump(exclude_unset=True)
    if "aliases" in updates and updates["aliases"] is not None:
        updates["aliases"] = json.dumps(updates["aliases"])
    fields = []
    values: list[Any] = []
    for field in (
        "name", "aliases", "description", "position", "priority", "status"
    ):
        if field in updates and updates[field] is not None:
            fields.append(f"{field} = ?")
            values.append(updates[field])
    if not fields:
        return _topic_payload(topic)
    values.append(topic_id)
    with schema.connect() as connection:
        if "name" in updates and updates["name"] != topic["name"]:
            clash = connection.execute(
                "SELECT id FROM topics WHERE roadmap_id = ? AND name = ? "
                "AND id != ?",
                (topic["roadmap_id"], updates["name"], topic_id),
            ).fetchone()
            if clash is not None:
                raise HTTPException(400, "A topic with that name already exists.")
        connection.execute(
            f"UPDATE topics SET {', '.join(fields)}, updated_at = ? "
            "WHERE id = ?",
            (*values[:-1], _now(), topic_id),
        )
    new_status = updates.get("status")
    if new_status and new_status != topic["status"]:
        if new_status == "learning":
            progress.log_activity(topic_id, None, "started")
        elif new_status == "completed":
            progress.log_activity(topic_id, None, "completed")
        elif new_status == "on_hold" and topic["status"] == "learning":
            progress.log_activity(topic_id, None, "postponed")
    return _topic_payload(_get_topic(topic_id))


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int) -> dict[str, str]:
    _get_topic(topic_id)
    with schema.connect() as connection:
        connection.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    return {"status": "deleted"}


@router.get("/topics/{topic_id}/links")
def get_topic_links(topic_id: int) -> dict[str, Any]:
    _get_topic(topic_id)
    links = progress.list_confirmed_task_links(topic_id)
    return {"links": links}


@router.get("/progress")
def get_progress() -> dict[str, Any]:
    return progress.overall_progress()


@router.get("/next")
def get_next(limit: int = Query(progress.NEXT_TOPIC_LIMIT, ge=1, le=20)) -> dict[str, Any]:
    return {"next": progress.next_topics(limit=limit)}


@router.post("/links/scan")
def scan_links() -> dict[str, Any]:
    """Scan all open tasks against open learning topics and return suggested links."""
    created = classifier.suggest_links_for_all_open_tasks()
    return {
        "created": created,
        "links": progress.list_suggested_links(),
    }


@router.get("/links")
def list_links(state: str = Query("suggested")) -> dict[str, Any]:
    if state not in schema.LINK_STATES:
        raise HTTPException(400, f"'state' must be one of {schema.LINK_STATES}.")
    if state != "suggested":
        return {"links": []}
    return {"links": progress.list_suggested_links()}


@router.patch("/links/{link_id}")
def update_link(link_id: int, payload: schema.LinkPatch = Body(...)) -> dict[str, Any]:
    with schema.connect() as connection:
        link = connection.execute(
            "SELECT * FROM task_topic_links WHERE id = ?", (link_id,)
        ).fetchone()
        if link is None:
            raise HTTPException(404, "Link not found.")
        topic_id = payload.topic_id or link["topic_id"]
        topic = connection.execute(
            "SELECT id FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if topic is None:
            raise HTTPException(404, "Topic not found.")
        source = "manual" if payload.topic_id else link["source"]
        connection.execute(
            "UPDATE task_topic_links SET state = ?, topic_id = ?, source = ? "
            "WHERE id = ?",
            (payload.state, topic_id, source, link_id),
        )
    if payload.state == "confirmed":
        # Idempotent by design: log_activity dedupes (topic, task, kind).
        progress.log_activity(topic_id, link["task_id"], "planned")
    with schema.connect() as connection:
        row = connection.execute(
            "SELECT * FROM task_topic_links WHERE id = ?", (link_id,)
        ).fetchone()
    return dict(row)


@router.get("/activity")
def list_activity(limit: int = Query(progress.ACTIVITY_LIMIT, ge=1, le=200)) -> dict[str, Any]:
    return {"activities": progress.list_activities(limit=limit)}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return {"nudges_enabled": progress.nudges_enabled()}


@router.patch("/settings")
def update_settings(payload: schema.SettingsPatch = Body(...)) -> dict[str, Any]:
    progress.set_setting(progress.NUDGES_KEY, "1" if payload.nudges_enabled else "0")
    return {"nudges_enabled": payload.nudges_enabled}


# ---------------------------------------------------------------------------
# Local Folder Auto-Tracking & Hybrid Code RAG Endpoints
# ---------------------------------------------------------------------------


def _shared_embedder():
    try:
        import app

        return app.memory_store.embed
    except Exception:
        return None


@router.get("/folders")
def list_folders() -> dict[str, Any]:
    return {"folders": code_rag.list_folder_links()}


@router.post("/folders/pick")
def pick_folder(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    """Open a native OS folder picker window on the local machine and return the chosen path."""
    initial_dir = (payload or {}).get("initial_dir") if isinstance(payload, dict) else None
    try:
        chosen = code_rag.pick_local_folder(initial_dir=initial_dir)
    except RuntimeError as err:
        raise HTTPException(500, str(err)) from err
    if not chosen:
        return {"cancelled": True, "folder_path": None}
    return {"cancelled": False, "folder_path": chosen}


@router.post("/roadmaps/{roadmap_id}/folder/open")
def open_roadmap_folder(roadmap_id: int) -> dict[str, Any]:
    """Open the roadmap's linked folder in the OS File Explorer."""
    _get_roadmap(roadmap_id)
    link = code_rag.get_folder_link(roadmap_id)
    if link is None:
        raise HTTPException(404, "No folder is linked to this roadmap.")
    try:
        code_rag.open_folder_in_explorer(link["folder_path"])
        return {"status": "opened", "folder_path": link["folder_path"]}
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@router.put("/roadmaps/{roadmap_id}/folder")
def link_roadmap_folder(
    roadmap_id: int, payload: schema.FolderLinkIn = Body(...)
) -> dict[str, Any]:
    _get_roadmap(roadmap_id)
    try:
        return code_rag.link_folder_to_roadmap(
            roadmap_id,
            payload.folder_path,
            enabled=payload.enabled,
            sync_now=True,
            embed=_shared_embedder(),
        )
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@router.delete("/roadmaps/{roadmap_id}/folder")
def unlink_roadmap_folder(roadmap_id: int) -> dict[str, Any]:
    _get_roadmap(roadmap_id)
    removed = code_rag.unlink_folder_from_roadmap(roadmap_id)
    return {"status": "unlinked" if removed else "not_linked"}


@router.post("/roadmaps/{roadmap_id}/sync")
def sync_roadmap_folder(roadmap_id: int) -> dict[str, Any]:
    _get_roadmap(roadmap_id)
    try:
        return code_rag.sync_roadmap_folder(roadmap_id, embed=_shared_embedder())
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@router.post("/folders/sync-all")
def sync_all_folders() -> dict[str, Any]:
    results = code_rag.sync_all_linked_folders(embed=_shared_embedder())
    return {
        "results": results,
        "suggestions": code_rag.list_code_suggestions(state="pending"),
    }


@router.get("/roadmaps/{roadmap_id}/code-insights")
def get_roadmap_code_insights(roadmap_id: int) -> dict[str, Any]:
    _get_roadmap(roadmap_id)
    try:
        return code_rag.get_roadmap_code_insights(roadmap_id)
    except ValueError as err:
        raise HTTPException(404, str(err)) from err


@router.get("/code-suggestions")
def list_code_suggestions(
    roadmap_id: int | None = Query(None),
    state: str = Query("pending"),
) -> dict[str, Any]:
    if state not in schema.CODE_SUGGESTION_STATES:
        raise HTTPException(400, f"'state' must be one of {schema.CODE_SUGGESTION_STATES}.")
    return {
        "suggestions": code_rag.list_code_suggestions(roadmap_id=roadmap_id, state=state)
    }


@router.patch("/code-suggestions/{suggestion_id}")
def patch_code_suggestion(
    suggestion_id: int, payload: schema.CodeSuggestionPatch = Body(...)
) -> dict[str, Any]:
    try:
        updated = code_rag.resolve_code_suggestion(suggestion_id, payload.state)
        if payload.state == "confirmed":
            try:
                import app

                if hasattr(app.memory_store, "award_xp"):
                    app.memory_store.award_xp(
                        25, reason=f"Completed learning topic from code: {updated['topic_name']}"
                    )
            except Exception:
                pass
        return updated
    except ValueError as err:
        raise HTTPException(404, str(err)) from err


@router.post("/rag/search")
def search_code_rag_endpoint(payload: schema.CodeRagQueryIn = Body(...)) -> dict[str, Any]:
    hits = code_rag.search_code_rag(
        payload.query,
        roadmap_id=payload.roadmap_id,
        limit=payload.limit,
        embed=_shared_embedder(),
    )
    return {"query": payload.query, "results": hits}
