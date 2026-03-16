from __future__ import annotations

from lc import db


def set_current(problem_id: int, attempt_id: int, file_path: str = "") -> None:
    db.set_session("current_problem_id", str(problem_id))
    db.set_session("current_attempt_id", str(attempt_id))
    if file_path:
        db.set_session("current_file_path", file_path)


def get_current() -> tuple[int, int] | None:
    pid = db.get_session("current_problem_id")
    aid = db.get_session("current_attempt_id")
    if pid is None or aid is None:
        return None
    return int(pid), int(aid)


def get_file_path() -> str | None:
    return db.get_session("current_file_path")


def clear_current() -> None:
    db.delete_session("current_problem_id")
    db.delete_session("current_attempt_id")
    db.delete_session("current_file_path")
    db.delete_session("suspended_problem_id")
    db.delete_session("suspended_attempt_id")
    db.delete_session("suspended_file_path")


def suspend_current() -> None:
    """Move current state to suspended — get_current() will return None."""
    pid = db.get_session("current_problem_id")
    aid = db.get_session("current_attempt_id")
    fp = db.get_session("current_file_path")
    if pid and aid:
        db.set_session("suspended_problem_id", pid)
        db.set_session("suspended_attempt_id", aid)
        if fp:
            db.set_session("suspended_file_path", fp)
        db.delete_session("current_problem_id")
        db.delete_session("current_attempt_id")
        db.delete_session("current_file_path")


def resume_current() -> tuple[int, int] | None:
    """Restore suspended state back to current. Returns (pid, aid) or None."""
    pid = db.get_session("suspended_problem_id")
    aid = db.get_session("suspended_attempt_id")
    fp = db.get_session("suspended_file_path")
    if pid and aid:
        db.set_session("current_problem_id", pid)
        db.set_session("current_attempt_id", aid)
        if fp:
            db.set_session("current_file_path", fp)
        db.delete_session("suspended_problem_id")
        db.delete_session("suspended_attempt_id")
        db.delete_session("suspended_file_path")
        return int(pid), int(aid)
    return None
