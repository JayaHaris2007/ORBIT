"""Regression tests ensuring cross-domain intent routing never hijacks other modules."""

from __future__ import annotations

import pytest

import app
from learning import progress as learning_progress, schema as learning_schema


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    db_path = tmp_path / "routing_test.db"
    store = app.MemoryStore(db_path)
    monkeypatch.setattr(app, "memory_store", store)
    learning_schema.init(db_path)
    rm = learning_progress.create_roadmap("Python", category="technical")
    learning_progress.create_topic(rm["id"], "AsyncIO Fundamentals")
    learning_progress.create_topic(rm["id"], "Type Hints & Protocols")
    store.create_habit("Read 20 mins", "BookOpen")
    yield store
    monkeypatch.setattr(learning_schema, "_database_path", None)


@pytest.mark.parametrize(
    "prompt",
    [
        "show my pending to learn next",
        "what is pending to learn",
        "what's pending to learn next",
        "show pending learning",
        "show my pending learning topics",
        "show remaining topics",
        "what is left to learn",
        "what do i have left to study",
        "next in learning",
        "show next to learn",
        "what should i learn next",
        "what should i study next",
        "show my learning goals",
        "show my study plan",
    ],
)
def test_learning_pending_and_next_never_hijacked_by_tasks(clean_env, prompt):
    result = app._handle_local_command(prompt, "test-chat")
    assert result is not None, f"Expected deterministic learning route for: {prompt!r}"
    reply, provider = result
    assert provider == "local-learning", f"Misrouted {prompt!r} to {provider!r}: {reply}"
    assert "task list" not in reply.lower()
    assert "memory list" not in reply.lower()


@pytest.mark.parametrize(
    "prompt,expected_provider",
    [
        ("what's pending today?", "local-task-manager"),
        ("show my pending tasks", "local-task-manager"),
        ("show pending habits", "local-habit-manager"),
        ("check my habits", "local-habit-manager"),
        ("show my pending reminders", "local-scheduler"),
        ("show my saved notes", "local-memory"),
        ("open my learning", "local-navigate:learning"),
        ("open tasks", "local-navigate:tasks"),
        ("open habits", "local-navigate:habits"),
        ("open reminders", "local-navigate:reminders"),
        ("show settings", "local-navigate:settings"),
        ("show analytics", "local-navigate:analytics"),
    ],
)
def test_all_domains_route_to_exact_owner(clean_env, prompt, expected_provider):
    result = app._handle_local_command(prompt, "test-chat")
    assert result is not None, f"No route matched {prompt!r}"
    _, provider = result
    assert provider == expected_provider, f"Expected {expected_provider} for {prompt!r}, got {provider}"
