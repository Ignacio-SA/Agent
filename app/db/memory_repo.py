import sqlite3
from datetime import datetime

from ..config import settings
from ..models.memory import MemoryEntry


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.memory_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory_db():
    """Crea las tablas si no existen. Se llama al iniciar la app."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chatbot_memory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL UNIQUE,
                user_id    TEXT    NOT NULL,
                context    TEXT,
                summary    TEXT,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                agent_type TEXT,
                created_at TEXT    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id)")
        conn.commit()


class MemoryRepository:
    @staticmethod
    def create(entry: MemoryEntry) -> int:
        now = datetime.now().isoformat()
        with _get_conn() as conn:
            # Upsert: si ya existe la sesión, actualiza
            existing = conn.execute(
                "SELECT id FROM chatbot_memory WHERE session_id = ?", (entry.session_id,)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE chatbot_memory SET context=?, summary=?, updated_at=? WHERE session_id=?",
                    (entry.context, entry.summary, now, entry.session_id),
                )
                conn.commit()
                return existing["id"]
            else:
                cursor = conn.execute(
                    """INSERT INTO chatbot_memory (session_id, user_id, context, summary, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (entry.session_id, entry.user_id, entry.context, entry.summary, now, now),
                )
                conn.commit()
                return cursor.lastrowid

    @staticmethod
    def read(session_id: str) -> MemoryEntry | None:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM chatbot_memory WHERE session_id = ? ORDER BY updated_at DESC",
                (session_id,),
            ).fetchone()

            if row:
                return MemoryEntry(
                    id=row["id"],
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    context=row["context"],
                    summary=row["summary"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
        return None

    @staticmethod
    def update(session_id: str, context: str, summary: str) -> bool:
        with _get_conn() as conn:
            cursor = conn.execute(
                "UPDATE chatbot_memory SET context=?, summary=?, updated_at=? WHERE session_id=?",
                (context, summary, datetime.now().isoformat(), session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def list_all() -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, user_id, summary, created_at, updated_at FROM chatbot_memory ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def delete(session_id: str) -> bool:
        with _get_conn() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM chatbot_memory WHERE session_id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def save_message(session_id: str, role: str, content: str, agent_type: str = None):
        if content is None:
            content = ""
        now = datetime.now().isoformat()
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, agent_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, agent_type, now),
            )
            conn.commit()

    @staticmethod
    def get_messages(session_id: str) -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content, agent_type, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]


memory_repo = MemoryRepository()
