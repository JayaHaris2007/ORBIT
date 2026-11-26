"""Local SQLite storage and bounded memory retrieval for the assistant."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading

LOGGER = logging.getLogger("spidey.memory")
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


MAX_CONTEXT_TOKENS = 1800
MAX_MEMORY_TEXT = 500
MAX_RETRIEVED_MEMORIES = 5
HABIT_COMPLETION_XP = 10


def _resolve_local_timezone() -> ZoneInfo:
    tz_name = os.environ.get("SPIDEY_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        LOGGER.warning("Invalid SPIDEY_TIMEZONE %r; falling back to Asia/Kolkata", tz_name)
        return ZoneInfo("Asia/Kolkata")


LOCAL_TIMEZONE = _resolve_local_timezone()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self._embedder = None
        self._embedding_warning_printed = False
        self._local = threading.local()
        self._open_connections: list[tuple[int, sqlite3.Connection]] = []
        self._conn_lock = threading.Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _get_thread_connection(self) -> sqlite3.Connection:
        db_key = str(self.database_path)
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        conn_key: str | None = getattr(self._local, "db_key", None)
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
            self.database_path,
            check_same_thread=False,
            timeout=30.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        self._local.conn = connection
        self._local.db_key = db_key
        with self._conn_lock:
            self._open_connections.append((threading.get_ident(), connection))
        return connection

    def close(self) -> None:
        """Safely close cached SQLite connections owned by the current thread or exited threads."""
        cur_tid = threading.get_ident()
        alive_tids = {t.ident for t in threading.enumerate() if t.ident is not None}
        to_close: list[sqlite3.Connection] = []
        still_active: list[tuple[int, sqlite3.Connection]] = []
        with self._conn_lock:
            for tid, conn in self._open_connections:
                if tid == cur_tid or tid not in alive_tids:
                    to_close.append(conn)
                else:
                    still_active.append((tid, conn))
            self._open_connections[:] = still_active
        self._local.__dict__.clear()
        for conn in to_close:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def connect(self):
        connection = self._get_thread_connection()
        in_tx_before = connection.in_transaction
        try:
            yield connection
            if not in_tx_before:
                connection.commit()
        except Exception:
            if not in_tx_before:
                connection.rollback()
            raise

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(conversation_id, role, content, created_at)
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_idx
                    ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL UNIQUE,
                    embedding TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS external_sessions (
                    provider TEXT NOT NULL,
                    external_user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id)
                        ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider, external_user_id)
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'medium'
                        CHECK(priority IN ('low', 'medium', 'high')),
                    due_at TEXT,
                    completed INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_status_idx
                    ON tasks(completed, priority, due_at);
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    recurrence TEXT,
                    chat_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reminders_active_idx
                    ON reminders(active, run_at);
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    icon TEXT NOT NULL DEFAULT 'Activity',
                    daily_goal INTEGER NOT NULL DEFAULT 1 CHECK(daily_goal > 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS habit_completions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                    completion_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(habit_id, completion_date)
                );
                CREATE INDEX IF NOT EXISTS habit_completions_date_idx
                    ON habit_completions(completion_date, habit_id);
                CREATE TABLE IF NOT EXISTS gamification (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
                    valid_streak_dates TEXT NOT NULL DEFAULT '[]',
                    achievements TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL REFERENCES conversations(id)
                        ON DELETE CASCADE,
                    reminder_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(reminder_id, created_at)
                );
                CREATE TABLE IF NOT EXISTS reminder_delivery_targets (
                    reminder_id TEXT PRIMARY KEY,
                    channel_id INTEGER,
                    guild_id INTEGER,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reminder_delivery_targets_idx
                    ON reminder_delivery_targets(reminder_id);
                DELETE FROM messages
                WHERE role = 'assistant'
                  AND EXISTS (
                      SELECT 1
                      FROM notifications
                      WHERE notifications.chat_id = messages.conversation_id
                        AND notifications.content = messages.content
                  );
                """
            )
            session_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(external_sessions)")
            }
            if "last_notification_id" not in session_columns:
                connection.execute(
                    "ALTER TABLE external_sessions ADD COLUMN last_notification_id INTEGER NOT NULL DEFAULT 0"
                )
            reminder_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(reminders)")
            }
            if "chat_id" not in reminder_columns:
                connection.execute(
                    "ALTER TABLE reminders ADD COLUMN chat_id TEXT "
                    "REFERENCES conversations(id) ON DELETE SET NULL"
                )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)")
            }
            if "completed_at" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN completed_at TEXT"
                )
                connection.execute(
                    "UPDATE tasks SET completed_at = updated_at "
                    "WHERE completed = 1"
                )
            if "description" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "INSERT OR IGNORE INTO gamification "
                "(id, updated_at) VALUES (1, ?)",
                (_now(),),
            )

    def create_chat(self, title: str = "New conversation") -> dict[str, Any]:
        chat_id = str(uuid.uuid4())
        now = _now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?)",
                (chat_id, title[:120], now, now),
            )
        return {"id": chat_id, "title": title[:120], "created_at": now, "updated_at": now}

    def list_chats(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def chat_exists(self, chat_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (chat_id,)
            ).fetchone() is not None

    def get_messages(self, chat_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id",
                (chat_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, chat_id: str, role: str, content: str) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("Invalid message role.")
        if not content.strip():
            raise ValueError("Message cannot be empty.")
        now = _now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages(conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (chat_id, role, content, now),
            )
            if role == "user":
                title = content.strip().replace("\n", " ")[:80]
                connection.execute(
                    "UPDATE conversations SET title = CASE WHEN title = "
                    "'New conversation' THEN ? ELSE title END, updated_at = ? "
                    "WHERE id = ?",
                    (title, now, chat_id),
                )
            else:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, chat_id),
                )
        return {"id": cursor.lastrowid, "role": role, "content": content, "created_at": now}

    def delete_chat(self, chat_id: str) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (chat_id,)
            )
        return result.rowcount > 0

    def clear_chats(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM conversations")

    def clear_chat_messages(self, chat_id: str) -> int:
        """Delete all messages in a single conversation while preserving the chat row and all user data."""
        with self.connect() as connection:
            cur = connection.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (chat_id,)
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (_now(), chat_id),
            )
            return max(0, cur.rowcount)

    def clear_stale_chat_messages(self, chat_id: str, max_age_days: float = 3.0) -> int:
        """Clear all messages in ``chat_id`` once its oldest message is >= ``max_age_days`` old."""
        if max_age_days <= 0:
            return 0
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MIN(created_at) AS oldest_at, COUNT(*) AS cnt "
                "FROM messages WHERE conversation_id = ?",
                (chat_id,),
            ).fetchone()
        if not row or not row["cnt"] or not row["oldest_at"]:
            return 0
        try:
            oldest_dt = datetime.fromisoformat(str(row["oldest_at"]).replace("Z", "+00:00"))
            if oldest_dt.tzinfo is None:
                oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
        except Exception:
            return 0
        age = datetime.now(timezone.utc) - oldest_dt
        if age >= timedelta(days=max_age_days):
            return self.clear_chat_messages(chat_id)
        return 0

    def reset_stale_external_chats(
        self, provider: str, max_age_days: float = 3.0
    ) -> dict[str, int]:
        """Clear message history for every external chat of ``provider`` whose window reached ``max_age_days``."""
        if max_age_days <= 0:
            return {}
        cleared: dict[str, int] = {}
        for item in self.list_external_chats(provider):
            cid = item["id"]
            removed = self.clear_stale_chat_messages(cid, max_age_days=max_age_days)
            if removed > 0:
                cleared[cid] = removed
        return cleared

    def get_or_create_external_chat(
        self, provider: str, external_user_id: str
    ) -> dict[str, Any]:
        if not provider.strip() or not external_user_id.strip():
            raise ValueError("External session identifiers cannot be empty.")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at "
                "FROM external_sessions AS s "
                "JOIN conversations AS c ON c.id = s.conversation_id "
                "WHERE s.provider = ? AND s.external_user_id = ?",
                (provider, external_user_id),
            ).fetchone()
            if row is not None:
                return dict(row)

        chat = self.create_chat(title=f"{provider} conversation")
        now = _now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO external_sessions "
                "(provider, external_user_id, conversation_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, external_user_id, chat["id"], now, now),
            )
        return chat

    def get_external_last_notification_id(self, chat_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT last_notification_id FROM external_sessions WHERE conversation_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["last_notification_id"]) if row and row["last_notification_id"] is not None else 0

    def set_external_last_notification_id(self, chat_id: str, last_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE external_sessions SET last_notification_id = ? WHERE conversation_id = ?",
                (last_id, chat_id),
            )

    def get_external_session(self, chat_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT provider, external_user_id FROM external_sessions "
                "WHERE conversation_id = ?",
                (chat_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_external_chats(self, provider: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.id, s.external_user_id "
                "FROM external_sessions AS s "
                "JOIN conversations AS c ON c.id = s.conversation_id "
                "WHERE s.provider = ?",
                (provider,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_local_chat_ids(self) -> list[str]:
        """Conversation ids belonging to local web sessions."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.id FROM conversations AS c "
                "LEFT JOIN external_sessions AS s ON s.conversation_id = c.id "
                "WHERE s.provider IS NULL"
            ).fetchall()
        return [row["id"] for row in rows]

    def list_tasks(self, include_completed: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks"
        if not include_completed:
            query += " WHERE completed = 0"
        query += (
            " ORDER BY completed, CASE priority WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 ELSE 3 END, due_at, id"
        )
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def create_task(
        self,
        title: str,
        priority: str = "medium",
        due_at: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        title = title.strip()
        description = description.strip()
        if not title or len(title) > 500:
            raise ValueError("Task title must contain 1-500 characters.")
        if len(description) > 2000:
            raise ValueError("Task description must be 2000 characters or fewer.")
        if priority not in {"low", "medium", "high"}:
            raise ValueError("Priority must be low, medium, or high.")
        now = _now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO tasks(title, description, priority, due_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, priority, due_at, now, now),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row)

    def update_task(
        self,
        task_id: int,
        title: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        completed: bool | None = None,
        description: str | None = None,
        clear_due_at: bool = False,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if existing is None:
                return None
            if clear_due_at:
                due_value = None
            elif due_at is not None:
                due_value = due_at
            else:
                due_value = existing["due_at"]
            values = (
                title.strip() if title is not None else existing["title"],
                description.strip() if description is not None else existing["description"],
                priority if priority is not None else existing["priority"],
                due_value,
                int(completed) if completed is not None else existing["completed"],
                (
                    datetime.now(timezone.utc).isoformat()
                    if completed is True
                    else None
                    if completed is False
                    else existing["completed_at"]
                ),
                _now(),
                task_id,
            )
            if not values[0] or len(values[0]) > 500:
                raise ValueError("Task title must contain 1-500 characters.")
            if len(values[1]) > 2000:
                raise ValueError("Task description must be 2000 characters or fewer.")
            if values[2] not in {"low", "medium", "high"}:
                raise ValueError("Priority must be low, medium, or high.")
            connection.execute(
                "UPDATE tasks SET title = ?, description = ?, priority = ?, due_at = ?, "
                "completed = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                values,
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return dict(row)

    def delete_task(self, task_id: int) -> bool:
        with self.connect() as connection:
            result = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return result.rowcount > 0

    @staticmethod
    def _calculate_streak(completed_dates: list[str]) -> int:
        completed = set(completed_dates)
        today = datetime.now(LOCAL_TIMEZONE).date()
        if today.isoformat() not in completed:
            today -= timedelta(days=1)
            if today.isoformat() not in completed:
                return 0
        streak = 0
        while today.isoformat() in completed:
            streak += 1
            today -= timedelta(days=1)
        return streak

    def _get_gamification(self, connection: sqlite3.Connection) -> dict[str, Any]:
        row = connection.execute(
            "SELECT xp, valid_streak_dates, achievements FROM gamification WHERE id = 1"
        ).fetchone()
        if row is None:
            now = _now()
            connection.execute(
                "INSERT INTO gamification(id, updated_at) VALUES (1, ?)", (now,)
            )
            return {"xp": 0, "valid_streak_dates": [], "achievements": []}
        return {
            "xp": row["xp"],
            "valid_streak_dates": json.loads(row["valid_streak_dates"]),
            "achievements": json.loads(row["achievements"]),
        }

    def _refresh_gamification(self, connection: sqlite3.Connection, xp_delta: int = 0) -> None:
        data = self._get_gamification(connection)
        habits = connection.execute("SELECT id FROM habits").fetchall()
        valid_dates: list[str] = []
        if habits:
            rows = connection.execute(
                "SELECT completion_date, COUNT(*) AS completed FROM habit_completions "
                "GROUP BY completion_date"
            ).fetchall()
            threshold = len(habits) * 0.7
            valid_dates = [row["completion_date"] for row in rows if row["completed"] >= threshold]
        achievements = set(data["achievements"])
        if habits:
            achievements.add("first-habit")
        if self._calculate_streak(valid_dates) >= 7:
            achievements.add("seven-day-streak")
        xp = max(0, data["xp"] + xp_delta)
        if xp >= 100:
            achievements.add("hundred-xp")
        connection.execute(
            "UPDATE gamification SET xp = ?, valid_streak_dates = ?, achievements = ?, updated_at = ? "
            "WHERE id = 1",
            (xp, json.dumps(sorted(valid_dates)), json.dumps(sorted(achievements)), _now()),
        )

    def award_xp(self, amount: int, reason: str = "") -> dict[str, Any]:
        """Award (or deduct) XP and refresh gamification state."""
        with self.connect() as connection:
            self._refresh_gamification(connection, xp_delta=int(amount))
            data = self._get_gamification(connection)
        if reason:
            LOGGER.info("Awarded %d XP (%s). Total XP: %d", amount, reason, data["xp"])
        return {"xp": data["xp"], "awarded": int(amount), "reason": reason}

    def list_habits(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            habits = connection.execute("SELECT * FROM habits ORDER BY id").fetchall()
            result = []
            for habit in habits:
                dates = [
                    row["completion_date"]
                    for row in connection.execute(
                        "SELECT completion_date FROM habit_completions "
                        "WHERE habit_id = ? ORDER BY completion_date",
                        (habit["id"],),
                    )
                ]
                item = dict(habit)
                item["completed_dates"] = dates
                item["streak"] = self._calculate_streak(dates)
                result.append(item)
        return result

    def create_habit(self, name: str, icon: str = "Activity", daily_goal: int = 1) -> dict[str, Any]:
        name = name.strip()
        if not name or len(name) > 200:
            raise ValueError("Habit name must contain 1-200 characters.")
        if not isinstance(daily_goal, int) or isinstance(daily_goal, bool) or daily_goal < 1:
            raise ValueError("daily_goal must be a positive integer.")
        now = _now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO habits(name, icon, daily_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, icon.strip() or "Activity", daily_goal, now, now),
            )
            self._refresh_gamification(connection)
        return next(habit for habit in self.list_habits() if habit["id"] == cursor.lastrowid)

    def delete_habit(self, habit_id: int) -> bool:
        with self.connect() as connection:
            result = connection.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
            if result.rowcount:
                self._refresh_gamification(connection)
        return result.rowcount > 0

    def update_habit(
        self,
        habit_id: int,
        name: str | None = None,
        icon: str | None = None,
        daily_goal: int | None = None,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM habits WHERE id = ?", (habit_id,)
            ).fetchone()
            if existing is None:
                return None
            next_name = name.strip() if name is not None else existing["name"]
            next_icon = icon.strip() if icon is not None else existing["icon"]
            next_goal = daily_goal if daily_goal is not None else existing["daily_goal"]
            if not next_name or len(next_name) > 200:
                raise ValueError("Habit name must contain 1-200 characters.")
            if not next_icon:
                raise ValueError("Habit icon cannot be empty.")
            if (
                not isinstance(next_goal, int)
                or isinstance(next_goal, bool)
                or next_goal < 1
            ):
                raise ValueError("daily_goal must be a positive integer.")
            connection.execute(
                "UPDATE habits SET name = ?, icon = ?, daily_goal = ?, updated_at = ? "
                "WHERE id = ?",
                (next_name, next_icon, next_goal, _now(), habit_id),
            )
        return next(habit for habit in self.list_habits() if habit["id"] == habit_id)

    def set_habit_completion(self, habit_id: int, completion_date: str, completed: bool) -> dict[str, Any] | None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", completion_date):
            raise ValueError("completion_date must use YYYY-MM-DD format.")
        with self.connect() as connection:
            if connection.execute("SELECT 1 FROM habits WHERE id = ?", (habit_id,)).fetchone() is None:
                return None
            existing = connection.execute(
                "SELECT 1 FROM habit_completions WHERE habit_id = ? AND completion_date = ?",
                (habit_id, completion_date),
            ).fetchone()
            xp_delta = 0
            if completed and existing is None:
                connection.execute(
                    "INSERT INTO habit_completions(habit_id, completion_date, created_at) VALUES (?, ?, ?)",
                    (habit_id, completion_date, _now()),
                )
                xp_delta = HABIT_COMPLETION_XP
            elif not completed and existing is not None:
                connection.execute(
                    "DELETE FROM habit_completions WHERE habit_id = ? AND completion_date = ?",
                    (habit_id, completion_date),
                )
                xp_delta = -HABIT_COMPLETION_XP
            connection.execute("UPDATE habits SET updated_at = ? WHERE id = ?", (_now(), habit_id))
            self._refresh_gamification(connection, xp_delta)
        return next(habit for habit in self.list_habits() if habit["id"] == habit_id)

    def get_gamification(self) -> dict[str, Any]:
        with self.connect() as connection:
            self._refresh_gamification(connection)
            data = self._get_gamification(connection)
        return {
            "xp": data["xp"],
            "global_streak": self._calculate_streak(data["valid_streak_dates"]),
            "valid_streak_dates": data["valid_streak_dates"],
            "achievements": data["achievements"],
        }

    def list_reminders(self, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM reminders"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY run_at"
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def create_reminder(
        self,
        text: str,
        run_at: str,
        recurrence: str | None = None,
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text or len(text) > 500:
            raise ValueError("Reminder text must contain 1-500 characters.")
        if not run_at.strip():
            raise ValueError("Reminder time cannot be empty.")
        reminder_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO reminders(id, text, run_at, recurrence, chat_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (reminder_id, text, run_at.strip(), recurrence, chat_id, _now()),
            )
            row = connection.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return dict(row)

    def get_reminder(self, reminder_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_notification(
        self, chat_id: str, reminder_id: str, content: str
    ) -> dict[str, Any]:
        created_at = _now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO notifications "
                "(chat_id, reminder_id, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, reminder_id, content, created_at),
            )
            row = connection.execute(
                "SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row)

    def list_notifications(self, chat_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notifications WHERE chat_id = ? AND id > ? "
                "ORDER BY id",
                (chat_id, after_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_notification_id(self, chat_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(id), 0) AS latest FROM notifications "
                "WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["latest"])

    def save_reminder_delivery_target(
        self,
        reminder_id: str,
        channel_id: int | None,
        guild_id: int | None,
        user_id: int,
    ) -> None:
        now = _now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO reminder_delivery_targets
                (reminder_id, channel_id, guild_id, user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(reminder_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    guild_id = excluded.guild_id,
                    user_id = excluded.user_id,
                    created_at = excluded.created_at
                """,
                (reminder_id, channel_id, guild_id, user_id, now),
            )

    def get_reminder_delivery_target(
        self, reminder_id: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reminder_delivery_targets WHERE reminder_id = ?",
                (reminder_id,),
            ).fetchone()
        return dict(row) if row else None

    def has_recent_coach_notification(
        self, chat_id: str, minutes: int = 30
    ) -> bool:
        """Return True if a task-coach notification was sent recently."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).isoformat()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM notifications WHERE chat_id = ? "
                "AND reminder_id LIKE 'task-coach-%' AND created_at > ? LIMIT 1",
                (chat_id, cutoff),
            ).fetchone()
        return row is not None

    def has_recent_weekly_nudge(
        self, chat_id: str, now: datetime | None = None, days: int = 6
    ) -> bool:
        """Return True if a weekly learning nudge landed in the last ``days``."""
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=days)).isoformat()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM notifications WHERE chat_id = ? "
                "AND reminder_id LIKE 'weekly-learning-nudge-%' "
                "AND created_at > ? LIMIT 1",
                (chat_id, cutoff),
            ).fetchone()
        return row is not None

    def set_reminder_active(
        self, reminder_id: str, active: bool, run_at: str | None = None
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            if run_at is not None:
                connection.execute(
                    "UPDATE reminders SET active = ?, run_at = ? WHERE id = ?",
                    (1 if active else 0, run_at, reminder_id),
                )
            else:
                connection.execute(
                    "UPDATE reminders SET active = ? WHERE id = ?",
                    (1 if active else 0, reminder_id),
                )
            row = connection.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return dict(row) if row else None

    def cancel_reminder(self, reminder_id: str) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE reminders SET active = 0 WHERE id = ?", (reminder_id,)
            )
        return result.rowcount > 0

    def list_memories(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, content, created_at, updated_at FROM memories "
                "ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_memory(self, content: str, embedding: list[float] | None = None) -> dict[str, Any]:
        content = content.strip()
        if not content or len(content) > MAX_MEMORY_TEXT:
            raise ValueError(f"Memory must contain 1-{MAX_MEMORY_TEXT} characters.")
        now = _now()
        if embedding is None:
            embedding = self.embed(content)
        serialized = json.dumps(embedding) if embedding is not None else None
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO memories(content, embedding, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (content, serialized, now, now),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("That memory already exists.") from error
        return {"id": cursor.lastrowid, "content": content, "created_at": now, "updated_at": now}

    def update_memory(self, memory_id: int, content: str) -> dict[str, Any] | None:
        content = content.strip()
        if not content or len(content) > MAX_MEMORY_TEXT:
            raise ValueError(f"Memory must contain 1-{MAX_MEMORY_TEXT} characters.")
        now = _now()
        embedding = self.embed(content)
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE memories SET content = ?, embedding = ?, updated_at = ? "
                "WHERE id = ?",
                (content, json.dumps(embedding) if embedding is not None else None, now, memory_id),
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                "SELECT id, content, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return dict(row)

    def delete_memory(self, memory_id: int) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
        return result.rowcount > 0

    def search_memories(self, query: str, limit: int = MAX_RETRIEVED_MEMORIES) -> list[dict[str, Any]]:
        ranked_by_id: dict[Any, tuple[float, dict[str, Any]]] = {}

        query_embedding = self.embed(query)
        if query_embedding is not None:
            q_len = len(query_embedding)
            query_norm = sum(value * value for value in query_embedding) ** 0.5
            with self.connect() as connection:
                rows = connection.execute(
                    "SELECT id, content, embedding, created_at, updated_at "
                    "FROM memories WHERE embedding IS NOT NULL"
                ).fetchall()
            for row in rows:
                try:
                    values = json.loads(row["embedding"])
                except Exception:
                    continue
                if not isinstance(values, list) or len(values) != q_len:
                    continue
                denominator = query_norm * (sum(value * value for value in values) ** 0.5)
                score = sum(a * b for a, b in zip(query_embedding, values)) / denominator if denominator else 0.0
                if score >= 0.35:
                    item = dict(row)
                    item["score"] = float(score)
                    ranked_by_id[item["id"]] = (float(score), item)

        # Hybrid lexical + stemmed + typo-tolerant + semantic-concept fallback across ALL memories
        stop_words = {
            "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
            "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
            "have", "has", "had", "the", "a", "an", "of", "to", "in", "on", "for",
            "with", "about", "from", "by", "at", "as", "into", "my", "me", "i",
            "you", "your", "kind", "type", "tell", "know", "saved", "remember",
        }
        concept_groups = [
            {"food", "dish", "dishes", "meal", "meals", "eat", "eating", "cuisine", "snack", "breakfast", "lunch", "dinner", "biryani", "chicken", "spicy", "restaurant"},
            {"like", "likes", "love", "loves", "favorite", "favourite", "prefer", "prefers", "enjoy", "enjoys", "fond"},
            {"laptop", "pc", "computer", "hardware", "specs", "gpu", "cpu", "ram", "asus", "tuf", "ryzen", "rtx", "machine"},
            {"skill", "skills", "tech", "stack", "programming", "language", "languages", "framework", "frameworks", "code", "coding", "developer", "react", "python", "javascript", "cpp", "dsa", "java"},
            {"startup", "business", "company", "venture", "lighthouse", "client", "clients"},
            {"project", "projects", "app", "apps", "application", "applications", "built", "building", "developing", "kage", "orbit"},
            {"study", "studies", "education", "college", "diploma", "degree", "student", "course", "branch", "learn", "exam", "interview"},
            {"goal", "goals", "aim", "ambition", "future", "career", "plan"},
            {"name", "called", "identity", "who"},
            {"email", "mail", "gmail", "inbox"},
            {"routine", "morning", "habit", "schedule", "workout", "gym", "sleep"},
        ]

        def _norm_mem_tokens(text: str) -> set[str]:
            norm = re.sub(r"(?<![a-z0-9])c\s*\+\s*\+(?![a-z0-9])", " cpp ", text.lower())
            norm = re.sub(r"\bc\s+plus\s+plus\b", " cpp ", norm)
            norm = re.sub(r"(?<![a-z0-9])c\s*#(?![a-z0-9])", " csharp ", norm)
            toks = set(re.findall(r"[a-z0-9]+", norm))
            stems = set(toks)
            for t in toks:
                if t in ("learnt", "learned", "learning"):
                    stems.add("learn")
                elif t in ("studied", "studies", "studying"):
                    stems.add("study")
                elif t in ("coded", "coding"):
                    stems.add("code")
                elif len(t) >= 5 and t.endswith("ies"):
                    stems.add(t[:-3] + "y")
                elif len(t) >= 5 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
                    stems.add(t[:-1])
            return stems

        raw_terms = _norm_mem_tokens(query)
        meaningful_terms = raw_terms - stop_words
        if not meaningful_terms:
            meaningful_terms = raw_terms

        # Expand query terms with concept synonyms
        expanded_terms = set(meaningful_terms)
        for group in concept_groups:
            if meaningful_terms & group:
                expanded_terms |= group

        try:
            from rapidfuzz.distance import DamerauLevenshtein
            _mem_sim = lambda a, b: DamerauLevenshtein.normalized_similarity(a, b) * 100.0
        except Exception:
            try:
                from rapidfuzz import fuzz as _rf_fuzz
                _mem_sim = _rf_fuzz.ratio
            except Exception:
                _mem_sim = None

        for memory in self.list_memories():
            mem_id = memory["id"]
            mem_terms = _norm_mem_tokens(memory["content"])
            exact_hits = len(meaningful_terms & mem_terms)
            concept_hits = len(expanded_terms & mem_terms)
            fuzzy_bonus = 0.0
            if exact_hits == 0 and _mem_sim is not None:
                long_q = [t for t in meaningful_terms if len(t) >= 4]
                long_m = [t for t in mem_terms if len(t) >= 4]
                if long_q and long_m:
                    for qt in long_q[:6]:
                        best = max((_mem_sim(qt, mt) for mt in long_m), default=0.0)
                        if best >= 80.0:
                            fuzzy_bonus += 0.22 * (best / 100.0)
            if exact_hits == 0 and concept_hits == 0 and fuzzy_bonus == 0.0:
                continue
            lex_score = exact_hits * 0.25 + concept_hits * 0.12 + min(0.45, fuzzy_bonus)
            existing = ranked_by_id.get(mem_id)
            if existing is None or lex_score > existing[0]:
                mem_copy = dict(memory)
                mem_copy["score"] = round(max(lex_score, existing[0] if existing else 0.0), 3)
                ranked_by_id[mem_id] = (mem_copy["score"], mem_copy)

        ranked_list = sorted(ranked_by_id.values(), key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked_list[:limit]]

    def embed(self, text: str) -> list[float] | None:
        if os.environ.get("AI_ENABLE_SEMANTIC_MEMORY", "1") == "0":
            return None
        if self._embedder is not None:
            try:
                return self._embedder.encode(text, normalize_embeddings=True).tolist()
            except Exception:
                pass

        # 1. Try in-process model registry first (fast, no Ollama VRAM swap)
        try:
            from runtime.models import REGISTRY
            if REGISTRY.is_ready("embedder"):
                self._embedder = REGISTRY.get("embedder")
                return self._embedder.encode(text, normalize_embeddings=True).tolist()
        except Exception:
            pass

        # 2. Optional Ollama embedding endpoint (only if explicitly enabled via AI_OLLAMA_EMBEDDINGS=1
        # to prevent unloading/swapping the main chat LLM on single-GPU machines)
        if os.environ.get("AI_OLLAMA_EMBEDDINGS", "0") == "1" and not getattr(self, "_ollama_embed_failed", False):
            try:
                ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
                embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip()
                payload = json.dumps({"model": embed_model, "prompt": text}).encode("utf-8")
                import urllib.request
                req = urllib.request.Request(
                    f"{ollama_url}/api/embeddings",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "embedding" in data and isinstance(data["embedding"], list):
                        return data["embedding"]
            except Exception:
                self._ollama_embed_failed = True

        if not self._embedding_warning_printed:
            LOGGER.info("Semantic memory model unavailable; using hybrid lexical-concept retrieval.")
            self._embedding_warning_printed = True
        return None

    def build_context(
        self,
        chat_id: str,
        tokenizer: Any,
        query: str,
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> list[dict[str, str]]:
        messages = self.get_messages(chat_id)
        selected: list[dict[str, str]] = []
        for message in reversed(messages):
            candidate = {"role": message["role"], "content": message["content"]}
            trial = [candidate, *selected]
            try:
                if tokenizer is None:
                    raise TypeError("Tokenizer not loaded")
                encoded = tokenizer.apply_chat_template(
                    trial, tokenize=True, add_generation_prompt=True
                )
                if isinstance(encoded, dict) or hasattr(encoded, "input_ids"):
                    ids = encoded["input_ids"]
                    token_count = len(ids[0]) if ids and isinstance(ids[0], list) else len(ids)
                else:
                    token_count = len(encoded)
            except Exception:
                token_count = sum(len(item["content"]) // 4 + 8 for item in trial)
            if token_count > max_tokens:
                break
            selected = trial
        return selected

    def clear_all_data(self) -> dict[str, int]:
        """Delete all user records across core and learning tables in the SQLite database."""
        tables_to_wipe = (
            "messages",
            "notifications",
            "external_sessions",
            "reminder_delivery_targets",
            "reminders",
            "conversations",
            "memories",
            "tasks",
            "habit_completions",
            "habits",
            "learning_code_chunks_fts",
            "learning_code_chunks",
            "topic_code_evidence",
            "learning_code_files",
            "learning_folders",
            "learning_activities",
            "task_topic_links",
            "topic_prerequisites",
            "topics",
            "roadmaps",
        )
        deleted_counts: dict[str, int] = {}
        with self.connect() as connection:
            existing_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in tables_to_wipe:
                if table in existing_tables:
                    cur = connection.execute(f"DELETE FROM {table}")
                    deleted_counts[table] = max(0, cur.rowcount)
            if "gamification" in existing_tables:
                connection.execute(
                    "UPDATE gamification SET xp = 0, valid_streak_dates = '[]', "
                    "achievements = '[]', updated_at = ? WHERE id = 1",
                    (_now(),),
                )
        return deleted_counts


