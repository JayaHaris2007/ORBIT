"""S.P.I.D.E.Y. (ORBIT007) FastAPI application entry point and service wiring."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import sys
import threading
import warnings
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure `import app` inside discord_bot.py shares this exact module instance when run as __main__
sys.modules.setdefault("app", sys.modules[__name__])

# Filter benign pydub warning about missing system ffmpeg
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub.utils")

# Set Hugging Face offline flags unless explicitly opted out with SPIDEY_ALLOW_HUB=1
if os.environ.get("SPIDEY_ALLOW_HUB") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    from dotenv import load_dotenv
except ImportError:  # Optional during partial installs.
    load_dotenv = None
else:
    load_dotenv(Path(__file__).resolve().parent / ".env")

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "spidey.log"
TTS_DIR = BASE_DIR / "TTS"
TTS_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_spidey_configured", False):
        return
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root._spidey_configured = True


configure_logging()
LOGGER = logging.getLogger("spidey")

MAX_PROMPT_CHARS = 2000
MAX_NEW_TOKENS = 2048
DEFAULT_CHAT_ID = "default"
DATABASE_PATH = Path(os.environ.get("ORBIT_DB_DIR", BASE_DIR)) / "assistant.db"

# LLM Backend configuration (Ollama + per-request Gemini)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b").strip()
try:
    OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192").strip())
except ValueError:
    OLLAMA_NUM_CTX = 8192

OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "5m").strip()
try:
    OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120").strip())
except ValueError:
    OLLAMA_TIMEOUT = 120.0

_ollama_ready: bool = False
logging.getLogger("orbit007").info("LLM backend: ollama (%s @ %s)", OLLAMA_MODEL, OLLAMA_URL)

import assistant_tone  # noqa: E402, F401
from agent.confirm import ConfirmationManager  # noqa: E402
from agent.deps import AgentDeps  # noqa: E402
from agent.gemini import (  # noqa: E402, F401
    gemini_chat_request,
    get_active_gemini_config,
    is_gemini_active,
    reset_request_gemini_config,
    set_request_gemini_config,
)
from agent.loop import AgentResult, close_http_sessions, run_agent_loop, run_agent_loop_stream  # noqa: E402, F401
from learning import classifier as learning_classifier  # noqa: E402, F401
from learning import code_rag as learning_code_rag  # noqa: E402, F401
from learning import nudges as learning_nudges  # noqa: E402, F401
from learning import progress as learning_progress  # noqa: E402
from learning import roadmaps as learning_roadmaps  # noqa: E402, F401
from learning import schema as learning_schema  # noqa: E402
from learning.router import router as learning_router  # noqa: E402
from memory import LOCAL_TIMEZONE, MAX_RETRIEVED_MEMORIES, MemoryStore  # noqa: E402, F401
from research.router import router as research_router  # noqa: E402
from research.search_engine import (  # noqa: E402, F401
    SearchFailed,
    SearchNotConfigured,
    search as web_search,
)
from voice.config import purge_voice_tmp  # noqa: E402
from voice.router import (  # noqa: E402
    router as voice_router,
    set_chat_handler as set_voice_chat_handler,
    set_stream_chat_handler as set_voice_stream_chat_handler,
    ws_router as voice_ws_router,
)

# Shared runtime singletons
generation_lock = threading.RLock()
memory_store = MemoryStore(DATABASE_PATH)
LOCAL_TIMEZONE_NAME = getattr(LOCAL_TIMEZONE, "key", str(LOCAL_TIMEZONE))
reminder_scheduler = BackgroundScheduler(timezone=LOCAL_TIMEZONE)
MAIN_LOOP: asyncio.AbstractEventLoop | None = None

# Service layer re-exports (preserves `app.*` interface for tests, bridge, and Discord bot)
from services.command_router import (  # noqa: E402, F401
    _daily_briefing_command,
    _extract_context_entities,
    _handle_local_command,
    _memory_command,
    _resolve_contextual_completion,
    _resolve_contextual_mutation,
    _xp_status_command,
)
from services.learning_commands import (  # noqa: E402, F401
    _clean_topic_reference,
    _extract_learning_context,
    _learning_command,
    _learning_complete_reply,
    _learning_hold_reply,
    _learning_next_reply,
    _learning_progress_reply,
    _learning_reopen_reply,
    _learning_roadmap_progress_reply,
    _learning_roadmap_topics_reply,
    _learning_start_reply,
    _learning_status_topics_reply,
    _learning_unknown_roadmap_reply,
    _resolve_roadmap_from_context_or_ref,
    _resolve_topic_from_context_or_ref,
)
from services.learning_hooks import (  # noqa: E402, F401
    WEEKLY_LEARNING_NUDGE_JOB,
    _fallback_llm_for_learning,
    _learning_on_task_completed,
    _learning_suggest_for_task,
    _run_learning_hook,
    _schedule_weekly_learning_nudge,
    _weekly_learning_nudge,
    init_learning_module,
)
from services.proactive_coach import (  # noqa: E402, F401
    PROACTIVE_COACH_JOB_ID,
    build_proactive_checkin,
    deliver_proactive_checkin,
    get_proactive_snapshot,
    proactive_coach_command as _proactive_coach_command,
    run_scheduled_proactive_checkins,
    schedule_proactive_coach,
)
from services.llm import (  # noqa: E402, F401
    DEFAULT_SYSTEM_PROMPT,
    TOKENS_BRIEF,
    TOKENS_DEFAULT,
    TOKENS_LONG,
    TOKENS_MEDIUM,
    _build_local_command_ui_actions,
    _check_ollama_ps,
    _generate_ollama,
    _get_async_generation_lock,
    _learning_digest,
    _llm_available,
    _ollama_check,
    _productivity_context,
    _token_budget,
    _trim_incomplete,
    _validate_generate_payload,
    ensure_model_loaded,
    generate_response,
    get_active_ollama_model,
    list_ollama_models,
    reset_request_ollama_model,
    resolve_short_follow_up,
    respond_with_tools,
    respond_with_tools_stream,
    select_generation_context,
    set_request_ollama_model,
)
from services.productivity_parsers import (  # noqa: E402, F401
    _complete_habit,
    _complete_task,
    _extract_task_due_date,
    _find_habit,
    _find_task_reference,
    _format_habit_list,
    _format_task_list,
    _fuzzy_best_match,
    _habit_completion_line,
    _has_negation_or_unmark,
    _is_advice_question,
    _is_habit_follow_up,
    _is_habit_list_request,
    _is_task_list_request,
    _normalize_command,
    _normalize_tech_text,
    _parse_chat_habit,
    _parse_completion_target,
    _parse_generic_delete,
    _parse_habit_completion,
    _strip_delete_filler,
    _parse_habit_delete,
    _parse_habit_rename,
    _parse_habit_uncomplete,
    _parse_task_completion,
    _parse_task_create,
    _parse_task_delete,
    _parse_task_due_date,
    _parse_task_reopen,
    _parse_task_update,
    _parse_web_search_query,
    _reopen_all_tasks,
    _search_snippet,
    _task_completion_line,
    _uncomplete_all_habits,
    _uncomplete_habit,
    _web_search_reply,
)
from services.profile_and_nav import (  # noqa: E402, F401
    _PAGE_ALIASES,
    _assistant_intro_answer,
    _builder_names,
    _describes_assistant,
    _greeting_answer,
    _identity_answer,
    _memories_for_prompt,
    _page_for_provider,
    _parse_navigation,
    _profile_answer,
    _profile_buckets,
    _profile_label,
    _profile_overview,
    _profile_topic,
    _profile_topic_answer,
    _route_for_page,
    _second_person,
    _user_fact_memories,
    _user_name,
)
from services.reminders import (  # noqa: E402, F401
    _cancel_reminder_unified,
    _create_reminder_unified,
    _ensure_chat_exists,
    _find_reminder,
    _format_due_date,
    _format_reminder_list,
    _is_reminder_list_request,
    _live_reminders,
    _notify_completion,
    _parse_chat_reminder,
    _parse_reminder_cancel,
    _parse_reminder_reschedule,
    _parse_reminder_time,
    _push_reminder_alert,
    _recommend_next_task,
    _reminder_clarification,
    _reminder_result,
    _reminder_view,
    _restore_reminders,
    _run_reminder,
    _schedule_reminder,
    _validate_recurrence,
)
from services.voice_ws import (  # noqa: E402, F401
    ConnectionManager,
    _cleanup_temp_audio,
    _cleanup_tts,
    generate_tts_url,
    process_agent_turn,
    run_existing_tts,
    transcribe_pcm_bytes,
)

ws_manager = ConnectionManager()
confirmation_mgr = ConfirmationManager()
_ORIGINAL_GENERATE_RESPONSE = generate_response
_ORIGINAL_RESPOND_WITH_TOOLS = respond_with_tools

agent_deps = AgentDeps(
    memory_store=memory_store,
    create_reminder_unified=_create_reminder_unified,
    cancel_reminder_unified=_cancel_reminder_unified,
    parse_reminder_time=_parse_reminder_time,
    validate_recurrence=_validate_recurrence,
    live_reminders=_live_reminders,
    web_search=web_search,
    learning_schema_initialized=learning_schema.is_initialized,
    learning_overall_progress=learning_progress.overall_progress,
    learning_next_topics=learning_progress.next_topics,
    run_learning_hook=_run_learning_hook,
    suggest_learning_for_task=_learning_suggest_for_task,
    local_timezone=LOCAL_TIMEZONE,
    page_aliases=_PAGE_ALIASES,
    generate_response=generate_response,
    token_budget=_token_budget,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    _cleanup_tts()
    from runtime.guard import acquire_model_process_lock, release_model_process_lock

    acquire_model_process_lock()
    try:
        from runtime.loaders import load_all_models_eager

        await asyncio.to_thread(load_all_models_eager, generation_lock=generation_lock)
        _restore_reminders(provider="local")
        init_learning_module("local")
        schedule_proactive_coach("local")
        purge_voice_tmp()
        reminder_scheduler.add_job(
            _cleanup_temp_audio,
            IntervalTrigger(minutes=15, timezone=LOCAL_TIMEZONE),
            id="spidey-temp-audio-cleanup",
            replace_existing=True,
        )

        discord_token = os.environ.get("AI_DISCORD_TOKEN", "").strip()
        if discord_token:
            try:
                from discord_bot import start_discord_bot_in_process

                await start_discord_bot_in_process(discord_token)
            except Exception as err:
                LOGGER.warning("Failed to start in-process Discord bot: %s", err)

        yield
    finally:
        discord_token = os.environ.get("AI_DISCORD_TOKEN", "").strip()
        if discord_token:
            try:
                from discord_bot import stop_discord_bot_in_process

                await stop_discord_bot_in_process()
            except Exception:
                LOGGER.debug("Suppressed error shutting down Discord bot", exc_info=True)

        if reminder_scheduler.running:
            reminder_scheduler.shutdown(wait=False)
        await close_http_sessions()
        memory_store.close()
        learning_schema.close_connections()
        release_model_process_lock()


cors_origins_env = os.environ.get(
    "ORBIT_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
)
ORBIT_CORS_ORIGINS = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]
API_TOKEN = os.environ.get("ORBIT_API_TOKEN", "").strip()
_OPEN_PATHS = ("/health", "/api/health")

app = FastAPI(title="ORBIT Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORBIT_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_http_token(request: Request) -> str:
    header_tok = (request.headers.get("x-orbit-token") or "").strip()
    if header_tok:
        return header_tok
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _safe_header_str(headers: Any, key: str) -> str:
    if not isinstance(headers, dict) and not hasattr(headers, "get"):
        return ""
    # Avoid creating unawaited coroutines when tests pass AsyncMock WebSockets
    if type(headers).__name__ == "AsyncMock":
        return ""
    val = headers.get(key)
    return val.strip() if isinstance(val, str) else ""


def _extract_ws_token(ws: WebSocket) -> str:
    headers = getattr(ws, "headers", None)
    header_tok = _safe_header_str(headers, "x-orbit-token")
    if header_tok:
        return header_tok
    proto_header = _safe_header_str(headers, "sec-websocket-protocol")
    for part in proto_header.split(","):
        item = part.strip()
        if item.startswith("orbit-token."):
            return item[len("orbit-token.") :]
    qp = getattr(ws, "query_params", None)
    if type(qp).__name__ == "AsyncMock" or not hasattr(qp, "get"):
        return ""
    tok = qp.get("token", "")
    return tok if isinstance(tok, str) else ""


@app.middleware("http")
async def gemini_context_middleware(request: Request, call_next):
    api_key = request.headers.get("x-gemini-api-key")
    model = request.headers.get("x-gemini-model")
    ollama_model = request.headers.get("x-ollama-model")
    tokens = set_request_gemini_config(api_key, model)
    ollama_tok = set_request_ollama_model(ollama_model)
    try:
        return await call_next(request)
    finally:
        reset_request_ollama_model(ollama_tok)
        reset_request_gemini_config(tokens)


@app.middleware("http")
async def token_guard(request: Request, call_next):
    if API_TOKEN and request.method != "OPTIONS" and not request.url.path.startswith(_OPEN_PATHS):
        supplied = _extract_http_token(request)
        if not secrets.compare_digest(supplied, API_TOKEN):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


async def ws_authorized(ws: WebSocket) -> bool:
    if not API_TOKEN:
        return True
    ok = secrets.compare_digest(_extract_ws_token(ws), API_TOKEN)
    if not ok:
        await ws.close(code=1008)
    return ok


app.mount("/tts", StaticFiles(directory=str(TTS_DIR)), name="tts")


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception):
    LOGGER.exception("Unhandled API error: %s", error)
    return JSONResponse(status_code=500, content={"error": "The backend could not complete that request."})


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, error: HTTPException):
    detail = error.detail
    msg = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(status_code=error.status_code, content={"detail": msg, "error": msg})


from routers.chat import (  # noqa: E402, F401
    ChatPayload,
    api_chat,
    generate,
    generate_stream,
    router as chat_router,
    websocket_agent_endpoint,
)
from routers.health import health, router as health_router  # noqa: E402, F401
from routers.productivity import (  # noqa: E402, F401
    ReminderCreatePayload,
    ReminderUpdatePayload,
    api_create_reminder,
    api_delete_reminder,
    api_get_history,
    api_get_reminders,
    api_update_reminder,
    clear_chats,
    compat_list_notifications,
    create_chat,
    create_habit,
    create_memory,
    create_task,
    delete_chat,
    delete_habit,
    delete_memory,
    delete_task,
    get_gamification,
    history,
    list_chats,
    list_habits,
    list_memories,
    list_notifications,
    list_tasks,
    nudge_task,
    router as productivity_router,
    set_habit_completion,
    update_habit,
    update_memory,
    update_task,
)


async def _voice_chat_turn(prompt: str, chat_id: str | None = None):
    payload = {"prompt": prompt, "channel": "voice"}
    if chat_id:
        payload["chat_id"] = chat_id
    return await generate(payload)


async def _voice_chat_turn_stream(
    prompt: str,
    chat_id: str | None = None,
    on_token=None,
    on_stream_reset=None,
):
    from services.turn_orchestrator import execute_turn_stream

    payload = {"prompt": prompt}
    if chat_id:
        payload["chat_id"] = chat_id
    validated_prompt, _max_tokens, resolved_chat_id = _validate_generate_payload(payload)
    outcome = await execute_turn_stream(
        validated_prompt,
        resolved_chat_id,
        channel="voice",
        on_token=on_token,
        on_stream_reset=on_stream_reset,
        stream_local_tokens=False,
    )
    return {
        "response": outcome.response,
        "spoken_response": outcome.spoken_response,
        "chat_id": outcome.chat_id,
        "messages": memory_store.get_messages(outcome.chat_id),
        "provider": outcome.provider,
        "navigate": outcome.navigate,
        "ui_actions": outcome.ui_actions,
    }


set_voice_chat_handler(_voice_chat_turn)
_voice_chat_turn._is_default_voice_handler = True  # type: ignore[attr-defined]
set_voice_stream_chat_handler(_voice_chat_turn_stream)
app.include_router(research_router)
app.include_router(learning_router)
app.include_router(voice_router)
app.include_router(voice_ws_router)
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(productivity_router)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Qwen AI assistant")
    parser.add_argument("--server", action="store_true", help="Start the HTTP server instead of the CLI.")
    parser.add_argument("--host", default="127.0.0.1", help="Server bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Server port.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload the server when Python source files change (development only).",
    )
    parser.add_argument("prompt", nargs="?", help="Prompt to run once. Omit it to start interactive mode.")
    parser.add_argument("--max-new-tokens", type=int, default=None, help=f"Maximum response tokens (1-{MAX_NEW_TOKENS}).")
    return parser.parse_args()


def main() -> None:
    configure_logging(level=logging.INFO)
    args = parse_arguments()
    if args.server:
        if args.host == "0.0.0.0" and not os.environ.get("ORBIT_API_TOKEN", "").strip():
            LOGGER.warning(
                "[SECURITY WARNING] Server is binding to 0.0.0.0 with no ORBIT_API_TOKEN set! "
                "Any machine on your network can access this assistant."
            )
        from runtime.guard import SPIDEY_MODEL_GUARD_PORT, get_port_owner_pid

        owner_pid = get_port_owner_pid(args.port) or get_port_owner_pid(SPIDEY_MODEL_GUARD_PORT)
        if owner_pid is not None and owner_pid != os.getpid():
            print(f"\n[FATAL] S.P.I.D.E.Y server or models are already running in process [PID {owner_pid}].")
            print(f"To stop the previous instance, run: taskkill /PID {owner_pid} /F (or Stop-Process -Id {owner_pid})\n")
            return

        uvicorn.run("app:app" if args.reload else app, host=args.host, port=args.port, log_level="info", reload=args.reload)
        return

    if args.max_new_tokens is not None and not 1 <= args.max_new_tokens <= MAX_NEW_TOKENS:
        raise ValueError(f"--max-new-tokens must be between 1 and {MAX_NEW_TOKENS}.")

    if args.prompt is not None:
        tokens = args.max_new_tokens if args.max_new_tokens is not None else _token_budget(args.prompt)
        print(generate_response(args.prompt, tokens))
        return

    print("Local AI assistant. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if prompt.lower() in {"exit", "quit"}:
            return
        try:
            tokens = args.max_new_tokens if args.max_new_tokens is not None else _token_budget(prompt)
            print(f"AI: {generate_response(prompt, tokens)}")
        except ValueError as error:
            print(f"Error: {error}")


if __name__ == "__main__":
    main()
