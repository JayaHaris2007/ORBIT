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


def test_proactive_checkin_mirrors_to_discord(temp_db):
    web_chat = app.memory_store.create_chat()
    discord_chat = app.memory_store.get_or_create_external_chat("discord", "123456789")
    app.memory_store.create_task("Study pointers in C++", priority="high")

    daytime = datetime(2026, 11, 20, 10, 0, tzinfo=app.LOCAL_TIMEZONE)
    res = app.deliver_proactive_checkin(chat_id=web_chat["id"], force=True, now=daytime)
    assert res["nudge"] is True
    assert res["discord_delivered"] == 1

    discord_notifs = app.memory_store.list_notifications(discord_chat["id"], after_id=0)
    assert len(discord_notifs) == 1
    assert "Study pointers in C++" in discord_notifs[0]["content"]


def test_proactive_checkin_uses_natural_friend_tone_without_robotic_labels(temp_db):
    chat = app.memory_store.create_chat()
    app.memory_store.create_task("learning C++ basics", priority="medium")
    app.memory_store.create_habit("Learning DSA", "Code", 1)
    app.init_learning_module("local")

    daytime = datetime(2026, 11, 21, 14, 0, tzinfo=app.LOCAL_TIMEZONE)
    for cat in ("task", "habit", "learning", "combined"):
        checkin = app.build_proactive_checkin(chat["id"], preferred_category=cat, now=daytime)
        assert checkin is not None
        msg = checkin["message"]
        # No robotic labels or bullet-list templates
        for forbidden in ("Habit push:", "Study push:", "accountability check-in:", "- Top Task:", "- Daily Habit:"):
            assert forbidden.lower() not in msg.lower(), f"Robotic phrase {forbidden!r} found in {msg!r}"


def test_proactive_checkin_goes_only_to_frontend_when_frontend_is_open(temp_db):
    web_chat = app.memory_store.create_chat()
    discord_chat = app.memory_store.get_or_create_external_chat("discord", "987654321")
    app.memory_store.create_task("Practice binary search", priority="high")
    daytime = datetime(2026, 11, 20, 11, 0, tzinfo=app.LOCAL_TIMEZONE)

    # Simulate frontend tab being open
    app.mark_frontend_active(client_id="win-tab-1", chat_id=web_chat["id"])
    assert app.is_frontend_active() is True

    # Scheduled Discord coach job must send NOTHING while frontend is open
    assert app.run_scheduled_proactive_checkins("discord", now=daytime) == 0
    assert app.memory_store.list_notifications(discord_chat["id"], after_id=0) == []

    # Scheduled local coach job must send ONLY to frontend (zero to Discord)
    assert app.run_scheduled_proactive_checkins("local", now=daytime) == 1
    assert len(app.memory_store.list_notifications(web_chat["id"], after_id=0)) == 1
    assert app.memory_store.list_notifications(discord_chat["id"], after_id=0) == []

    # Even forced check-in from an open frontend must NOT mirror to Discord
    res = app.deliver_proactive_checkin(chat_id=web_chat["id"], force=True, now=daytime)
    assert res["nudge"] is True
    assert res["discord_delivered"] == 0
    assert app.memory_store.list_notifications(discord_chat["id"], after_id=0) == []


def test_proactive_checkin_goes_only_to_discord_when_frontend_is_closed(temp_db):
    web_chat = app.memory_store.create_chat()
    discord_chat = app.memory_store.get_or_create_external_chat("discord", "987654321")
    app.memory_store.create_task("Review graph traversal", priority="high")
    daytime = datetime(2026, 11, 20, 11, 0, tzinfo=app.LOCAL_TIMEZONE)

    # Frontend is NOT open
    app.mark_frontend_inactive()
    assert app.is_frontend_active() is False

    # Scheduled local job routes exclusively to Discord (does NOT pile up in closed web chat)
    assert app.run_scheduled_proactive_checkins("local", now=daytime) == 1
    assert app.memory_store.list_notifications(web_chat["id"], after_id=0) == []
    discord_notifs = app.memory_store.list_notifications(discord_chat["id"], after_id=0)
    assert len(discord_notifs) == 1
    assert "Review graph traversal" in discord_notifs[0]["content"]

    # Subsequent Discord scheduled job respects cooldown (no duplicate spam)
    assert app.run_scheduled_proactive_checkins("discord", now=daytime) == 0


def test_code_suggestion_nudges_respect_frontend_open_state(temp_db):
    from services.learning_hooks import _notify_new_code_suggestions

    web_chat = app.memory_store.create_chat()
    discord_chat = app.memory_store.get_or_create_external_chat("discord", "555111222")
    sync_results = [
        {
            "new_suggestions": [
                {
                    "topic_id": 42,
                    "topic_name": "Control Flow",
                    "roadmap_name": "C++ with DSA",
                    "files": "while_loop.cpp, if_else.cpp",
                    "reason": "matched control flow constructs",
                }
            ]
        }
    ]

    # 1. Frontend open -> frontend ONLY
    app.mark_frontend_active(client_id="tab-a", chat_id=web_chat["id"])
    _notify_new_code_suggestions(sync_results)
    assert len(app.memory_store.list_notifications(web_chat["id"], after_id=0)) == 1
    assert app.memory_store.list_notifications(discord_chat["id"], after_id=0) == []

    # 2. Frontend closed -> Discord ONLY (no new web notification)
    app.mark_frontend_inactive("tab-a")
    _notify_new_code_suggestions(sync_results)
    assert len(app.memory_store.list_notifications(web_chat["id"], after_id=0)) == 1
    assert len(app.memory_store.list_notifications(discord_chat["id"], after_id=0)) == 1


def test_frontend_presence_api_tracks_multi_tab_open_and_close(temp_db):
    client = TestClient(app.app)
    web_chat = app.memory_store.create_chat()
    discord_chat = app.memory_store.get_or_create_external_chat("discord", "777888999")
    app.memory_store.create_task("Solve DP problems", priority="high")

    assert client.get("/api/frontend/presence").json()["active"] is False

    # Tab 1 opens
    r1 = client.post(
        "/api/frontend/presence",
        json={"active": True, "client_id": "tab-1", "chat_id": web_chat["id"]},
    )
    assert r1.status_code == 200
    assert r1.json()["active"] is True

    # Tab 2 opens
    r2 = client.post(
        "/api/frontend/presence",
        json={"active": True, "client_id": "tab-2", "chat_id": web_chat["id"]},
    )
    assert r2.status_code == 200
    assert r2.json()["active"] is True

    # Frontend-triggered check-in must NOT mirror to Discord
    chk = client.post(
        "/api/proactive/check-in",
        json={"chat_id": web_chat["id"], "force": True, "source": "frontend"},
        headers={"X-Orbit-Client-Id": "tab-1"},
    )
    assert chk.status_code == 200
    assert chk.json()["discord_delivered"] == 0
    assert app.memory_store.list_notifications(discord_chat["id"], after_id=0) == []

    # Tab 1 closes -> Tab 2 still keeps frontend active
    r3 = client.post("/api/frontend/presence", json={"active": False, "client_id": "tab-1"})
    assert r3.json()["active"] is True

    # Tab 2 closes -> frontend is immediately inactive
    r4 = client.post("/api/frontend/presence", json={"active": False, "client_id": "tab-2"})
    assert r4.json()["active"] is False
    assert app.is_proactive_notification_key("task-coach-learning-abc") is True
    assert app.is_proactive_notification_key("code-sugg-12-loop.cpp") is True
    assert app.is_proactive_notification_key("user-reminder-uuid-1234") is False


