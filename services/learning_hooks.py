"""Learning module lifecycle hooks and weekly nudge scheduling."""

from __future__ import annotations

import threading

from apscheduler.triggers.cron import CronTrigger

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
        return _app().learning_schema.is_initialized()
    except Exception as error:  # pragma: no cover - defensive
        _app().LOGGER.debug("Learning module init skipped: %s", error)
        return False


