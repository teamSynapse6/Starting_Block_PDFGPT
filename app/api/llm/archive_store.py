import json
import sqlite3
from datetime import datetime, timezone
from app.core.config import SQLITE_ARCHIVE_PATH


class SQLiteArchiveStore:
    def __init__(self):
        self.db_path = SQLITE_ARCHIVE_PATH

    def initialize(self):
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS archived_sessions (
                    thread_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    archived_at TEXT NOT NULL,
                    announcement_id INTEGER,
                    messages_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def archive_session(self, session: dict):
        archived_at = datetime.now(timezone.utc).isoformat()
        messages_json = json.dumps(session.get("messages", []), ensure_ascii=False)

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO archived_sessions (
                    thread_id,
                    created_at,
                    last_activity,
                    archived_at,
                    announcement_id,
                    messages_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    last_activity=excluded.last_activity,
                    archived_at=excluded.archived_at,
                    announcement_id=excluded.announcement_id,
                    messages_json=excluded.messages_json
                """,
                (
                    session["thread_id"],
                    session["created_at"],
                    session["last_activity"],
                    archived_at,
                    session.get("announcement_id"),
                    messages_json,
                ),
            )
            connection.commit()
