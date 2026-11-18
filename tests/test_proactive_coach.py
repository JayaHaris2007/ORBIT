"""Tests for proactive coach check-ins, automatic suggestions, quiet hours, and concise spoken summaries."""

from datetime import datetime
from fastapi.testclient import TestClient

import app
from services.proactive_coach import is_evening_wrapup, is_quiet_hours
from voice.text_clean import summarize_for_speech


def test_summarize_for_speech_hackathon_list():
    raw = (
        "Here are some upcoming hackathons in India for late 2026:\n\n"
        "Upcoming:\n\n"
        "Vastoco Blueprint 2026 — Nov 18, 2026 (Online) — Design Hackathon with ₹30k prize.\n"
        "Hackathon by Reskilll — Aug 1–Nov 28, 2026 (Hybrid) — Phase 2 shortlisted teams.\n"
        "Health-a-thon 2026 — Koita Foundation × IIT Bombay (Online) — Healthcare AI focus with ₹54L+ prize.\n"
        "AgentVerse' 26 — Oct 30 – Dec 5, 2026 (Virtual) — Supported by OpenAI.\n"
        "Past:\n\n"
        "Goldman Sachs India Hackathon 2026 — May 23–24, 2026 (Online) — Individual and team tracks.\n"
        "Want to join any of these?"
    )
    spoken = summarize_for_speech(raw)
    assert "Vastoco Blueprint 2026" in spoken
    assert "Hackathon by Reskilll" in spoken
    assert "Health-a-thon 2026" in spoken
    assert "AgentVerse' 26" in spoken
    assert "Want to join any of these?" in spoken
    # Secondary details and Past section should NOT be read aloud
    assert "Goldman Sachs" not in spoken
    assert "Phase 2 shortlisted" not in spoken
    assert "30k" not in spoken


def test_proactive_coach_rotation_and_cooldown(temp_db):
    chat = app.memory_store.create_chat()
    chat_id = chat["id"]
    daytime = datetime(2026, 11, 18, 14, 0, tzinfo=app.LOCAL_TIMEZONE)

    app.memory_store.create_task("Finish DBMS project", priority="high")
    app.memory_store.create_habit("Drink 3L water", "Droplet", 1)
    app.init_learning_module("local")

    # 1. First daytime check-in picks task
    res1 = app.deliver_proactive_checkin(chat_id=chat_id, force=True, now=daytime)
    assert res1["nudge"] is True
    assert res1["category"] == "task"
    assert "Finish DBMS project" in res1["message"]

    # 2. Second daytime check-in rotates to habit
    res2 = app.deliver_proactive_checkin(chat_id=chat_id, force=True, now=daytime)
    assert res2["nudge"] is True
    assert res2["category"] == "habit"
    assert "Drink 3L water" in res2["message"]

    # 3. Third daytime check-in rotates to learning
    res3 = app.deliver_proactive_checkin(chat_id=chat_id, force=True, now=daytime)
    assert res3["nudge"] is True
    assert res3["category"] == "learning"

    # 4. Cooldown blocks immediate non-forced check-in during daytime
    blocked = app.deliver_proactive_checkin(chat_id=chat_id, force=False, cooldown_minutes=30, now=daytime)
    assert blocked["nudge"] is False
    assert blocked["reason"] == "already_nudged_recently"


def test_proactive_coach_night_quiet_hours_and_evening_wrapup(temp_db):
    chat = app.memory_store.create_chat()
    chat_id = chat["id"]

    app.memory_store.create_task("Deploy backend", priority="high")
    app.memory_store.create_habit("Evening Walk", "Activity", 1)

    late_night = datetime(2026, 11, 18, 2, 15, tzinfo=app.LOCAL_TIMEZONE)
    evening = datetime(2026, 11, 18, 21, 30, tzinfo=app.LOCAL_TIMEZONE)

    assert is_quiet_hours(late_night) is True
    assert is_evening_wrapup(evening) is True

    # Automatic background check-in is silenced at 2:15 AM
    silent = app.deliver_proactive_checkin(chat_id=chat_id, force=False, now=late_night)
    assert silent["nudge"] is False
    assert silent["reason"] == "quiet_hours"

    # Evening wind-down (9:30 PM) prioritizes unchecked daily habit before midnight
    eve_res = app.deliver_proactive_checkin(chat_id=chat_id, force=True, now=evening)
    assert eve_res["nudge"] is True
    assert eve_res["category"] == "habit"
    assert "Evening Walk" in eve_res["message"]
    assert "streak" in eve_res["message"].lower() or "before the day ends" in eve_res["message"].lower()


def test_proactive_coach_chat_commands_and_api(temp_db):
    client = TestClient(app.app)
    chat = app.memory_store.create_chat()
    chat_id = chat["id"]

    app.memory_store.create_task("Write unit tests", priority="high")
    app.memory_store.create_habit("Morning Exercise", "Activity", 1)

    # Chat command: "what should I do now"
    cmd_res = app._handle_local_command("what should I do now", chat_id)
    assert cmd_res is not None
    reply, provider = cmd_res
    assert provider == "local-proactive-coach"
    assert "Write unit tests" in reply
    assert "Morning Exercise" in reply

    # GET /api/proactive/suggestions
    sug_resp = client.get(f"/api/proactive/suggestions?chat_id={chat_id}")
    assert sug_resp.status_code == 200
    sug_data = sug_resp.json()
    assert sug_data["has_suggestions"] is True
    assert sug_data["pending_counts"]["tasks"] == 1
    assert sug_data["pending_counts"]["habits"] == 1

    # POST /api/proactive/check-in
    chk_resp = client.post("/api/proactive/check-in", json={"chat_id": chat_id, "force": True})
    assert chk_resp.status_code == 200
    chk_data = chk_resp.json()
    assert chk_data["nudge"] is True
    assert "spoken_response" in chk_data


def test_delete_all_database_data_endpoint(temp_db):
    client = TestClient(app.app)
    chat = app.memory_store.create_chat()
    app.memory_store.add_message(chat["id"], "user", "hello")
    app.memory_store.add_memory("My favorite language is C++")
    app.memory_store.create_task("Test DB wipe", priority="high")
    app.memory_store.create_habit("Read 10 pages", "Book", 1)
    app.init_learning_module("local")

    resp = client.delete("/api/database")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cleared"
    assert app.memory_store.list_tasks(include_completed=True) == []
    assert app.memory_store.list_habits() == []
    assert app.memory_store.list_memories() == []
    assert app.memory_store.get_gamification()["xp"] == 0

