from __future__ import annotations

import json

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


# ─── Plan mode ───

def is_plan_mode() -> bool:
    return db.get_session("plan_data") is not None


def get_plan() -> dict | None:
    raw = db.get_session("plan_data")
    if raw is None:
        return None
    return json.loads(raw)


def set_plan(plan: dict) -> None:
    db.set_session("plan_data", json.dumps(plan, ensure_ascii=False))


def clear_plan() -> None:
    db.delete_session("plan_data")


def advance_plan() -> dict | None:
    """Advance plan to next problem. Returns updated plan, or None if all done."""
    plan = get_plan()
    if plan is None:
        return None
    plan["current_index"] = plan.get("current_index", 0) + 1
    if plan["current_index"] >= len(plan["problems"]):
        clear_plan()
        return None
    set_plan(plan)
    return plan


def get_plan_progress() -> tuple[int, int] | None:
    """Returns (current_1based, total) or None if not in plan mode."""
    plan = get_plan()
    if plan is None:
        return None
    return plan.get("current_index", 0) + 1, len(plan["problems"])
