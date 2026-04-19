"""Workspace / file operation tools."""
from __future__ import annotations

import json
from pathlib import Path

from lc import db
from lc.display import console, show_problem
from lc.workspace import (
    relative_workspace_path,
    workspace_root,
)


def tool_check_problem(problem_id: int | None = None, **_) -> str:
    """Local-only memory index lookup. Does NOT call LeetCode API."""
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    if memory:
        return json.dumps({
            "problem_id": problem_id,
            "has_memory": True,
            "title": memory["title"],
            "difficulty": memory["difficulty"],
            "tags": memory["tags"],
            "memory_file": memory["memory_file"],
        }, ensure_ascii=False)
    return json.dumps({
        "problem_id": problem_id,
        "has_memory": False,
    }, ensure_ascii=False)


def tool_display_problem(problem_id: int | None = None, **_) -> str:
    """Pretty-render a problem's full detail to user via Rich panel + markdown.

    Fetches from LeetCode (so description is guaranteed). Pure UI side-effect.
    Prefer this over inlining description text when you want the user to see
    the problem cleanly without consuming your own output budget.
    """
    if not problem_id:
        return json.dumps(
            {"error": True, "message": "请传入 problem_id。"},
            ensure_ascii=False,
        )
    try:
        from lc.leetcode_api import fetch_problem
        problem = fetch_problem(problem_id)
    except Exception as e:
        return json.dumps(
            {"error": True, "message": f"获取题目失败: {e}"},
            ensure_ascii=False,
        )
    show_problem(problem)
    return json.dumps({
        "status": "displayed",
        "problem_id": problem.id,
        "title": problem.title,
    }, ensure_ascii=False)


def tool_fetch_problem_detail(
    problem_id: int | None = None,
    title_slug: str = "",
    include_description: bool = True,
    **_,
) -> str:
    """Fetch full problem detail from LeetCode API. Does NOT create any local files."""
    if not problem_id and not title_slug:
        return json.dumps(
            {"error": True, "message": "请传入 problem_id 或 title_slug（至少一个）。"},
            ensure_ascii=False,
        )
    try:
        from lc.leetcode_api import fetch_problem, fetch_problem_by_slug
        problem = (
            fetch_problem_by_slug(title_slug) if title_slug
            else fetch_problem(problem_id)
        )
    except Exception as e:
        return json.dumps(
            {"error": True, "message": f"获取题目失败: {e}"},
            ensure_ascii=False,
        )

    result: dict = {
        "problem_id": problem.id,
        "title": problem.title,
        "title_slug": problem.title_slug,
        "difficulty": problem.difficulty,
        "tags": problem.tags,
    }
    if include_description and problem.description:
        result["description"] = problem.description
    if problem.code_snippet:
        result["code_snippet"] = problem.code_snippet
    return json.dumps(result, ensure_ascii=False)


def tool_read_solution(file_path: str = "", problem_id: int | None = None, **_) -> str:
    if not file_path and problem_id:
        matches = list(workspace_root().glob(f"**/{problem_id}_*.py"))
        if not matches:
            return f"当前工作区内未找到第 {problem_id} 题的本地文件。"
        file_path = str(matches[0])
    if not file_path:
        return "请传入 file_path 或 problem_id 参数。"
    p = Path(file_path).resolve()
    try:
        p.relative_to(workspace_root())
    except ValueError:
        return f"路径不在工作区内: {file_path}"
    if not p.exists():
        return f"文件不存在: {file_path}"
    return p.read_text(encoding="utf-8")


def tool_find_problem_file(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"
    matches = list(workspace_root().glob(f"**/{problem_id}_*.py"))
    if not matches:
        return json.dumps(
            {"problem_id": problem_id, "found": False,
             "message": f"当前工作区内未找到第 {problem_id} 题的本地文件。"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"problem_id": problem_id, "found": True,
         "file": relative_workspace_path(matches[0])},
        ensure_ascii=False,
    )


def tool_append_solution(file_path: str = "", content: str = "", **_) -> str:
    if not file_path:
        return "请传入 file_path 参数。"
    p = Path(file_path).resolve()
    try:
        p.relative_to(workspace_root())
    except ValueError:
        return f"路径不在工作区内: {file_path}"
    if not p.exists():
        return f"文件不存在: {file_path}"
    with p.open("a", encoding="utf-8") as f:
        f.write("\n\n# ─── 参考解法 ───\n\n")
        f.write(content)
        f.write("\n")
    console.print(f"[dim]参考解法已追加到 {file_path}[/dim]")
    return f"已追加到 {file_path}"
