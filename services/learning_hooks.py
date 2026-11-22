"""Learning module lifecycle hooks and weekly nudge scheduling."""

from __future__ import annotations

import os
import threading

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

def _app():
    import app

    return app


def _learning_suggest_for_task(task_id: int) -> None:
    """Background hook: propose topic links for a freshly created task."""
    if not _app().learning_schema.is_initialized():
        return
    try:
        _app().learning_classifier.suggest_links_for_task(
            task_id,
            embed=_app().memory_store.embed,
            llm=_app()._fallback_llm_for_learning,
        )
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning link suggestion skipped: %s", error)


def _fallback_llm_for_learning(title: str, topics) -> str | None:
    """Ask the local model to name the best topic; skip when not loaded."""
    if not _app()._llm_available():
        return None
    numbered = "\n".join(
        f"{index}. {topic['name']}" for index, topic in enumerate(topics, 1)
    )
    prompt = (
        "Pick the single learning topic from the list below that best "
        "matches this task title. Reply with only the exact topic name, "
        "or the word none if nothing fits. No explanation."
        f"\n\nTask title: {title}\n\nTopics:\n{numbered}"
    )
    try:
        reply = _app().generate_response(prompt, 16)
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning LLM fallback skipped: %s", error)
        return None
    return reply or None


def _learning_on_task_completed(task_id: int) -> None:
    """Background hook: apply the completion rule to confirmed topic links."""
    if not _app().learning_schema.is_initialized():
        return
    try:
        _app().learning_progress.on_task_completed_links(task_id)
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning completion rule skipped: %s", error)


def _run_learning_hook(job) -> None:
    """Run a learning-module job off the request path so it can never block
    or break task creation and completion."""
    threading.Thread(target=job, daemon=True).start()


WEEKLY_LEARNING_NUDGE_JOB = "weekly-learning-nudge"
FOLDER_SYNC_JOB = "learning-folder-sync"
DEFAULT_FOLDER_SYNC_MINUTES = int(os.environ.get("ORBIT_FOLDER_SYNC_MINUTES", "2").strip() or "2")


def _notify_new_code_suggestions(sync_results: list[dict]) -> None:
    """When newly added/edited code matches a topic, ask the user in chat whether to mark it completed."""
    a = _app()
    new_items: list[dict] = []
    for res in sync_results:
        for sugg in res.get("new_suggestions") or []:
            new_items.append(sugg)
    if not new_items:
        return
    try:
        chat_ids = a.memory_store.list_local_chat_ids()
        if not chat_ids:
            a._ensure_chat_exists(a.DEFAULT_CHAT_ID)
            chat_ids = [a.DEFAULT_CHAT_ID]
        target_chat = chat_ids[0]

        if len(new_items) == 1:
            s = new_items[0]
            msg = (
                f"Hey! I checked your new code in `{s['files']}` ({s['reason']}) for "
                f"**{s['roadmap_name']}** — looks like you practiced **{s['topic_name']}**. "
                f"Want me to mark **{s['topic_name']}** as completed, or keep it in progress? "
                f"(Say `confirm code suggestion` or click Confirm on the Learning page.)"
            )
            notif_key = f"code-sugg-{s['topic_id']}-{s['files']}"
        else:
            names = ", ".join(f"**{s['topic_name']}** (`{s['files']}`)" for s in new_items[:3])
            msg = (
                f"Hey! I spotted new practice code for {names}. "
                "Want me to mark them completed, or keep them in progress? "
                "(Say `confirm all code suggestions` or review them on the Learning page.)"
            )
            notif_key = f"code-sugg-batch-{new_items[0]['topic_id']}-{len(new_items)}"

        a.memory_store.add_notification(target_chat, notif_key, msg)
        try:
            a._push_reminder_alert({"id": notif_key, "chat_id": target_chat, "text": msg}, msg)
        except Exception:
            pass
    except Exception as error:  # pragma: no cover - defensive
        a.LOGGER.debug("Code suggestion notification skipped: %s", error)


def _sync_learning_folders_background() -> list[dict]:
    """Incrementally sync all linked learning folders off the request path."""
    if not _app().learning_schema.is_initialized():
        return []
    try:
        from learning import code_rag

        embed = getattr(_app().memory_store, "embed", None)
        results = code_rag.sync_all_linked_folders(embed=embed)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            _notify_new_code_suggestions(results)
        return results
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Background learning folder sync skipped: %s", error)
        return []


def _schedule_folder_sync(provider: str = "local") -> None:
    if not _app().learning_schema.is_initialized() or DEFAULT_FOLDER_SYNC_MINUTES <= 0:
        return
    try:
        _app().reminder_scheduler.add_job(
            _sync_learning_folders_background,
            IntervalTrigger(minutes=DEFAULT_FOLDER_SYNC_MINUTES, timezone=_app().LOCAL_TIMEZONE),
            id=FOLDER_SYNC_JOB if provider == "local" else f"{FOLDER_SYNC_JOB}-{provider}",
            replace_existing=True,
        )
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning folder sync schedule skipped: %s", error)


def _weekly_learning_nudge(provider: str = "local") -> None:
    """Monday-morning recap for one provider's chats, at most weekly each."""
    if not _app().learning_schema.is_initialized():
        return
    try:
        if provider == "discord":
            chat_ids = [
                chat["id"] for chat in _app().memory_store.list_external_chats("discord")
            ]
        else:
            chat_ids = _app().memory_store.list_local_chat_ids()
        _app().learning_nudges.deliver_weekly_nudge(
            chat_ids,
            _app().memory_store.add_notification,
            recently_sent=_app().memory_store.has_recent_weekly_nudge,
        )
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Weekly learning nudge skipped: %s", error)


def _schedule_weekly_learning_nudge(provider: str = "local") -> None:
    if not _app().learning_schema.is_initialized():
        return
    try:
        _app().reminder_scheduler.add_job(
            _app()._weekly_learning_nudge,
            CronTrigger(day_of_week="mon", hour=9, minute=0,
                        timezone=_app().LOCAL_TIMEZONE),
            args=[provider],
            id=WEEKLY_LEARNING_NUDGE_JOB if provider == "local" else f"{WEEKLY_LEARNING_NUDGE_JOB}-{provider}",
            replace_existing=True,
        )
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Weekly learning nudge not scheduled: %s", error)


def init_learning_module(provider: str = "local") -> bool:
    """Idempotent. Safe to call from both the web server and the Discord bot."""
    try:
        _app().learning_schema.init(_app().DATABASE_PATH)
        _app().learning_roadmaps.load_seeds()
        _app()._schedule_weekly_learning_nudge(provider)
        _schedule_folder_sync(provider)
        # Run a quick initial non-blocking sync on startup so RAG & insights stay fresh
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            _run_learning_hook(_sync_learning_folders_background)
        return _app().learning_schema.is_initialized()
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning module init skipped: %s", error)
        return False


