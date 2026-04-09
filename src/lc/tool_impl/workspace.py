"""Workspace / file operation tools."""
from __future__ import annotations

import json
from pathlib import Path

from lc import db
from lc.display import console
from lc.workspace import (
    problem_files_in_workspace,
    relative_workspace_path,
    slugify,
    workspace_file_payload,
    workspace_root,
)


def tool_check_problem(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    result: dict = {"problem_id": problem_id}
    if memory:
        result.update({
            "has_memory": True,
            "title": memory["title"],
            "difficulty": memory["difficulty"],
            "tags": memory["tags"],
            "memory_file": memory["memory_file"],
        })
    else:
        result["has_memory"] = False
        try:
            from lc.leetcode_api import fetch_problem
            problem = fetch_problem(problem_id)
            result.update({
                "title": problem.title,
                "difficulty": problem.difficulty,
                "tags": problem.tags,
            })
        except Exception:
            result["message"] = "未找到该题目信息。"
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
    content = p.read_text(encoding="utf-8")
    # Extract problem_id from filename (e.g. "72_edit_distance.py" -> 72)
    pid: int | None = None
    try:
        pid = int(p.stem.split("_")[0])
    except (ValueError, IndexError):
        pass
    reminder = ""
    if pid:
        reminder = (
            f"\n\n[reminder: 当你给出实质性指导后，"
            f"记得调用 analyze_and_memorize(problem_id={pid}) 写入记忆]"
        )
    return content + reminder


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


def tool_search_workspace_files(keyword: str = "", **_) -> str:
    keyword = (keyword or "").strip()
    if not keyword:
        return "请传入 keyword。"

    needle = keyword.lower().replace(" ", "_")
    matches = []
    for path in problem_files_in_workspace():
        rel = relative_workspace_path(path)
        haystacks = {
            path.stem.lower(),
            rel.lower(),
            path.parent.name.lower(),
        }
        if any(needle in h or keyword.lower() in h for h in haystacks):
            matches.append(workspace_file_payload(path))
        if len(matches) >= 10:
            break

    return json.dumps(
        {"keyword": keyword, "matches": matches, "count": len(matches)},
        ensure_ascii=False,
    )


def tool_list_category_problems(category: str = "", **_) -> str:
    category = (category or "").strip()
    if not category:
        return "请传入 category。"

    root = workspace_root()
    raw = category.lower()
    normalized = slugify(category)
    matched_dirs = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.lower()
        if name == raw or name == normalized or raw in name or normalized in name:
            matched_dirs.append(child)

    if not matched_dirs:
        return json.dumps(
            {"category": category, "matches": [], "count": 0,
             "message": "当前工作区内未找到匹配的分类目录。"},
            ensure_ascii=False,
        )

    directory = sorted(matched_dirs, key=lambda p: p.name)[0]
    files = sorted(
        (p for p in directory.glob("*.py") if p.is_file()),
        key=lambda p: p.name,
    )
    matches = [workspace_file_payload(path) for path in files[:50]]
    return json.dumps(
        {"category": category, "directory": relative_workspace_path(directory),
         "matches": matches, "count": len(matches)},
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
