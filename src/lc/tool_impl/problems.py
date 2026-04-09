"""Problem selection and planning tools."""
from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.ui import arrow_select
from lc.workspace import start_problem


def tool_search_problem(keyword: str = "", **_) -> str:
    from lc.leetcode_api import search_problems
    results = search_problems(keyword, limit=5)
    if not results:
        return f"没有找到与「{keyword}」相关的题目。"

    choices = [
        (f"#{p.id} {p.title} ({p.difficulty})", p)
        for p in results
    ]
    selected = arrow_select(choices)
    if not selected:
        return "用户未选择题目。"
    return json.dumps({
        "selected_id": selected.id,
        "title": selected.title,
        "difficulty": selected.difficulty,
    }, ensure_ascii=False)


def tool_pick_problem(tag: str | None = None, difficulty: str | None = None, **_) -> str:
    from lc.planner import _pick_from_codetop
    from lc.cli import get_config

    page_size = 5
    candidates = _pick_from_codetop(
        company=get_config("company"),
        difficulty=difficulty or get_config("difficulty"),
        tag=tag or get_config("tag"),
        limit=page_size * 5,
        randomize=get_config("mode") == "random",
    )

    if not candidates:
        return "没有找到合适的题目。"

    choices = [(f"#{p.id} {p.title} ({p.difficulty})", p) for p in candidates[:page_size]]
    remaining = candidates[page_size:]

    def load_more():
        nonlocal remaining
        batch = remaining[:page_size]
        remaining = remaining[page_size:]
        return [(f"#{p.id} {p.title} ({p.difficulty})", p) for p in batch]

    selected = arrow_select(choices, load_more=load_more if remaining else None)
    if not selected:
        return "用户未选择题目。"
    return json.dumps({
        "selected_id": selected.id,
        "title": selected.title,
        "difficulty": selected.difficulty,
    }, ensure_ascii=False)


def tool_start_problem(problem_id: int | None = None, *, client: OpenAI, **_) -> str:
    result = start_problem(problem_id, client)
    if isinstance(result, str):
        return result
    problem, rel_path, memory_path = result
    return json.dumps(
        {
            "status": "started",
            "problem_id": problem.id,
            "problem": f"{problem.id}. {problem.title}",
            "difficulty": problem.difficulty,
            "tags": problem.tags,
            "file": str(rel_path),
            "memory_file": str(memory_path.relative_to(Path.cwd())),
        },
        ensure_ascii=False,
    )


def tool_get_daily_plan(**_) -> str:
    from lc.planner import generate_daily_plan
    from lc.cli import get_config
    plan = generate_daily_plan(
        company=get_config("company"),
        difficulty=get_config("difficulty"),
        tag=get_config("tag"),
        randomize=get_config("mode") == "random",
    )
    from lc.display import show_daily_plan
    show_daily_plan(plan)
    result = {
        "new_problems": [
            {"problem_id": p.id, "title": p.title, "difficulty": p.difficulty}
            for p in plan.new_problems
        ],
    }
    return json.dumps(result, ensure_ascii=False)


def tool_get_hot_problems(company: str | None = None, tag: str | None = None, **_) -> str:
    from lc.codetop_api import fetch_hot_problems
    from lc.cli import get_config
    company = company or get_config("company") or None
    tag = tag or get_config("tag") or None
    problems, total = fetch_hot_problems(company=company, tag=tag, page=1, page_size=20)
    practiced_ids = db.get_practiced_problem_ids()
    from lc.display import show_hot_problems
    show_hot_problems(problems, practiced_ids, company)
    result = [
        {"problem_id": p.leetcode_id, "title": p.title, "difficulty": p.difficulty,
         "frequency": p.frequency, "practiced": p.leetcode_id in practiced_ids}
        for p in problems
    ]
    return json.dumps({"hot_problems": result, "total": total}, ensure_ascii=False)
