from __future__ import annotations

import sqlite3

from lc.config import DB_PATH

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS problem_memories (
            problem_id    INTEGER PRIMARY KEY,
            title         TEXT NOT NULL,
            difficulty    TEXT,
            tags          TEXT,
            memory_file   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session (
            key           TEXT PRIMARY KEY,
            value         TEXT
        );
    """)
    # Drop legacy tables from old schema (one-time cleanup)
    for table in ("problems", "problem_tags", "attempts", "reviews", "tag_stats", "schema_version", "sqlite_sequence"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


# ─── Problem memories ───

def upsert_memory(problem_id: int, title: str, memory_file: str,
                   difficulty: str = "", tags: str = "") -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO problem_memories (problem_id, title, difficulty, tags, memory_file)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(problem_id) DO UPDATE SET
               title=excluded.title, difficulty=excluded.difficulty,
               tags=excluded.tags, memory_file=excluded.memory_file""",
        (problem_id, title, difficulty, tags, memory_file),
    )
    conn.commit()


def get_memory(problem_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM problem_memories WHERE problem_id = ?", (problem_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "problem_id": row["problem_id"],
        "title": row["title"],
        "difficulty": row["difficulty"],
        "tags": row["tags"],
        "memory_file": row["memory_file"],
    }


def get_all_memories() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM problem_memories ORDER BY problem_id").fetchall()
    return [{
        "problem_id": r["problem_id"],
        "title": r["title"],
        "difficulty": r["difficulty"],
        "tags": r["tags"],
        "memory_file": r["memory_file"],
    } for r in rows]


def get_practiced_problem_ids() -> set[int]:
    """Return problem IDs that have memory entries (i.e. have been practiced)."""
    conn = get_connection()
    rows = conn.execute("SELECT problem_id FROM problem_memories").fetchall()
    return {r["problem_id"] for r in rows}


# ─── Session ───

def set_session(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO session (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_session(key: str) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM session WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def delete_session(key: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM session WHERE key = ?", (key,))
    conn.commit()


def clear_session() -> None:
    conn = get_connection()
    conn.execute("DELETE FROM session")
    conn.commit()
