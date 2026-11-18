"""Health check routes."""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["health"])


def _app():
    import app

    return app


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
