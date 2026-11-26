import os
import pytest
from unittest.mock import MagicMock

# Ensure semantic memory doesn't download sentence-transformer weights during unit tests
os.environ["AI_ENABLE_SEMANTIC_MEMORY"] = "0"

import app
from memory import MemoryStore


@pytest.fixture
def temp_db(tmp_path):
    """Provide a fresh, isolated MemoryStore in a temporary directory."""
    db_file = tmp_path / "test_assistant.db"
    store = MemoryStore(db_file)
    try:
        yield store
    finally:
        store.close()
        try:
            from learning import schema as learning_schema
            learning_schema.close_connections()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def isolate_app_environment(temp_db, monkeypatch):
    """Ensure all app.py operations use the temporary SQLite database and never touch assistant.db."""
    monkeypatch.setattr(app, "DATABASE_PATH", temp_db.database_path)
    monkeypatch.setattr(app, "memory_store", temp_db)

    # Mock the APScheduler instance to avoid spawning unneeded background threads during testing
    mock_scheduler = MagicMock()
    monkeypatch.setattr(app, "reminder_scheduler", mock_scheduler)

    # Mock ensure_model_loaded so tests never attempt to load Qwen3 into VRAM or CPU
    monkeypatch.setattr(app, "ensure_model_loaded", MagicMock())

    # Never touch the real Gmail account/token during tests
    from services import gmail_reader
    monkeypatch.setattr(gmail_reader, "CLIENT_SECRET_PATH", temp_db.database_path.parent / "no_client_secret.json")
    monkeypatch.setattr(gmail_reader, "TOKEN_PATH", temp_db.database_path.parent / "no_gmail_token.json")
    gmail_reader.clear_cache()
    from services import profile_and_nav
    monkeypatch.setattr(profile_and_nav, "_last_morning_brief_date", None)

    # Reset frontend open/closed presence between tests so presence state never leaks
    app.mark_frontend_inactive()
    yield temp_db
    app.mark_frontend_inactive()
