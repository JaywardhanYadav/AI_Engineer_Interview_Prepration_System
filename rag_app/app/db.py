"""PostgreSQL Database Layer for Users, Sessions, Conversations, and Interview History."""
from __future__ import annotations

import json
import logging
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import psycopg
from psycopg.rows import dict_row

from . import config

logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    """Context manager for PostgreSQL connection with dictionary row factory."""
    conn = psycopg.connect(config.PG_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize PostgreSQL tables for users, sessions, conversations, and interview history."""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS sessions (
        session_token VARCHAR(64) PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

    CREATE TABLE IF NOT EXISTS conversations (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title VARCHAR(255) DEFAULT 'New Chat',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);

    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        conversation_id INT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        sources JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

    CREATE TABLE IF NOT EXISTS interview_results (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        topic VARCHAR(100),
        difficulty VARCHAR(20),
        question TEXT NOT NULL,
        user_answer TEXT,
        score INT,
        verdict TEXT,
        strengths JSONB DEFAULT '[]'::jsonb,
        gaps JSONB DEFAULT '[]'::jsonb,
        model_answer TEXT,
        follow_up TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_interview_results_user_id ON interview_results(user_id);
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
    logger.info("PostgreSQL database tables initialized successfully.")


# ================= User & Session Management =================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_user(username: str, password: str) -> dict[str, Any]:
    username = username.strip().lower()
    if len(username) < 3 or len(password) < 4:
        raise ValueError("Username must be at least 3 characters and password at least 4 characters.")

    pw_hash = hash_password(password)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s;", (username,))
            if cur.fetchone():
                raise ValueError("Username already taken. Please choose another.")
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id, username, created_at;",
                (username, pw_hash),
            )
            return cur.fetchone()


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    username = username.strip().lower()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s;", (username,))
            user = cur.fetchone()
            if not user:
                return None
            if not verify_password(password, user["password_hash"]):
                return None
            return {"id": user["id"], "username": user["username"]}


def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=config.SESSION_EXPIRE_DAYS)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (session_token, user_id, expires_at) VALUES (%s, %s, %s);",
                (token, user_id, expires_at),
            )
    return token


def get_user_by_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.username, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.session_token = %s AND s.expires_at > NOW();
                """,
                (token,),
            )
            return cur.fetchone()


def delete_session(token: str) -> None:
    if not token:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE session_token = %s;", (token,))


# ================= Conversation Management =================

def create_conversation(user_id: int, title: str = "New Chat") -> dict[str, Any]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id, user_id, title, created_at, updated_at;",
                (user_id, title),
            )
            return cur.fetchone()


def list_conversations(user_id: int) -> list[dict[str, Any]]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.user_id = %s
                GROUP BY c.id
                ORDER BY c.updated_at DESC;
                """,
                (user_id,),
            )
            return cur.fetchall()


def get_conversation(conv_id: int, user_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE id = %s AND user_id = %s;",
                (conv_id, user_id),
            )
            conv = cur.fetchone()
            if not conv:
                return None

            cur.execute(
                "SELECT id, role, content, sources, created_at FROM messages WHERE conversation_id = %s ORDER BY id ASC;",
                (conv_id,),
            )
            conv["messages"] = cur.fetchall()
            return conv


def add_message(conv_id: int, role: str, content: str, sources: list[dict] | None = None) -> dict[str, Any]:
    sources_json = json.dumps(sources or [])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (conversation_id, role, content, sources)
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id, conversation_id, role, content, sources, created_at;
                """,
                (conv_id, role, content, sources_json),
            )
            msg = cur.fetchone()
            cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s;", (conv_id,))
            return msg


def update_conversation_title(conv_id: int, user_id: int, title: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET title = %s, updated_at = NOW() WHERE id = %s AND user_id = %s;",
                (title[:250], conv_id, user_id),
            )


def delete_conversation(conv_id: int, user_id: int) -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s RETURNING id;", (conv_id, user_id))
            return bool(cur.fetchone())


# ================= Mock Interview History =================

def save_interview_result(user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interview_results (
                    user_id, topic, difficulty, question, user_answer,
                    score, verdict, strengths, gaps, model_answer, follow_up
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb, %s, %s
                ) RETURNING id, score, verdict, created_at;
                """,
                (
                    user_id,
                    data.get("topic"),
                    data.get("difficulty"),
                    data.get("question"),
                    data.get("user_answer"),
                    data.get("score"),
                    data.get("verdict"),
                    json.dumps(data.get("strengths") or []),
                    json.dumps(data.get("gaps") or []),
                    data.get("model_answer"),
                    data.get("follow_up"),
                ),
            )
            return cur.fetchone()


def get_user_interview_stats(user_id: int) -> dict[str, Any]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) as total, AVG(score) as avg_score
                FROM interview_results WHERE user_id = %s;
                """,
                (user_id,),
            )
            summary = cur.fetchone()
            cur.execute(
                """
                SELECT topic, AVG(score) as avg_score, COUNT(*) as count
                FROM interview_results
                WHERE user_id = %s AND topic IS NOT NULL
                GROUP BY topic
                ORDER BY avg_score ASC;
                """,
                (user_id,),
            )
            by_topic = cur.fetchall()
            return {
                "total": summary["total"] or 0,
                "avg_score": round(float(summary["avg_score"] or 0.0), 1),
                "by_topic": by_topic,
            }
