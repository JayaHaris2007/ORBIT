import io
import json
import logging
import urllib.error
import urllib.request
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app

# Save the real ensure_model_loaded from app.py before conftest autouse fixture mocks it
_ORIGINAL_ENSURE_MODEL_LOADED = app.ensure_model_loaded


def _make_mock_response(data: dict, status: int = 200):
    body = json.dumps(data).encode("utf-8")
    resp = io.BytesIO(body)
    resp.status = status
    resp.code = status
    return resp


def test_ollama_request_body_structure(monkeypatch, temp_db):
    """Request body has think: False, stream: False, options.num_predict, and options.num_ctx."""
    monkeypatch.setattr(app, "_ollama_ready", True)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append((req, req.data))
        return _make_mock_response({
            "message": {"role": "assistant", "content": "I am S.P.I.D.E.Y."},
            "done_reason": "stop",
            "eval_count": 8,
            "eval_duration": 120_000_000,
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    res = app.generate_response("hello", 128)
    assert res == "I am S.P.I.D.E.Y."
    assert len(captured_requests) == 1

    req, req_data = captured_requests[0]
    payload = json.loads(req_data.decode("utf-8"))

    # Top-level fields
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["model"] == app.OLLAMA_MODEL
    assert payload["keep_alive"] == app.OLLAMA_KEEP_ALIVE

    # Options fields
    opts = payload["options"]
    assert opts["num_predict"] == 128
    assert opts["num_ctx"] == app.OLLAMA_NUM_CTX
    assert opts["temperature"] == 0
    assert opts["repeat_penalty"] == 1.05


def test_ollama_think_tags_stripped(monkeypatch, temp_db):
    """A reply containing <think>...</think> is stripped cleanly."""
    monkeypatch.setattr(app, "_ollama_ready", True)

    raw_reply = (
        "<think>Reasoning through the question...\nAnalyzing user mood.</think>"
        "Greetings! How may I assist you today?"
    )

    def mock_urlopen(req, timeout=None):
        return _make_mock_response({
            "message": {"role": "assistant", "content": raw_reply},
            "done_reason": "stop",
            "eval_count": 15,
            "eval_duration": 200_000_000,
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    res = app.generate_response("who are you", 100)
    assert res == "Greetings! How may I assist you today?"
    assert "<think>" not in res
    assert "</think>" not in res


def test_ollama_done_reason_length_trims_incomplete(monkeypatch, temp_db):
    """When done_reason is 'length', response is trimmed to the last complete sentence."""
    monkeypatch.setattr(app, "_ollama_ready", True)

    truncated_reply = "Here is your first instruction. Here is a half finished thought that got cut"

    def mock_urlopen(req, timeout=None):
        return _make_mock_response({
            "message": {"role": "assistant", "content": truncated_reply},
            "done_reason": "length",
            "eval_count": 20,
            "eval_duration": 300_000_000,
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    res = app.generate_response("give steps", 50)
    assert res == "Here is your first instruction."


def test_ollama_prompt_truncation_warning(caplog, monkeypatch, temp_db):
    """When prompt_eval_count >= OLLAMA_NUM_CTX - 8, a warning is logged."""
    monkeypatch.setattr(app, "_ollama_ready", True)

    def mock_urlopen(req, timeout=None):
        return _make_mock_response({
            "message": {"role": "assistant", "content": "Understood."},
            "done_reason": "stop",
            "prompt_eval_count": app.OLLAMA_NUM_CTX,  # >= 4088
            "eval_count": 5,
            "eval_duration": 50_000_000,
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    with caplog.at_level(logging.WARNING, logger="orbit007"):
        res = app.generate_response("long prompt test", 32)
        assert res == "Understood."
        assert any("probably truncated" in record.message for record in caplog.records)


def test_ollama_connection_error_raises_runtime_error(monkeypatch):
    """Connection error raises RuntimeError with 'not running' and 'ollama serve'."""
    monkeypatch.setattr(app, "_ollama_ready", False)
    monkeypatch.setattr(app, "ensure_model_loaded", _ORIGINAL_ENSURE_MODEL_LOADED)

    def mock_urlopen_fail(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_fail)

    with pytest.raises(RuntimeError) as exc_info:
        app.ensure_model_loaded()

    msg = str(exc_info.value)
    assert "Ollama is not running at" in msg
    assert "Start it with `ollama serve`" in msg


def test_ollama_missing_model_raises_pull_message(monkeypatch):
    """Missing model raises RuntimeError with 'not found' and 'ollama pull'."""
    monkeypatch.setattr(app, "_ollama_ready", False)
    monkeypatch.setattr(app, "OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setattr(app, "ensure_model_loaded", _ORIGINAL_ENSURE_MODEL_LOADED)

    def mock_urlopen_tags(req, timeout=None):
        return _make_mock_response({
            "models": [
                {"name": "llama3:latest"},
                {"name": "mistral:7b"},
            ]
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_tags)

    with pytest.raises(RuntimeError) as exc_info:
        app.ensure_model_loaded()

    msg = str(exc_info.value)
    assert "Model qwen3.5:4b not found" in msg
    assert "Run `ollama pull qwen3.5:4b`" in msg


def test_ollama_model_matches_with_or_without_latest(monkeypatch):
    """Model name match succeeds whether or not ':latest' tag is explicit."""
    monkeypatch.setattr(app, "_ollama_ready", False)
    monkeypatch.setattr(app, "OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setattr(app, "ensure_model_loaded", _ORIGINAL_ENSURE_MODEL_LOADED)

    def mock_urlopen_tags(req, timeout=None):
        return _make_mock_response({
            "models": [{"name": "qwen3.5:4b:latest"}]
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_tags)

    app.ensure_model_loaded()
    assert app._ollama_ready is True


def test_health_includes_llm_backend_and_ps_data(temp_db, monkeypatch):
    """The /api/health endpoint includes llm_backend, llm_reachable, and size_vram from /api/ps."""
    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/tags" in url:
            return _make_mock_response({
                "models": [{"name": app.OLLAMA_MODEL}]
            })
        elif "/api/ps" in url:
            return _make_mock_response({
                "models": [{
                    "name": app.OLLAMA_MODEL,
                    "size_vram": 2147483648,
                    "size": 3324173934,
                }]
            })
        return _make_mock_response({})

    monkeypatch.setattr(app, "_ollama_ready", True)
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    client = TestClient(app.app)
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["llm_backend"] == "ollama"
    assert data["llm_reachable"] is True
    assert data["model"] == app.OLLAMA_MODEL
    assert data.get("size_vram") == 2147483648
    assert data.get("size") == 3324173934


def test_eager_loads_ollama(monkeypatch):
    """When Ollama is running, load_all_models_eager registers ollama."""
    import runtime.loaders as loaders
    from runtime.models import REGISTRY

    orig_items = dict(REGISTRY._items)
    orig_status = dict(REGISTRY.status)
    orig_errors = dict(REGISTRY.errors)
    orig_metrics = dict(REGISTRY.metrics)

    monkeypatch.setattr(loaders, "wait_for_ollama", lambda *args, **kwargs: True)
    monkeypatch.setattr(loaders, "load_phonon_eager", lambda *args, **kwargs: (MagicMock(), 1.0))
    monkeypatch.setattr(loaders, "load_embedder_eager", lambda *args, **kwargs: (MagicMock(), 1.0))
    monkeypatch.setattr(loaders, "load_stt_eager", lambda *args, **kwargs: MagicMock())

    try:
        loaders.load_all_models_eager()
        assert REGISTRY.is_ready("llm") is True
        assert REGISTRY.get("llm") == "ollama"
    finally:
        REGISTRY._items = orig_items
        REGISTRY.status = orig_status
        REGISTRY.errors = orig_errors
        REGISTRY.metrics = orig_metrics


def test_eager_fails_llm_when_ollama_unavailable(monkeypatch):
    """When Ollama is not running, load_all_models_eager marks llm as failed without crashing."""
    import runtime.loaders as loaders
    from runtime.models import REGISTRY

    orig_items = dict(REGISTRY._items)
    orig_status = dict(REGISTRY.status)
    orig_errors = dict(REGISTRY.errors)
    orig_metrics = dict(REGISTRY.metrics)

    monkeypatch.setattr(loaders, "wait_for_ollama", lambda *args, **kwargs: False)
    monkeypatch.setattr(loaders, "load_phonon_eager", lambda *args, **kwargs: (MagicMock(), 1.0))
    monkeypatch.setattr(loaders, "load_embedder_eager", lambda *args, **kwargs: (MagicMock(), 1.0))
    monkeypatch.setattr(loaders, "load_stt_eager", lambda *args, **kwargs: MagicMock())

    try:
        loaders.load_all_models_eager()
        assert REGISTRY.status.get("llm") == "failed"
        assert "Ollama is not running" in REGISTRY.errors.get("llm", "")
    finally:
        REGISTRY._items = orig_items
        REGISTRY.status = orig_status
        REGISTRY.errors = orig_errors
        REGISTRY.metrics = orig_metrics


def test_universal_ollama_model_adapts_when_tools_and_think_unsupported(monkeypatch, temp_db):
    """Any Ollama model lacking native 'think' or 'tools' support auto-adapts and answers cleanly."""
    from agent.confirm import ConfirmationManager
    from agent.loop import _MODELS_WITHOUT_THINK, _MODELS_WITHOUT_TOOLS, run_agent_loop

    model_tag = "gemma3-custom:4b"
    _MODELS_WITHOUT_THINK.discard(model_tag)
    _MODELS_WITHOUT_TOOLS.discard(model_tag)
    monkeypatch.setattr(app, "OLLAMA_MODEL", model_tag)

    seen_payloads = []

    def mock_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        seen_payloads.append(body)
        if "think" in body:
            err_fp = io.BytesIO(b'{"error":"model does not support thinking"}')
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, err_fp)
        if "tools" in body:
            err_fp = io.BytesIO(b'{"error":"registry.ollama.ai/library/gemma3:4b does not support tools"}')
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, err_fp)
        return _make_mock_response({
            "message": {
                "role": "assistant",
                "content": "<thought>Internal thought</thought>Hello from Gemma3 without native tools!",
            },
            "done_reason": "stop",
        })

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    res = run_agent_loop(
        prompt="Explain binary search",
        chat_id="default",
        history=[],
        memories=[],
        channel="web",
        deps=app.agent_deps,
        confirm_mgr=ConfirmationManager(),
    )
    assert res.reply == "Hello from Gemma3 without native tools!"
    assert model_tag in _MODELS_WITHOUT_THINK
    assert model_tag in _MODELS_WITHOUT_TOOLS
    assert len(seen_payloads) == 3

    _MODELS_WITHOUT_THINK.discard(model_tag)
    _MODELS_WITHOUT_TOOLS.discard(model_tag)


def test_ollama_models_list_and_hot_swap_select(monkeypatch, temp_db):
    """GET /api/ollama/models lists all chat models and POST /api/ollama/select hot-swaps active model."""
    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/tags" in url:
            return _make_mock_response({
                "models": [
                    {
                        "name": "qwen3.5:4b",
                        "size": 2600000000,
                        "details": {"parameter_size": "4.3B", "quantization_level": "Q4_K_M", "family": "qwen3"},
                    },
                    {
                        "name": "deepseek-r1:8b",
                        "size": 4900000000,
                        "details": {"parameter_size": "8.0B", "quantization_level": "Q4_K_M", "family": "llama"},
                    },
                    {
                        "name": "nomic-embed-text:latest",
                        "size": 274000000,
                        "details": {"families": ["nomic-bert"]},
                    },
                ]
            })
        if "/api/ps" in url:
            return _make_mock_response({"models": [{"name": "deepseek-r1:8b"}]})
        return _make_mock_response({})

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(app, "OLLAMA_MODEL", "qwen3.5:4b")

    client = TestClient(app.app)
    res = client.get("/api/ollama/models")
    assert res.status_code == 200
    data = res.json()
    assert data["reachable"] is True
    assert "qwen3.5:4b" in data["chat_models"]
    assert "deepseek-r1:8b" in data["chat_models"]
    assert "nomic-embed-text:latest" not in data["chat_models"]

    sel = client.post("/api/ollama/select", json={"model": "deepseek-r1:8b", "persist": False})
    assert sel.status_code == 200
    assert sel.json()["active_model"] == "deepseek-r1:8b"
    assert app.OLLAMA_MODEL == "deepseek-r1:8b"
