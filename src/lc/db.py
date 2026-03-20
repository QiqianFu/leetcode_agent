from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

from lc.config import DB_PATH
from lc.models import Attempt, Problem, Review, TagStat

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


SCHEMA_VERSION = 2

# Each migration is a list of SQL statements to run.
# Index 0 = migration from version 0 to 1 (initial schema), etc.
_MIGRATIONS = [
    # v0 → v1: initial schema
    [
        """CREATE TABLE IF NOT EXISTS problems (
            id            INTEGER PRIMARY KEY,
            title         TEXT NOT NULL,
            title_slug    TEXT NOT NULL UNIQUE,
            difficulty    TEXT NOT NULL CHECK(difficulty IN ('Easy','Medium','Hard')),
            description   TEXT,
            ac_rate       REAL,
            fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS problem_tags (
            problem_id    INTEGER NOT NULL REFERENCES problems(id),
            tag           TEXT NOT NULL,
            PRIMARY KEY (problem_id, tag)
        )""",
        """CREATE TABLE IF NOT EXISTS attempts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id    INTEGER NOT NULL REFERENCES problems(id),
            started_at    TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at   TEXT,
            self_rating   INTEGER CHECK(self_rating BETWEEN 1 AND 5),
            hints_used    INTEGER NOT NULL DEFAULT 0,
            teach_used    INTEGER NOT NULL DEFAULT 0,
            notes         TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS reviews (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id    INTEGER NOT NULL REFERENCES problems(id),
            due_date      TEXT NOT NULL,
            interval_days INTEGER NOT NULL,
            completed     INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS tag_stats (
            tag           TEXT PRIMARY KEY,
            total_attempts INTEGER NOT NULL DEFAULT 0,
            avg_rating    REAL NOT NULL DEFAULT 0,
            last_practiced TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS session (
            key           TEXT PRIMARY KEY,
            value         TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_reviews_due ON reviews(due_date) WHERE completed = 0",
        "CREATE INDEX IF NOT EXISTS idx_attempts_problem ON attempts(problem_id)",
        "CREATE INDEX IF NOT EXISTS idx_problem_tags_tag ON problem_tags(tag)",
    ],
    # v1 → v2: add code_snippet column
    [
        "ALTER TABLE problems ADD COLUMN code_snippet TEXT DEFAULT ''",
    ],
]


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version, 0 if no schema_version table exists."""
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist — check if this is a fresh DB or pre-versioning DB
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "problems" in tables:
            # Pre-versioning DB: already has tables, figure out version
            cols = {r[1] for r in conn.execute("PRAGMA table_info(problems)").fetchall()}
            return 2 if "code_snippet" in cols else 1
        return 0


def init_db() -> None:
    conn = get_connection()

    # Create version tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)
    conn.commit()

    current = _get_schema_version(conn)

    # Run pending migrations
    for i in range(current, SCHEMA_VERSION):
        for sql in _MIGRATIONS[i]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # e.g. column already exists
        conn.commit()

    # Update version
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


# --------------- problems ---------------

def upsert_problem(p: Problem) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO problems (id, title, title_slug, difficulty, description, ac_rate, code_snippet)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               title=excluded.title, title_slug=excluded.title_slug,
               difficulty=excluded.difficulty, description=excluded.description,
               ac_rate=excluded.ac_rate, code_snippet=excluded.code_snippet,
               fetched_at=datetime('now')""",
        (p.id, p.title, p.title_slug, p.difficulty, p.description, p.ac_rate, p.code_snippet),
    )
    # replace tags
    conn.execute("DELETE FROM problem_tags WHERE problem_id = ?", (p.id,))
    for tag in p.tags:
        conn.execute(
            "INSERT INTO problem_tags (problem_id, tag) VALUES (?, ?)",
            (p.id, tag),
        )
    conn.commit()


def get_problem(problem_id: int) -> Problem | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()
    if row is None:
        return None
    p = Problem.from_row(row)
    tags = conn.execute(
        "SELECT tag FROM problem_tags WHERE problem_id = ?", (problem_id,)
    ).fetchall()
    p.tags = [r["tag"] for r in tags]
    # Load code_snippet if available in row
    try:
        p.code_snippet = row["code_snippet"] or ""
    except (IndexError, KeyError):
        pass
    return p


# --------------- attempts ---------------

def create_attempt(problem_id: int) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO attempts (problem_id) VALUES (?)", (problem_id,)
    )
    conn.commit()
    return cur.lastrowid


def get_attempt(attempt_id: int) -> Attempt | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    return Attempt.from_row(row) if row else None


def finish_attempt(attempt_id: int, self_rating: int, notes: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE attempts SET finished_at = datetime('now'),
           self_rating = ?, notes = ? WHERE id = ?""",
        (self_rating, notes, attempt_id),
    )
    conn.commit()


def undo_finish_attempt(attempt_id: int) -> None:
    """Revert a finished attempt back to in-progress state."""
    conn = get_connection()
    conn.execute(
        "UPDATE attempts SET finished_at = NULL, self_rating = NULL, notes = NULL WHERE id = ?",
        (attempt_id,),
    )
    conn.commit()


def delete_reviews_for_attempt(problem_id: int, after_time: str) -> None:
    """Delete reviews created after a given time for a problem."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM reviews WHERE problem_id = ? AND created_at >= ?",
        (problem_id, after_time),
    )
    conn.commit()


def increment_hints(attempt_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE attempts SET hints_used = hints_used + 1 WHERE id = ?", (attempt_id,)
    )
    conn.commit()


def increment_teach(attempt_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE attempts SET teach_used = teach_used + 1 WHERE id = ?", (attempt_id,)
    )
    conn.commit()


# --------------- reviews ---------------

def insert_reviews(reviews: list[Review]) -> None:
    conn = get_connection()
    conn.executemany(
        "INSERT INTO reviews (problem_id, due_date, interval_days) VALUES (?, ?, ?)",
        [(r.problem_id, r.due_date, r.interval_days) for r in reviews],
    )
    conn.commit()


def get_pending_reviews(as_of: str | None = None) -> list[Review]:
    if as_of is None:
        as_of = date.today().isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reviews WHERE due_date <= ? AND completed = 0 ORDER BY due_date",
        (as_of,),
    ).fetchall()
    return [Review.from_row(r) for r in rows]


def get_pending_reviews_by_problem(as_of: str | None = None) -> list[Review]:
    """Return pending reviews deduplicated by problem_id, keeping the earliest due one."""
    deduped: list[Review] = []
    seen_problem_ids: set[int] = set()
    for review in get_pending_reviews(as_of=as_of):
        if review.problem_id in seen_problem_ids:
            continue
        seen_problem_ids.add(review.problem_id)
        deduped.append(review)
    return deduped


def complete_review(review_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE reviews SET completed = 1 WHERE id = ?", (review_id,))
    conn.commit()


def complete_due_reviews(problem_id: int, as_of: str | None = None) -> None:
    """Mark all currently due reviews for a problem as completed."""
    if as_of is None:
        as_of = date.today().isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE reviews SET completed = 1 WHERE problem_id = ? AND due_date <= ? AND completed = 0",
        (problem_id, as_of),
    )
    conn.commit()


def cancel_future_reviews(problem_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE reviews SET completed = 1 WHERE problem_id = ? AND completed = 0",
        (problem_id,),
    )
    conn.commit()


def get_active_review_for_problem(problem_id: int) -> Review | None:
    conn = get_connection()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM reviews WHERE problem_id = ? AND due_date <= ? AND completed = 0 ORDER BY due_date LIMIT 1",
        (problem_id, today),
    ).fetchone()
    return Review.from_row(row) if row else None


# --------------- tag_stats ---------------

def update_tag_stats(problem_id: int) -> None:
    conn = get_connection()
    tags = conn.execute(
        "SELECT tag FROM problem_tags WHERE problem_id = ?", (problem_id,)
    ).fetchall()
    for (tag,) in tags:
        stats = conn.execute(
            """SELECT COUNT(*) as total, AVG(a.self_rating) as avg_rating,
                      MAX(a.started_at) as last_practiced
               FROM attempts a
               JOIN problem_tags pt ON a.problem_id = pt.problem_id
               WHERE pt.tag = ? AND a.self_rating IS NOT NULL""",
            (tag,),
        ).fetchone()
        if stats and stats["total"] > 0:
            conn.execute(
                """INSERT INTO tag_stats (tag, total_attempts, avg_rating, last_practiced)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(tag) DO UPDATE SET
                       total_attempts=excluded.total_attempts,
                       avg_rating=excluded.avg_rating,
                       last_practiced=excluded.last_practiced""",
                (tag, stats["total"], stats["avg_rating"], stats["last_practiced"]),
            )
    conn.commit()


def get_weakest_tags(limit: int = 5) -> list[TagStat]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tag_stats WHERE total_attempts >= 1 ORDER BY avg_rating DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [TagStat.from_row(r) for r in rows]


def get_all_tag_stats() -> list[TagStat]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tag_stats ORDER BY avg_rating DESC"
    ).fetchall()
    return [TagStat.from_row(r) for r in rows]


# --------------- session ---------------

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


# --------------- stats helpers ---------------

def get_attempt_stats() -> dict:
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(DISTINCT problem_id) as cnt FROM attempts WHERE self_rating IS NOT NULL"
    ).fetchone()["cnt"]
    by_diff = conn.execute(
        """SELECT p.difficulty, COUNT(DISTINCT a.problem_id) as cnt
           FROM attempts a JOIN problems p ON a.problem_id = p.id
           WHERE a.self_rating IS NOT NULL
           GROUP BY p.difficulty"""
    ).fetchall()
    avg = conn.execute(
        "SELECT AVG(self_rating) as avg FROM attempts WHERE self_rating IS NOT NULL"
    ).fetchone()["avg"]
    pending = len(get_pending_reviews_by_problem())
    # Recent 7 days
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_7d = conn.execute(
        "SELECT COUNT(DISTINCT problem_id) as cnt FROM attempts WHERE self_rating IS NOT NULL AND started_at >= ?",
        (week_ago,),
    ).fetchone()["cnt"]

    # Streak: consecutive days with at least one completed attempt
    streak_rows = conn.execute(
        """SELECT DISTINCT date(started_at) as d FROM attempts
           WHERE self_rating IS NOT NULL ORDER BY d DESC"""
    ).fetchall()
    streak = 0
    expected = date.today()
    for row in streak_rows:
        d = date.fromisoformat(row["d"])
        if d == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        elif d < expected:
            break

    return {
        "total_solved": total,
        "by_difficulty": {r["difficulty"]: r["cnt"] for r in by_diff},
        "avg_rating": avg or 0,
        "pending_reviews": pending,
        "recent_7d": recent_7d,
        "streak": streak,
    }


def get_unsolved_by_tags(tags: list[str], limit: int = 5) -> list[Problem]:
    """Get problems matching given tags that haven't been attempted yet."""
    conn = get_connection()
    if not tags:
        return []
    placeholders = ",".join("?" * len(tags))
    rows = conn.execute(
        f"""SELECT DISTINCT p.* FROM problems p
            JOIN problem_tags pt ON p.id = pt.problem_id
            WHERE pt.tag IN ({placeholders})
              AND p.id NOT IN (
                  SELECT DISTINCT problem_id FROM attempts
              )
            ORDER BY RANDOM()
            LIMIT ?""",
        (*tags, limit),
    ).fetchall()
    problems = []
    for row in rows:
        p = Problem.from_row(row)
        t = conn.execute("SELECT tag FROM problem_tags WHERE problem_id = ?", (p.id,)).fetchall()
        p.tags = [r["tag"] for r in t]
        problems.append(p)
    return problems


def get_attempted_problem_ids() -> set[int]:
    """Return problem IDs that have been attempted, including abandoned/in-progress ones."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT problem_id FROM attempts"
    ).fetchall()
    return {r["problem_id"] for r in rows}


def get_solved_problem_ids() -> set[int]:
    """Backward-compatible alias for attempted problem IDs."""
    return get_attempted_problem_ids()
