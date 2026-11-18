"""Tests for the Google AI Studio (Gemini) backend adapter, BYOK routing, security, and E2E integration."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

import app
from agent.gemini import (
    convert_messages_to_gemini,
    convert_tools_to_gemini,
    gemini_chat_request,
    get_active_gemini_config,
    is_gemini_active,
    reset_request_gemini_config,
    set_request_gemini_config,
)
from agent.tools import TOOLS


def test_convert_tools_to_gemini_strips_unsupported_keys():
    ollama_tools = [t.to_ollama_tool() for t in TOOLS]
    gemini_tools = convert_tools_to_gemini(ollama_tools)
    assert gemini_tools is not None
    assert len(gemini_tools) == 1
    decls = gemini_tools[0]["functionDeclarations"]
    assert len(decls) == len(TOOLS)
    for decl in decls:
        assert "name" in decl
        params = decl.get("parameters")
        if params:
            assert "additionalProperties" not in params
            assert "$schema" not in params


def test_convert_messages_to_gemini_merges_consecutive_tool_turns():
    messages = [
        {"role": "system", "content": "You are Spidey."},
        {"role": "user", "content": "Check my tasks and reminders."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "list_tasks", "arguments": {}}},
                {"function": {"name": "list_reminders", "arguments": {}}},
            ],
        },
        {"role": "tool", "tool_name": "list_tasks", "content": '{"status": "ok", "tasks": []}'},
        {"role": "tool", "tool_name": "list_reminders", "content": '{"status": "ok", "reminders": []}'},
    ]
    sys_inst, contents = convert_messages_to_gemini(messages)
    assert sys_inst == {"parts": [{"text": "You are Spidey."}]}
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert len(contents[1]["parts"]) == 2
    assert contents[1]["parts"][0]["functionCall"]["name"] == "list_tasks"
    assert len(contents[2]["parts"]) == 2
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "list_tasks"
    assert contents[2]["parts"][1]["functionResponse"]["name"] == "list_reminders"


def test_request_context_overrides_ollama_check_and_routes_generate_response():
    tokens = set_request_gemini_config("AIza-test-key-123", "gemini-3.5-flash")
    try:
        key, model = get_active_gemini_config()
        assert key == "AIza-test-key-123"
        assert model == "gemini-3.5-flash"
        assert is_gemini_active() is True

        with patch.object(app, "_ollama_check", side_effect=AssertionError("Should not check Ollama")):
            app.ensure_model_loaded()
            assert app._llm_available() is True

        fake_resp = {"message": {"role": "assistant", "content": "Hello from Gemini!"}, "done": True}
        with (
            patch.object(app, "gemini_chat_request", return_value=fake_resp) as mock_gemini,
            patch.object(app, "_generate_ollama", side_effect=AssertionError("Should not call Ollama")),
        ):
            reply = app.generate_response("Hi there", max_new_tokens=64)
            assert reply == "Hello from Gemini!"
            mock_gemini.assert_called_once()
    finally:
        reset_request_gemini_config(tokens)

    assert is_gemini_active() is False


def test_gemini_503_transient_retry_and_fallback():
    """Verify 503 high-demand error retries and falls back cleanly."""
    call_count = 0

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "candidates": [{"content": {"parts": [{"text": "Recovered from 503!"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }).encode("utf-8")

    def _fake_urlopen(req, timeout=60.0):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err_body = io.BytesIO(b'{"error": {"message": "High demand"}}')
            raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, err_body)
        return _FakeResp()

    with (
        patch("urllib.request.urlopen", side_effect=_fake_urlopen),
        patch("time.sleep"),
    ):
        result = gemini_chat_request(
            [{"role": "user", "content": "Ping"}],
            api_key="test-key",
            model="gemini-3.5-flash",
        )
        assert result["message"]["content"] == "Recovered from 503!"
        assert call_count == 2


def test_ws_rejects_query_param_key_and_accepts_inband_config():
    """Verify WebSocket ignores ?gemini_key=... in URL and accepts set_gemini_config frame."""
    client = TestClient(app.app)
    with client.websocket_connect("/ws?gemini_key=LEAKED_IN_URL") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "connected"

        # Sending set_gemini_config without a key confirms query param was NOT used
        ws.send_json({"type": "set_gemini_config"})
        ack1 = ws.receive_json()
        assert ack1["type"] == "gemini_config_set"
        assert ack1["active"] is False

        # Sending key in-band activates Gemini for the session
        ws.send_json({
            "type": "set_gemini_config",
            "gemini_api_key": "AQ.inband-secret",
            "gemini_model": "gemini-3.5-flash",
        })
        ack2 = ws.receive_json()
        assert ack2["type"] == "gemini_config_set"
        assert ack2["active"] is True
        assert ack2["model"] == "gemini-3.5-flash"


def test_productivity_router_endpoints():
    """Verify extracted productivity router serves chats, tasks, habits, and memories."""
    client = TestClient(app.app)
    assert client.get("/api/chats").status_code == 200
    assert client.get("/api/tasks").status_code == 200
    assert client.get("/api/habits").status_code == 200
    assert client.get("/api/memories").status_code == 200
    assert client.get("/api/gamification").status_code == 200
    assert client.get("/api/reminders").status_code == 200


def test_live_llm_end_to_end_when_available():
    """Run a real E2E generation against Gemini or local Ollama when available."""
    env_gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_gemini_key:
        tokens = set_request_gemini_config(env_gemini_key, "gemini-3.5-flash")
        try:
            reply = app.generate_response("Reply with the single word OK.", max_new_tokens=16)
            assert isinstance(reply, str) and len(reply.strip()) > 0
        finally:
            reset_request_gemini_config(tokens)
        return

    try:
        app._ollama_check()
    except RuntimeError:
        pytest.skip("Neither GEMINI_API_KEY nor local Ollama is currently active.")

    reply = app.generate_response("Reply with the single word OK.", max_new_tokens=16)
    assert isinstance(reply, str) and len(reply.strip()) > 0
