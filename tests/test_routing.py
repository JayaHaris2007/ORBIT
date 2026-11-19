"""Routing regression tests for the intent detectors in app.py.

Advice questions about habits/tasks/reminders must fall through to the LLM
instead of being trapped by the deterministic list handlers.
"""

import app


def test_habit_list_detector_true_cases():
    assert app._is_habit_list_request("what are habits i am having") is True
    assert app._is_habit_list_request("show my pending habits") is True


def test_habit_list_detector_advice_false_cases():
    assert (
        app._is_habit_list_request(
            "what new habits do i need to add to improve myself"
        )
        is False
    )
    assert (
        app._is_habit_list_request(
            "my habits and what should i do to improve"
        )
        is False
    )
    assert (
        app._is_habit_list_request("what do you think about my habits") is False
    )


def test_task_list_detector_cases():
    assert app._is_task_list_request("show my tasks") is True
    assert app._is_task_list_request("give me task ideas") is False
    assert app._is_task_list_request("how can i manage my tasks better") is False


def test_reminder_list_detector_cases():
    assert app._is_reminder_list_request("show my reminders") is True
    assert app._is_reminder_list_request("suggest some reminders i should set") is False


def test_entity_parsers_still_work():
    assert app._parse_chat_habit("add habit drink water") is not None
    assert app._parse_task_create("add task finish report") is not None


def test_task_create_extracts_and_saves_due_dates(temp_db):
    chat = app.memory_store.create_chat()

    reply, provider = app._handle_local_command(
        "create a new task learning C++ basics by 20-11-2026", chat["id"]
    )
    assert provider == "local-task-manager"
    assert "20 Nov 2026" in reply

    tasks = app.memory_store.list_tasks(include_completed=True)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "learning C++ basics"
    assert tasks[0]["due_at"].startswith("2026-11-20")

    # DMY date where day <= 12 (05-12-2026 -> 2026-12-05, not May 12) + priority
    app._handle_local_command(
        "add task submit DBMS lab on 05-12-2026 high priority", chat["id"]
    )
    tasks = app.memory_store.list_tasks(include_completed=True)
    dbms_task = next(t for t in tasks if t["title"] == "submit DBMS lab")
    assert dbms_task["priority"] == "high"
    assert dbms_task["due_at"].startswith("2026-12-05")

    # Task without a date stays due_at=None
    app._handle_local_command("add task buy milk", chat["id"])
    tasks = app.memory_store.list_tasks(include_completed=True)
    milk_task = next(t for t in tasks if t["title"] == "buy milk")
    assert milk_task["due_at"] is None

