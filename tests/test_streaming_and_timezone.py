"""Tests for Phase 2: token-by-token response streaming and configurable timezone."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import app
import memory
from agent.confirm import ConfirmationManager
from agent.deps import AgentDeps
from agent.loop import AgentResult, _ThinkTagStreamFilter, run_agent_loop_stream


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def _dummy_deps() -> AgentDeps:
    deps = MagicMock(spec=AgentDeps)
    deps.local_timezone = app.LOCAL_TIMEZONE
    deps.memory_store = MagicMock()
    deps.memory_store.create_task = MagicMock(
        return_value={"id": 1, "title": "Buy milk", "priority": "medium"}
    )
    deps.run_learning_hook = lambda fn: None
    deps.live_reminders = MagicMock(return_value=[])
    deps.token_budget = MagicMock(return_value=128)
    return deps


def test_think_tag_stream_filter_strips_split_blocks():
    flt = _ThinkTagStreamFilter()
    chunks = ["<", "th", "ink>hidden reasoning</", "think>", "  Hello", " world", "!"]
    emitted = "".join(flt.feed(c) for c in chunks) + flt.flush()
    assert emitted == "Hello world!"


def test_run_agent_loop_stream_tool_then_tokens():
    deps = _dummy_deps()
    confirm_mgr = ConfirmationManager()

    round_1_chunks = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "create_task", "arguments": {"title": "Buy milk"}},
                    }
                ],
            },
            "done": True,
        }
    ]
    round_2_chunks = [
        {"message": {"role": "assistant", "content": "<think>ok</think>"}, "done": False},
        {"message": {"role": "assistant", "content": "Added "}, "done": False},
        {"message": {"role": "assistant", "content": "Buy milk."}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 5, "eval_duration": 100_000_000},
    ]

    rounds = [round_1_chunks, round_2_chunks]

    async def fake_stream(*args, **kwargs):
        for chunk in rounds.pop(0):
            yield chunk

    tokens: list[str] = []

    async def _run():
        with patch("agent.loop._ollama_chat_stream", side_effect=fake_stream):
            return await run_agent_loop_stream(
                prompt="add task Buy milk",
                chat_id="stream-chat",
                history=[],
                memories=[],
                channel="web",
                deps=deps,
                confirm_mgr=confirm_mgr,
                on_token=tokens.append,
            )

    result = asyncio.run(_run())
    assert tokens == ["Added ", "Buy milk."]
    assert result.reply == "Added Buy milk."
    assert result.provider == "agent-tools"
    assert any(a.get("type") == "refresh" and "tasks" in a.get("sections", []) for a in result.ui_actions)
    deps.memory_store.create_task.assert_called_once_with("Buy milk", priority="medium", due_at=None)


def test_generate_stream_endpoint_emits_tokens_and_persists(temp_db, monkeypatch):
    client = TestClient(app.app)
    chat = temp_db.create_chat()
    chat_id = chat["id"]

    monkeypatch.setattr(app, "ensure_model_loaded", lambda: None)
    monkeypatch.setattr(app, "_handle_local_command", lambda *args, **kwargs: None)

    async def fake_loop_stream(
        prompt, chat_id, history, memories, channel, deps, confirm_mgr, on_token=None, on_stream_reset=None
    ):
        for tok in ["Hello", " from", " stream!"]:
            if on_token:
                await on_token(tok)
        return AgentResult(reply="Hello from stream!", ui_actions=[], provider="ollama")

    monkeypatch.setattr(app, "run_agent_loop_stream", fake_loop_stream)

    resp = client.post(
        "/api/generate/stream",
        json={"prompt": "say hi", "chat_id": chat_id},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    token_texts = [e["text"] for e in events if e["type"] == "token"]
    assert token_texts == ["Hello", " from", " stream!"]
    assert any(e["type"] == "stream_done" for e in events)
    done_evts = [e for e in events if e["type"] == "done"]
    assert len(done_evts) == 1
    assert done_evts[0]["response"] == "Hello from stream!"

    stored = temp_db.get_messages(chat_id)
    assert [m["content"] for m in stored[-2:]] == ["say hi", "Hello from stream!"]


def test_generate_stream_rules_first_command(temp_db):
    client = TestClient(app.app)
    chat = temp_db.create_chat()
    resp = client.post(
        "/api/generate/stream",
        json={"prompt": "list tasks", "chat_id": chat["id"]},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    assert len(events) == 1
    assert events[0]["type"] == "done"
    assert events[0]["provider"] == "local-task-manager"


def test_websocket_streams_tokens_then_agent_response(temp_db, monkeypatch):
    client = TestClient(app.app)
    monkeypatch.setattr(app, "ensure_model_loaded", lambda: None)
    monkeypatch.setattr(app, "_handle_local_command", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "generate_tts_url", AsyncMock(return_value=None))

    async def fake_loop_stream(
        prompt, chat_id, history, memories, channel, deps, confirm_mgr, on_token=None, on_stream_reset=None
    ):
        for tok in ["Streamed ", "WS ", "reply"]:
            if on_token:
                await on_token(tok)
        return AgentResult(reply="Streamed WS reply", ui_actions=[], provider="ollama")

    monkeypatch.setattr(app, "run_agent_loop_stream", fake_loop_stream)

    with client.websocket_connect("/ws") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "connected"

        ws.send_json({"message": "hello ws", "chat_id": "default"})

        received = []
        while True:
            msg = ws.receive_json()
            received.append(msg)
            if msg.get("type") == "agent_response":
                break

    types = [m["type"] for m in received]
    assert types[0] == "status"
    assert [m["text"] for m in received if m["type"] == "token"] == ["Streamed ", "WS ", "reply"]
    assert "stream_done" in types
    assert types[-1] == "agent_response"
    assert received[-1]["text"] == "Streamed WS reply"


def test_resolve_local_timezone_from_env_and_fallback(monkeypatch):
    monkeypatch.setenv("SPIDEY_TIMEZONE", "America/New_York")
    assert memory._resolve_local_timezone().key == "America/New_York"

    monkeypatch.setenv("SPIDEY_TIMEZONE", "Not/A_Real_Zone")
    assert memory._resolve_local_timezone().key == "Asia/Kolkata"
