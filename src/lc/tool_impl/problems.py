"""Problem search, listing, selection tools (atomic primitives)."""
from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.display import console
from lc.ui import arrow_select
from lc.workspace import start_problem


# ─── Pure data reads (no UI, no hidden state) ───

def tool_search_leetcode(keyword: str = "", limit: int = 5, **_) -> str:
    """Search LeetCode by English keyword. Returns candidate list JSON (no UI)."""
    if not keyword:
        return json.dumps(
            {"error": True, "message": "请传入 keyword 参数。"},
            ensure_ascii=False,
        )
    limit = min(max(1, limit), 20)
    from lc.leetcode_api import search_problems

    results = search_problems(keyword, limit=limit)
    if not results:
        return json.dumps(
            {"keyword": keyword, "problems": [],
             "message": f"没有找到与「{keyword}」相关的题目。"},
            ensure_ascii=False,
        )
    return json.dumps({
        "keyword": keyword,
        "problems": [
            {
                "id": p.id,
                "title": p.title,
                "difficulty": p.difficulty,
                "tags": p.tags,
                "ac_rate": p.ac_rate,
                "title_slug": p.title_slug,
            }
            for p in results
        ],
    }, ensure_ascii=False)


def tool_list_hot_problems(
    tag: str | None = None,
    difficulty: str | None = None,
    company: str | None = None,
    limit: int = 10,
    randomize: bool | None = None,
    **_,
) -> str:
    """List CodeTop hot problems (already filters practiced). Returns JSON (no UI).

    Missing params fall back to /config defaults. Response includes `used_filters`
    so the model can see what was actually applied.
    """
    from lc.cli import get_config
    from lc.planner import _pick_from_codetop

    eff_company = (company if company is not None else get_config("company")) or None
    eff_tag = (tag if tag is not None else get_config("tag")) or None
    eff_difficulty = (difficulty if difficulty is not None else get_config("difficulty")) or None
    eff_randomize = randomize if randomize is not None else (get_config("mode") == "random")
    limit = min(max(1, limit), 30)

    candidates = _pick_from_codetop(
        company=eff_company,
        difficulty=eff_difficulty,
        tag=eff_tag,
        limit=limit,
        randomize=eff_randomize,
    )

    used_filters = {
        "company": eff_company,
        "tag": eff_tag,
        "difficulty": eff_difficulty,
        "randomize": eff_randomize,
    }

    if not candidates:
        return json.dumps({
            "problems": [],
            "used_filters": used_filters,
            "message": "没有找到未做过的高频题。可尝试放宽筛选条件（去掉 tag/difficulty 或切换 company）。",
        }, ensure_ascii=False)

    return json.dumps({
        "problems": [
            {
                "id": p.id,
                "title": p.title,
                "difficulty": p.difficulty,
                "title_slug": p.title_slug,
            }
            for p in candidates
        ],
        "used_filters": used_filters,
        "note": "已自动过滤用户已做过的题目。",
    }, ensure_ascii=False)


def tool_list_practiced(
    tag: str | None = None,
    difficulty: str | None = None,
    limit: int = 30,
    **_,
) -> str:
    """List user's practiced problems (from L3 memory index) with optional filtering.

    Pure local DB read. Complements list_hot_problems: that one returns future
    candidates, this one returns past done problems.
    """
    from lc.codetop_api import expand_tag_synonyms

    limit = min(max(1, limit), 200)
    all_memories = db.get_all_memories()

    filtered = []
    tag_synonyms = expand_tag_synonyms(tag) if (tag or "").strip() else []
    diff_q = (difficulty or "").strip().title()

    for m in all_memories:
        if diff_q and (m.get("difficulty") or "").title() != diff_q:
            continue
        if tag_synonyms:
            mtags = (m.get("tags") or "").lower()
            if not any(syn in mtags for syn in tag_synonyms):
                continue
        filtered.append({
            "problem_id": m["problem_id"],
            "title": m["title"],
            "difficulty": m.get("difficulty") or "",
            "tags": m.get("tags") or "",
        })

    truncated = len(filtered) > limit
    return json.dumps({
        "total_matched": len(filtered),
        "returned": min(len(filtered), limit),
        "truncated": truncated,
        "problems": filtered[:limit],
        "filters": {"tag": tag, "difficulty": difficulty},
    }, ensure_ascii=False)


# ─── Optional UI tool (only when model wants user to self-pick) ───

def tool_let_user_pick(choices: list | None = None, prompt: str = "", **_) -> str:
    """Present candidates to user via arrow_select. Returns chosen id JSON.

    Use when you have multiple equally-good candidates; skip when you have a
    strong recommendation (just call start_problem directly).
    """
    if not choices:
        return json.dumps(
            {"error": True, "message": "请传入 choices 参数（非空数组）。"},
            ensure_ascii=False,
        )

    if prompt:
        console.print(f"\n[cyan]{prompt}[/cyan]")

    formatted = []
    for c in choices:
        if not isinstance(c, dict) or "id" not in c:
            continue
        label = f"#{c['id']} {c.get('title', '')}"
        if c.get("difficulty"):
            label += f" ({c['difficulty']})"
        formatted.append((label, c))

    if not formatted:
        return json.dumps(
            {"error": True,
             "message": "choices 格式错误，应为 [{id, title, difficulty}, ...]。"},
            ensure_ascii=False,
        )

    selected = arrow_select(formatted)
    if not selected:
        return json.dumps(
            {"status": "cancelled", "message": "用户取消选择。"},
            ensure_ascii=False,
        )

    return json.dumps({
        "status": "selected",
        "selected_id": selected["id"],
        "title": selected.get("title", ""),
        "difficulty": selected.get("difficulty", ""),
    }, ensure_ascii=False)


# ─── Action tool (unchanged) ───

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
