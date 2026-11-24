"""Learning tables and SQLite connection handling for the learning module.

Follows the conventions of memory.py: CREATE TABLE IF NOT EXISTS, foreign
keys with cascading deletes, a row factory returning dict-like rows, and a
connection manager that commits on success and rolls back on failure.

Nothing in this package owns assistant.db exclusively: ``init()`` must be
called once by app.py (with the same database path MemoryStore uses) before
any query runs. Tests call ``init()`` with a temporary database instead.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field, StrictBool

ROADMAP_CATEGORIES = ("academic", "technical", "personal")
TOPIC_STATUSES = ("not_started", "learning", "completed", "on_hold")
LINK_STATES = ("suggested", "confirmed", "rejected")
LINK_SOURCES = ("rule", "embedding", "llm", "manual")
ACTIVITY_KINDS = ("planned", "started", "completed", "postponed")
CODE_FILE_STATES = ("empty", "wip", "practiced")
CODE_SUGGESTION_STATES = ("pending", "confirmed", "dismissed")

Category = Literal["academic", "technical", "personal"]
TopicStatus = Literal["not_started", "learning", "completed", "on_hold"]
LinkState = Literal["suggested", "confirmed", "rejected"]
CodeSuggestionState = Literal["pending", "confirmed", "dismissed"]


class RoadmapIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Category = "technical"
    description: str = Field(default="", max_length=2000)
    topics: list[str] | str | None = None
    auto_subtopics: bool = False


class LearningPathImportIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    category: Category = "technical"
    description: str = Field(default="", max_length=2000)
    raw_text: str | None = None
    topics: list[str] | None = None
    priority: int = Field(default=2, ge=1, le=3)
    auto_subtopics: bool = True


class BulkTopicsIn(BaseModel):
    raw_text: str | None = None
    topics: list[str] | None = None
    priority: int = Field(default=2, ge=1, le=3)


class RoadmapPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Category | None = None
    description: str | None = Field(default=None, max_length=2000)


class TopicIn(BaseModel):
    roadmap_id: int
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=2000)
    position: int | None = None
    priority: int = Field(default=1, ge=1, le=3)
    status: TopicStatus = "not_started"
    requires_topic_ids: list[int] = Field(default_factory=list, max_length=20)


class TopicPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aliases: list[str] | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    position: int | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    status: TopicStatus | None = None


class LinkPatch(BaseModel):
    state: LinkState
    topic_id: int | None = None


class SettingsPatch(BaseModel):
    nudges_enabled: StrictBool


class FolderLinkIn(BaseModel):
    folder_path: str = Field(min_length=1, max_length=1000)
    enabled: StrictBool = True


class CodeSuggestionPatch(BaseModel):
    state: Literal["confirmed", "dismissed"]


class CodeRagQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    roadmap_id: int | None = None
    limit: int = Field(default=5, ge=1, le=15)

_database_path: Path | None = None
_local = threading.local()
_open_connections: list[sqlite3.Connection] = []
_conn_lock = threading.Lock()


def close_connections() -> None:
    """Close all cached thread-local SQLite connections for the learning schema."""
    with _conn_lock:
        conns = list(_open_connections)
        _open_connections.clear()
    _local.__dict__.clear()
    for conn in conns:
        try:
            conn.close()
        except Exception:
            pass


def is_initialized() -> bool:
    """Whether init() has pointed the module at a database yet."""
    return _database_path is not None


def init(database_path: Path) -> None:
    """Point the learning module at a database and create its tables."""
    global _database_path
    new_path = Path(database_path)
    if _database_path is not None and _database_path != new_path:
        close_connections()
    _database_path = new_path
    _database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS roadmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL CHECK(category IN ('academic', 'technical', 'personal')),
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roadmap_id INTEGER NOT NULL REFERENCES roadmaps(id)
                    ON DELETE CASCADE,
                name TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'not_started'
                    CHECK(status IN ('not_started', 'learning', 'completed', 'on_hold')),
                embedding BLOB,
                updated_at TEXT NOT NULL,
                UNIQUE(roadmap_id, name)
            );
            CREATE INDEX IF NOT EXISTS topics_roadmap_idx
                ON topics(roadmap_id, position);
            CREATE TABLE IF NOT EXISTS topic_prerequisites (
                topic_id INTEGER NOT NULL REFERENCES topics(id)
                    ON DELETE CASCADE,
                requires_topic_id INTEGER NOT NULL REFERENCES topics(id)
                    ON DELETE CASCADE,
                PRIMARY KEY(topic_id, requires_topic_id),
                CHECK(topic_id != requires_topic_id)
            );
            CREATE TABLE IF NOT EXISTS task_topic_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                confidence REAL NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'suggested'
                    CHECK(state IN ('suggested', 'confirmed', 'rejected')),
                source TEXT NOT NULL DEFAULT 'rule'
                    CHECK(source IN ('rule', 'embedding', 'llm', 'manual')),
                created_at TEXT NOT NULL,
                UNIQUE(task_id, topic_id)
            );
            CREATE INDEX IF NOT EXISTS task_topic_links_state_idx
                ON task_topic_links(state, id);
            CREATE TABLE IF NOT EXISTS learning_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL REFERENCES topics(id)
                    ON DELETE CASCADE,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                kind TEXT NOT NULL CHECK(kind IN ('planned', 'started', 'completed', 'postponed')),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS learning_activities_topic_idx
                ON learning_activities(topic_id, id);
            CREATE TABLE IF NOT EXISTS learning_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roadmap_id INTEGER NOT NULL UNIQUE REFERENCES roadmaps(id)
                    ON DELETE CASCADE,
                folder_path TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_synced_at TEXT,
                last_sync_summary TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_code_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roadmap_id INTEGER NOT NULL REFERENCES roadmaps(id)
                    ON DELETE CASCADE,
                rel_path TEXT NOT NULL,
                abs_path TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                line_count INTEGER NOT NULL DEFAULT 0,
                code_lines INTEGER NOT NULL DEFAULT 0,
                has_compiled_artifact INTEGER NOT NULL DEFAULT 0,
                file_state TEXT NOT NULL DEFAULT 'wip'
                    CHECK(file_state IN ('empty', 'wip', 'practiced')),
                concepts_json TEXT NOT NULL DEFAULT '[]',
                symbols_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                modified_at TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                UNIQUE(roadmap_id, rel_path)
            );
            CREATE INDEX IF NOT EXISTS learning_code_files_roadmap_idx
                ON learning_code_files(roadmap_id, modified_at DESC);
            CREATE TABLE IF NOT EXISTS learning_code_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL REFERENCES learning_code_files(id)
                    ON DELETE CASCADE,
                roadmap_id INTEGER NOT NULL REFERENCES roadmaps(id)
                    ON DELETE CASCADE,
                rel_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                start_line INTEGER NOT NULL DEFAULT 1,
                end_line INTEGER NOT NULL DEFAULT 1,
                content TEXT NOT NULL,
                concepts TEXT NOT NULL DEFAULT '',
                embedding BLOB
            );
            CREATE INDEX IF NOT EXISTS learning_code_chunks_file_idx
                ON learning_code_chunks(file_id, chunk_index);
            CREATE INDEX IF NOT EXISTS learning_code_chunks_roadmap_idx
                ON learning_code_chunks(roadmap_id);
            CREATE TABLE IF NOT EXISTS topic_code_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roadmap_id INTEGER NOT NULL REFERENCES roadmaps(id)
                    ON DELETE CASCADE,
                topic_id INTEGER NOT NULL REFERENCES topics(id)
                    ON DELETE CASCADE,
                confidence REAL NOT NULL DEFAULT 0.0,
                evidence_files TEXT NOT NULL DEFAULT '[]',
                reason TEXT NOT NULL DEFAULT '',
                suggestion_state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(suggestion_state IN ('pending', 'confirmed', 'dismissed')),
                updated_at TEXT NOT NULL,
                UNIQUE(roadmap_id, topic_id)
            );
            CREATE INDEX IF NOT EXISTS topic_code_evidence_state_idx
                ON topic_code_evidence(suggestion_state, roadmap_id);
            """
        )
        # Optional FTS5 virtual table for fast BM25 code RAG retrieval
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS learning_code_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    roadmap_id UNINDEXED,
                    rel_path,
                    concepts,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )
        except sqlite3.OperationalError:
            pass


def database_path() -> Path:
    if _database_path is None:
        raise RuntimeError("learning.schema.init() was not called yet.")
    return _database_path


def _get_thread_connection() -> sqlite3.Connection:
    db_path = database_path()
    db_key = str(db_path)
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    conn_key: str | None = getattr(_local, "db_key", None)
    if conn is not None and conn_key == db_key:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            conn = None

    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

    connection = sqlite3.connect(
        db_path,
        check_same_thread=False,
        timeout=30.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    _local.conn = connection
    _local.db_key = db_key
    with _conn_lock:
        _open_connections.append(connection)
    return connection


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = _get_thread_connection()
    in_tx_before = connection.in_transaction
    try:
        yield connection
        if not in_tx_before:
            connection.commit()
    except Exception:
        if not in_tx_before:
            connection.rollback()
        raise


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
