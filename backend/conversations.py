import json
import uuid

from backend.db import connect

DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def init_db() -> None:
    with connect() as conn:
        conn.execute(DDL)


def create_conversation(title: str = "New chat") -> dict:
    cid = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title) VALUES (%s, %s)", (cid, title)
        )
    return {"id": cid, "title": title}


def list_conversations() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id::text, title, created_at FROM conversations"
            " ORDER BY created_at DESC"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "created_at": r[2].isoformat()} for r in rows
    ]


def conversation_exists(cid: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = %s", (cid,)
        ).fetchone()
    return row is not None


def delete_conversation(cid: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = %s", (cid,))
        return cur.rowcount > 0


def get_messages(cid: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content, sources FROM messages"
            " WHERE conversation_id = %s ORDER BY id",
            (cid,),
        ).fetchall()
    return [{"role": r[0], "content": r[1], "sources": r[2] or []} for r in rows]


def add_message(cid: str, role: str, content: str, sources: list | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sources)"
            " VALUES (%s, %s, %s, %s)",
            (cid, role, content, json.dumps(sources) if sources else None),
        )
        if role == "user":
            # first user message names the chat
            conn.execute(
                "UPDATE conversations SET title = %s"
                " WHERE id = %s AND title = 'New chat'",
                (content[:60], cid),
            )
