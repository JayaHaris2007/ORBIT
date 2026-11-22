"""Regression tests for natural deletion phrasings, anti-hallucination confirmation short-circuit,
tech-alias matching (C++ <-> C plus plus), cross-domain hints, and task due dates in tools.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import app
from agent.confirm import ConfirmationManager
from agent.deps import AgentDeps
from agent.loop import run_agent_loop, run_agent_loop_stream
from agent.tools import ToolContext, resolve_entity, validate_and_execute_tool


def _fake_http_response(payload: dict) -> MagicMock:
    raw = json.dumps(payload).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


@pytest.fixture
def chat_id(temp_db):
    chat = temp_db.create_chat(title="Regression Chat")
    return chat["id"]


def test_remove_task_exact_webui_and_discord_phrasings(chat_id, temp_db):
    t1 = temp_db.create_task("learning oops in C++", priority="medium")
    t2 = temp_db.create_task("learning C++ basics", priority="medium")

    # 1. Exact WebUI prompt: "remove learning oops in C++"
    res = app._handle_local_command("remove learning oops in C++", chat_id)
    assert res is not None
    reply, provider = res
    assert provider == "local-task-manager"
    assert "learning oops in C++" in reply
    remaining_ids = [t["id"] for t in temp_db.list_tasks(include_completed=True)]
    assert t1["id"] not in remaining_ids
    assert t2["id"] in remaining_ids


def test_remove_task_with_trailing_in_task_and_cpp_alias(chat_id, temp_db):
    # Stored with spoken STT spelling "C plus plus"
    t1 = temp_db.create_task("learning oops in C plus plus", priority="medium")
    temp_db.create_task("learning C++ basics", priority="medium")

    # Exact Discord prompt using "C++" and trailing "in task"
    res = app._handle_local_command("remove the learning oops in C++ in task", chat_id)
    assert res is not None
    reply, provider = res
    assert provider == "local-task-manager"
    remaining_ids = [t["id"] for t in temp_db.list_tasks(include_completed=True)]
    assert t1["id"] not in remaining_ids


def test_contextual_remove_oops_after_pending_tasks_list(chat_id, temp_db):
    t1 = temp_db.create_task("learning oops in C++", priority="medium")
    t2 = temp_db.create_task("learning C++ basics", priority="medium")

    # Turn 1: user asks for pending tasks
    list_res = app._handle_local_command("What are the pending tas", chat_id)
    assert list_res is not None
    temp_db.add_message(chat_id, "user", "What are the pending tas")
    temp_db.add_message(chat_id, "assistant", list_res[0])

    # Turn 2: exact Discord follow-up with conversational filler tail
    del_res = app._handle_local_command(
        "Remove the oops I have just added it for testing", chat_id
    )
    assert del_res is not None
    reply, provider = del_res
    assert provider == "local-task-manager"
    remaining_ids = [t["id"] for t in temp_db.list_tasks(include_completed=True)]
    assert t1["id"] not in remaining_ids
    assert t2["id"] in remaining_ids


def test_trailing_keyword_deletes_across_all_domains(chat_id, temp_db):
    # Task by #id
    t = temp_db.create_task("Temp item", priority="low")
    res_id = app._handle_local_command(f"remove #{t['id']}", chat_id)
    assert res_id is not None and res_id[1] == "local-task-manager"
    assert temp_db.list_tasks(include_completed=True) == []

    # Habit with trailing "from habits"
    temp_db.create_habit("Morning Stretch")
    res_h = app._handle_local_command("remove Morning Stretch from habits", chat_id)
    assert res_h is not None and res_h[1] == "local-habit-manager"
    assert temp_db.list_habits() == []

    # Reminder with trailing "reminder"
    temp_db.create_reminder("Drink water", "2026-12-01T10:00:00+05:30", chat_id=chat_id)
    res_r = app._handle_local_command("remove Drink water reminder", chat_id)
    assert res_r is not None and res_r[1] == "local-scheduler"
    assert temp_db.list_reminders(active_only=True) == []

    # Note with trailing "from notes"
    temp_db.add_memory("My favorite editor is Neovim")
    res_m = app._handle_local_command("remove Neovim from notes", chat_id)
    assert res_m is not None and res_m[1] == "local-memory"
    assert temp_db.list_memories() == []


def test_generic_delete_does_not_hijack_coding_questions(chat_id, temp_db):
    temp_db.create_task("learning C++ basics", priority="medium")
    res = app._handle_local_command("remove duplicates from a python list", chat_id)
    assert res is None


def test_agent_loop_short_circuits_needs_confirmation_without_hallucination(temp_db):
    """When a destructive tool returns needs_confirmation, the loop must NOT invoke a second LLM round."""
    task = temp_db.create_task("learning oops in C++", priority="medium")
    confirm_mgr = ConfirmationManager()

    deps = MagicMock(spec=AgentDeps)
    deps.local_timezone = app.LOCAL_TIMEZONE
    deps.memory_store = temp_db
    deps.token_budget = MagicMock(return_value=128)
    deps.live_reminders = MagicMock(return_value=[])
    deps.learning_schema_initialized = MagicMock(return_value=False)

    # Round 1: model calls delete_task
    resp_round_1 = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_del", "function": {"name": "delete_task", "arguments": {"task": "learning oops in C++"}}}
            ],
        }
    }
    mock_urlopen = MagicMock(side_effect=[_fake_http_response(resp_round_1)])

    with patch("urllib.request.urlopen", mock_urlopen):
        result = run_agent_loop(
            prompt="please get rid of that oops thing",
            chat_id="chat-confirm-test",
            history=[],
            memories=[],
            channel="discord",
            deps=deps,
            confirm_mgr=confirm_mgr,
        )

    # Must short-circuit after round 1 — LLM never got a chance to hallucinate "I've deleted it!"
    assert mock_urlopen.call_count == 1
    assert "yes" in result.reply.lower()
    assert "confirm" in result.reply.lower()
    assert "learning oops in C++" in result.reply
    # Task is still present until user confirms
    assert len(temp_db.list_tasks(include_completed=True)) == 1

    # Replying "ok" or "yes" executes the deletion deterministically
    handled, conf_reply, actions = confirm_mgr.check_and_handle("chat-confirm-test", "ok", deps)
    assert handled is True
    assert "deleted" in conf_reply.lower()
    assert temp_db.list_tasks(include_completed=True) == []
    assert any(a.get("type") == "refresh" and "tasks" in a.get("sections", []) for a in actions)


def test_resolve_entity_tech_aliases_cpp_vs_c_plus_plus():
    items = [
        {"id": 15, "title": "learning oops in C plus plus"},
        {"id": 13, "title": "learning C++ basics"},
    ]
    resolved, err = resolve_entity("learning oops in C++", items, title_key="title", entity_name="task")
    assert err is None
    assert resolved is not None
    assert resolved["id"] == 15


def test_tool_create_and_update_task_due_date_dmy(temp_db):
    deps = MagicMock(spec=AgentDeps)
    deps.memory_store = temp_db
    deps.local_timezone = app.LOCAL_TIMEZONE
    deps.parse_reminder_time = app._parse_reminder_time
    deps.run_learning_hook = lambda fn: None
    deps.suggest_learning_for_task = MagicMock()

    ctx = ToolContext(deps=deps, chat_id="default", channel="web")

    created = validate_and_execute_tool(
        "create_task",
        {"title": "Study pointers by 25-11-2026", "priority": "high"},
        ctx,
    )
    assert created["status"] == "ok"
    assert created["task"]["title"] == "Study pointers"
    assert str(created["task"]["due_at"]).startswith("2026-11-25")

    updated = validate_and_execute_tool(
        "update_task",
        {"task": str(created["task"]["id"]), "due": "28-11-2026"},
        ctx,
    )
    assert updated["status"] == "ok"
    assert str(updated["task"]["due_at"]).startswith("2026-11-28")
