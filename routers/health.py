"""Health check routes."""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["health"])

_SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")


class OllamaSelectPayload(BaseModel):
    model: str
    persist: bool = True


class OllamaPullPayload(BaseModel):
    model: str
    select_after: bool = True


def _app():
    import app

    return app


def _validate_model_tag(raw: str) -> str:
    cleaned = (raw or "").strip()
    if not cleaned or len(cleaned) > 160 or not _SAFE_MODEL_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="Invalid Ollama model tag.")
    return cleaned


def _persist_env_model(model_name: str) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from spidey_launcher import save_env_values
        save_env_values({"OLLAMA_MODEL": model_name})
    except Exception:
        pass


@router.get("/api/ollama/models")
async def get_ollama_models():
    a = _app()
    return await asyncio.to_thread(a.list_ollama_models)


@router.post("/api/ollama/select")
async def select_ollama_model(payload: OllamaSelectPayload):
    a = _app()
    requested = _validate_model_tag(payload.model)

    info = await asyncio.to_thread(a.list_ollama_models)
    resolved = requested
    if info.get("reachable") and info.get("models"):
        from services.llm import _match_installed_model
        matched = _match_installed_model(requested, info["models"])
        if matched:
            resolved = matched

    a.OLLAMA_MODEL = resolved
    os.environ["OLLAMA_MODEL"] = resolved
    a._ollama_ready = False
    if payload.persist:
        await asyncio.to_thread(_persist_env_model, resolved)

    try:
        await asyncio.to_thread(a._ollama_check)
    except RuntimeError:
        # Allow selecting a tag before pulling it or while Ollama is offline
        pass

    updated = await asyncio.to_thread(a.list_ollama_models)
    updated["status"] = "ok"
    updated["active_model"] = a.OLLAMA_MODEL
    return updated


@router.post("/api/ollama/pull")
async def pull_ollama_model(payload: OllamaPullPayload):
    a = _app()
    target = _validate_model_tag(payload.model)

    def _do_pull() -> dict:
        url = f"{a.OLLAMA_URL}/api/pull"
        body = json.dumps({"name": target, "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            err_txt = ""
            try:
                err_txt = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_txt = exc.reason
            raise RuntimeError(f"Ollama pull failed ({exc.code}): {err_txt[:200]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama is not running at {a.OLLAMA_URL}. Start it with `ollama serve`.") from exc

    try:
        pull_res = await asyncio.to_thread(_do_pull)
    except RuntimeError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    if payload.select_after:
        a.OLLAMA_MODEL = target
        os.environ["OLLAMA_MODEL"] = target
        a._ollama_ready = False
        await asyncio.to_thread(_persist_env_model, target)
        try:
            await asyncio.to_thread(a._ollama_check)
        except RuntimeError:
            pass

    updated = await asyncio.to_thread(a.list_ollama_models)
    return {
        "status": pull_res.get("status", "success"),
        "pulled_model": target,
        "active_model": a.OLLAMA_MODEL,
        **updated,
    }


@router.get("/api/health")
@router.get("/health")
async def health():
    from runtime.models import REGISTRY

    a = _app()
    reachable = a._llm_available()
    ps_info = a._check_ollama_ps() if reachable else {}
    res = {
        "status": "ok",
        "llm_backend": "ollama",
        "llm_reachable": reachable,
        "db_connected": a.DATABASE_PATH.exists(),
        "db_path": str(a.DATABASE_PATH),
        "api_version": "spidey-local-2026-11",
        "model": a.OLLAMA_MODEL,
        "database": str(a.DATABASE_PATH),
        "semantic_memory": os.environ.get("AI_ENABLE_SEMANTIC_MEMORY", "1") != "0",
        "scheduler_running": a.reminder_scheduler.running if hasattr(a, "reminder_scheduler") else False,
        "scheduled_jobs": len(a.reminder_scheduler.get_jobs()) if hasattr(a, "reminder_scheduler") and a.reminder_scheduler.running else 0,
        "active_ws_clients": len(a.ws_manager.active) if hasattr(a, "ws_manager") else 0,
        "models": REGISTRY.get_status_summary() if hasattr(REGISTRY, "get_status_summary") else {},
    }
    if ps_info:
        if ps_info.get("size_vram") is not None:
            res["size_vram"] = ps_info["size_vram"]
        if ps_info.get("size") is not None:
            res["size"] = ps_info["size"]
    return res
