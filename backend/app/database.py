import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .schemas import Metadata, ModelMessage


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self, *, read_write: bool = False) -> sqlite3.Connection:
        location = f"{self.path.as_uri()}?mode=rw" if read_write else self.path
        connection = sqlite3.connect(location, timeout=5, uri=read_write)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self.connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        system_prompt TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS messages_session_order
                    ON messages (session_id, id);
                """)
        except (OSError, sqlite3.Error):
            raise RuntimeError("Could not initialize SQLite. Check DATABASE_URL and directory permissions.") from None

    def ping(self) -> None:
        with closing(self.connect(read_write=True)) as connection:
            connection.execute("SELECT id FROM sessions LIMIT 1").fetchone()
            connection.execute("SELECT id FROM messages LIMIT 1").fetchone()

    def context(self, session_id: str) -> tuple[str | None, list[ModelMessage]]:
        with closing(self.connect(read_write=True)) as connection, connection:
            connection.execute("BEGIN")
            session = connection.execute(
                "SELECT system_prompt FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            rows = connection.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return (
            session["system_prompt"] if session else None,
            [{"role": row["role"], "content": row["content"]} for row in rows],
        )

    def history(self, session_id: str) -> list[dict] | None:
        with closing(self.connect(read_write=True)) as connection:
            rows = connection.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        if not rows:
            return None
        messages = []
        for row in rows:
            message = {"role": row["role"], "content": row["content"]}
            if row["role"] == "assistant":
                message["metadata"] = json.loads(row["metadata"]) if row["metadata"] else None
            messages.append(message)
        return messages

    def save_turn(
        self, session_id: str, system_prompt: str, user_text: str, reply: str, metadata: Metadata
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        with closing(self.connect(read_write=True)) as connection, connection:
            connection.execute(
                """
                INSERT INTO sessions (id, system_prompt) VALUES (?, ?)
                ON CONFLICT (id) DO UPDATE SET system_prompt = excluded.system_prompt
                """,
                (session_id, system_prompt),
            )
            connection.executemany(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (session_id, "user", user_text, None, created_at),
                    (session_id, "assistant", reply, metadata.model_dump_json(), created_at),
                ],
            )
