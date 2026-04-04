from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.display import console
from lc.ui import arrow_select
from lc.workspace import (
    relative_workspace_path,
    slugify,
    start_problem,
    workspace_file_payload,
    workspace_root,
    problem_files_in_workspace,
)

# ─── Tool schema definitions ───

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_problem",
            "description": "按题号查询题目信息。返回题目元信息和是否有记忆文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_solution",
            "description": "读取用户的解题代码文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "解题文件路径"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_problem_file",
            "description": "在当前工作区内按题号查找本地解题文件。只搜索当前 CLI 启动目录及其子目录，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_workspace_files",
            "description": "在当前工作区内按文件名关键词搜索本地题目文件。适合用户只记得题目名或部分关键词时使用。只搜索本地工作区，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "文件名或题目关键词"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_category_problems",
            "description": "列出当前工作区内某个分类文件夹下的题目文件。适合用户只记得题型或文件夹名时使用。只查看本地工作区目录，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类/文件夹名，如 dp、graph、tree、string"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_solution",
            "description": "将参考解法追加到用户的解题文件末尾（不会覆盖用户代码）。用户要求看答案、给正确解法时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "解题文件路径"},
                    "content": {"type": "string", "description": "参考解法代码"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pick_problem",
            "description": "推荐题目列表供用户选择。默认按 /config 配置（公司、难度、标签、排序模式），也可传 tag/difficulty 临时覆盖。用户用自然语言指定题型（如'来一道 DP 题'）时，传对应 tag 参数即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "临时指定标签筛选，如 dp, graph, heap, 二分查找。覆盖 /config 中的 tag 设置"},
                    "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"], "description": "临时指定难度筛选，覆盖 /config 中的 difficulty 设置"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_problem",
            "description": "用英文关键词搜索 LeetCode 题目。返回匹配的题目列表供用户选择。注意：只支持英文搜索，用户说中文时你需要自行翻译成英文关键词。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "英文搜索关键词，如 climbing stairs, two sum, LRU"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_problem",
            "description": "开始做指定题号的 LeetCode 题（用户明确给了题号时使用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "读取某道题的记忆文件内容。用于回顾做题记录、判断是否需要复习等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "写入或追加内容到某道题的记忆文件。记录做题心得、难点、提示使用、总结等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                    "content": {"type": "string", "description": "要写入的内容（markdown 格式）"},
                    "mode": {"type": "string", "enum": ["append", "overwrite"], "description": "写入模式：append 追加，overwrite 覆盖。默认 append"},
                },
                "required": ["problem_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_plan",
            "description": "生成今日刷题计划（新题推荐），基于用户 /config 中的设置",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_problems",
            "description": "查看高频题列表（从 CodeTop 获取，按用户配置的公司/标签筛选）",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "公司名（可选，默认用 /config 中的设置）"},
                    "tag": {"type": "string", "description": "标签名（可选，默认用 /config 中的设置）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取信息。适合查找算法讲解、题目思路、数据结构知识、面试经验等。当用户问的问题超出你已有知识范围，或需要最新信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（建议用英文以获得更好结果）"},
                    "max_results": {"type": "integer", "description": "返回结果数量，默认 5，最大 10"},
                },
                "required": ["query"],
            },
        },
    },
]


# ─── Tool implementations ───

def tool_check_problem(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    result = {"problem_id": problem_id}
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


def tool_read_solution(file_path: str = "", **_) -> str:
    if not file_path:
        return "请传入 file_path 参数。"
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
        limit=page_size * 5,  # fetch a generous pool for load-more
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
            "description": problem.description or "",
        },
        ensure_ascii=False,
    )


def tool_read_memory(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"
    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。"
    memory_path = Path(memory["memory_file"])
    if not memory_path.exists():
        return f"记忆文件不存在: {memory['memory_file']}"
    return memory_path.read_text(encoding="utf-8")


def tool_write_memory(problem_id: int | None = None, content: str = "",
                      mode: str = "append", **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"
    if not content:
        return "请传入要写入的 content。"
    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。请先用 start_problem 开始做题。"
    memory_path = Path(memory["memory_file"])

    if mode == "overwrite":
        memory_path.write_text(content, encoding="utf-8")
    else:
        with memory_path.open("a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
    return "已写入记忆文件。"


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


def tool_web_search(query: str = "", max_results: int = 5, **_) -> str:
    if not query:
        return "请传入 query 参数。"
    max_results = min(max(1, max_results), 10)
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return json.dumps({
            "error": True, "message": f"搜索失败: {e}",
            "hint": "请稍后重试，或换个关键词。",
        }, ensure_ascii=False)

    if not results:
        return json.dumps({"query": query, "results": [], "message": "未找到相关结果。"}, ensure_ascii=False)

    items = [
        {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
        for r in results
    ]
    return json.dumps({"query": query, "results": items}, ensure_ascii=False)


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


# ─── Dispatcher ───

# Map tool names to (handler_function, needs_client)
_TOOL_REGISTRY: dict[str, tuple] = {
    "check_problem":          (tool_check_problem, False),
    "read_solution":          (tool_read_solution, False),
    "find_problem_file":      (tool_find_problem_file, False),
    "search_workspace_files": (tool_search_workspace_files, False),
    "list_category_problems": (tool_list_category_problems, False),
    "append_solution":        (tool_append_solution, False),
    "search_problem":         (tool_search_problem, False),
    "pick_problem":           (tool_pick_problem, False),
    "start_problem":          (tool_start_problem, True),
    "read_memory":            (tool_read_memory, False),
    "write_memory":           (tool_write_memory, False),
    "get_daily_plan":         (tool_get_daily_plan, False),
    "get_hot_problems":       (tool_get_hot_problems, False),
    "web_search":             (tool_web_search, False),
}


def execute_tool(name: str, arguments: str, client: OpenAI) -> str:
    """Dispatch a tool call by name. Returns the result string."""
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": True,
            "tool": name,
            "message": f"参数 JSON 解析失败: {e}",
            "hint": "请检查工具参数格式是否正确。",
        }, ensure_ascii=False)

    entry = _TOOL_REGISTRY.get(name)
    if not entry:
        return json.dumps({
            "error": True,
            "tool": name,
            "message": f"未知工具: {name}",
            "hint": "请检查工具名称是否正确。可用工具: " + ", ".join(_TOOL_REGISTRY.keys()),
        }, ensure_ascii=False)

    handler, needs_client = entry
    try:
        if needs_client:
            return handler(**args, client=client)
        return handler(**args)
    except Exception as e:
        return json.dumps({
            "error": True,
            "tool": name,
            "error_type": type(e).__name__,
            "message": str(e),
            "hint": "工具执行出错，请检查参数或稍后重试。",
        }, ensure_ascii=False)
