from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.config import DEEPSEEK_MODEL, USER_MEMORY_PATH
from lc.display import console

logger = logging.getLogger("lc.agent")
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
            "description": "从 CodeTop 高频题库推荐题目供用户选择。仅在用户没有指定题型/关键词、只是说'开始刷题''来一道题'时使用。如果用户指定了题型（如'来一道 DP 题''树的题'），应改用 search_problem 搜索更精准的结果。",
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
            "description": "用英文关键词搜索 LeetCode 题目。返回匹配的题目列表供用户选择。当用户指定了题型或关键词（如'来一道 DP 题''二叉树的题''背包问题'）时优先使用此工具。注意：只支持英文搜索，用户说中文时你需要自行翻译成英文关键词。",
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
    {
        "type": "function",
        "function": {
            "name": "update_user_memory",
            "description": "当用户表达了编码偏好、辅导偏好、习惯等个人偏好时调用。子 agent 会根据当前对话上下文自动合并更新长期偏好记忆文件。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_problems",
            "description": "查找用户已做过的题目中与当前题目算法思路相似的题。开始做一道新题后调用，帮助用户联系过往经验。返回相似题的记忆内容供你引导用户思考方向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "当前题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_memorize",
            "description": "将当前题目的分析写入 L3 记忆文件。当你检查了用户答案、给出了指导、或用户表示做完时调用。子 agent 根据对话上下文和用户代码自动生成总结。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
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
    content = p.read_text(encoding="utf-8")
    # Extract problem_id from filename (e.g. "72_edit_distance.py" -> 72)
    problem_id = None
    try:
        problem_id = int(p.stem.split("_")[0])
    except (ValueError, IndexError):
        pass
    reminder = ""
    if problem_id:
        reminder = (
            f"\n\n[reminder: 当你给出实质性指导后，"
            f"记得调用 analyze_and_memorize(problem_id={problem_id}) 写入记忆]"
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


# ─── Sub-agent infrastructure ───

def _sub_agent_call(client: OpenAI, main_messages: list[dict],
                    task_instruction: str, max_tokens: int = 2048) -> str:
    """Sub-agent call that reuses main agent's message prefix for KV cache.

    main_messages is the exact messages list from Agent.chat() at tool execution
    time, which ends with the current assistant message (containing tool_calls).
    We strip that trailing assistant message to get the prefix that was sent to
    _call_model — this is the cached prefix on the provider side.

    We then append a user message with the task instruction. The provider sees:
        [system + tools + history ... | user(task)]
    where everything before the | is an exact prefix match with the main agent's
    last _call_model call, so KV cache hits fully.

    We also pass tools=TOOLS with tool_choice="none" so the tools portion of the
    prompt matches the main agent's request exactly (tools affect the prompt hash).
    """
    # Strip trailing assistant message to recover the exact cached prefix
    prefix = main_messages[:-1] if main_messages else []
    messages = prefix + [{"role": "user", "content": task_instruction}]
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="none",
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.error("sub-agent call failed: %s", e)
        return ""


def tool_update_user_memory(*, client: OpenAI, messages: list[dict], **_) -> str:
    existing = ""
    if USER_MEMORY_PATH.exists():
        existing = USER_MEMORY_PATH.read_text(encoding="utf-8").strip()

    task = (
        "你现在的任务是更新用户偏好记忆文件。"
        "根据上面的对话上下文，提取用户表达的编码偏好、辅导偏好、习惯等个人偏好信息。\n\n"
        f"现有记忆文件内容：\n{existing or '（空）'}\n\n"
        "规则：\n"
        "- 保留现有记忆中仍然有效的内容\n"
        "- 合并新的偏好信息\n"
        "- 如果新信息与旧信息矛盾，以新信息为准\n"
        "- 用 markdown 格式，分类记录（编码风格、辅导偏好、薄弱点、已掌握模式等）\n"
        "- 保持简洁，避免重复\n"
        "- 直接输出完整的记忆文件内容，不要加任何解释"
    )
    result = _sub_agent_call(client, messages, task)
    if not result:
        return "更新用户偏好记忆失败（子 agent 无响应）。"

    USER_MEMORY_PATH.write_text(result, encoding="utf-8")
    return "已更新用户偏好记忆。"


def _has_l3_content(memory_file: str) -> bool:
    """Check if a memory file has actual L3 content beyond the initial metadata header.

    Initial template from create_memory_file() only has title/difficulty/tags/link.
    analyze_and_memorize (or write_memory) adds '## ' sections like '## 解题思路'.
    """
    path = Path(memory_file)
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return "\n## " in content


def tool_find_similar_problems(problem_id: int | None = None,
                               *, client: OpenAI, messages: list[dict], **_) -> str:
    """Find similar practiced problems for the given problem."""
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。"

    # Build practiced problems list: only include problems with actual L3 content
    # (not just the initial metadata header from start_problem)
    all_memories = db.get_all_memories()
    practiced = [
        m for m in all_memories
        if m["problem_id"] != problem_id and _has_l3_content(m["memory_file"])
    ]
    problems_list = "\n".join(
        f"#{m['problem_id']} {m['title']} ({m['difficulty']}) [{m['tags']}]"
        for m in practiced
    )
    if not problems_list.strip():
        return json.dumps({"problem_id": problem_id, "similar_problems": [],
                           "message": "暂无有记忆的已做题目可供比较。"}, ensure_ascii=False)

    console.print("[dim]  ⚙ 正在查找相似题...[/dim]")

    task = (
        f"你现在的任务是从用户已做过的题目中，找出与第 {problem_id} 题算法思路最相似的题目（最多 3 道）。\n\n"
        f"当前题目：#{memory['problem_id']} {memory['title']} ({memory['difficulty']}) [{memory['tags']}]\n\n"
        f"已做过的题目：\n{problems_list}\n\n"
        "相似性判断依据：算法思路相同、数据结构相同、解题模式相同（如都是滑动窗口、都是拓扑排序等）。\n"
        "结合上面对话中用户正在解题的思路来判断相似性。\n\n"
        '输出格式：每行一个题号（纯数字），不要其他内容。如果没有相似题就输出"无"。'
    )
    result = _sub_agent_call(client, messages, task, max_tokens=128)

    # Parse similar IDs
    similar_ids: list[int] = []
    if result:
        for line in result.strip().splitlines():
            line = line.strip()
            if line == "无":
                similar_ids = []
                break
            nums = re.findall(r"\d+", line)
            if nums:
                similar_ids.append(int(nums[0]))
        similar_ids = similar_ids[:3]

    # Validate: DB exists + memory file has actual L3 content
    similar_results = []
    hallucination_count = 0
    for pid in similar_ids:
        sim_memory = db.get_memory(pid)
        if not sim_memory:
            hallucination_count += 1
            continue
        if not _has_l3_content(sim_memory["memory_file"]):
            continue
        sim_content = Path(sim_memory["memory_file"]).read_text(encoding="utf-8")
        similar_results.append({
            "problem_id": pid,
            "title": sim_memory["title"],
            "difficulty": sim_memory["difficulty"],
            "tags": sim_memory["tags"],
            "memory": sim_content,
        })
    if hallucination_count > 1:
        similar_results = []

    result_data = {"problem_id": problem_id, "similar_problems": similar_results}
    if similar_results:
        result_data["instruction"] = (
            "请告诉用户这道题与以下已做过的题目思路相似，可以从类似方向思考。"
            "同时根据相似题的历史记忆，分析用户是否有进步/退步/风格变化，"
            "如果发现有值得记录的变化，请调用 update_user_memory。"
        )
    return json.dumps(result_data, ensure_ascii=False)


def tool_analyze_and_memorize(problem_id: int | None = None,
                              *, client: OpenAI, messages: list[dict], **_) -> str:
    """Write L3 memory summary for a problem."""
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。请先用 start_problem 开始做题。"

    # Read current solution file
    matches = list(workspace_root().glob(f"**/{problem_id}_*.py"))
    solution_code = ""
    if matches:
        solution_code = matches[0].read_text(encoding="utf-8")

    # Read existing L3
    memory_path = Path(memory["memory_file"])
    existing_l3 = ""
    if memory_path.exists():
        existing_l3 = memory_path.read_text(encoding="utf-8")

    console.print("[dim]  ⚙ 正在生成题目总结...[/dim]")

    task = (
        f"你现在的任务是为第 {problem_id} 题写一份做题总结记忆。\n\n"
        f"题目：#{memory['problem_id']} {memory['title']} ({memory['difficulty']}) [{memory['tags']}]\n\n"
        f"用户代码：\n```python\n{solution_code or '（未找到代码文件）'}\n```\n\n"
        f"现有记忆：\n{existing_l3 or '（空）'}\n\n"
        "根据上面的对话上下文（你给的提示、发现的错误、用户的思路等）和用户代码，生成总结。\n\n"
        "记忆格式（markdown）：\n"
        "1. 保留文件开头的题目元信息（标题、难度、标签、链接）\n"
        "2. 追加或更新以下内容：\n"
        "   - ## 解题思路：用了什么算法/数据结构，核心想法\n"
        "   - ## 踩坑记录：遇到的错误、走过的弯路\n"
        "   - ## 关键收获：这道题学到了什么\n"
        "   - ## 复杂度：时间和空间复杂度\n\n"
        "规则：\n"
        "- 简洁直接，每个部分 2-3 句话\n"
        "- 如果已有记忆内容，保留有价值的部分，整合新信息\n"
        "- 直接输出完整的记忆文件内容，不要加任何解释"
    )
    l3_result = _sub_agent_call(client, messages, task)

    if not l3_result:
        return json.dumps({"l3_written": False, "problem_id": problem_id,
                           "message": "总结生成失败。"}, ensure_ascii=False)

    memory_path.write_text(l3_result, encoding="utf-8")
    return json.dumps({"l3_written": True, "problem_id": problem_id}, ensure_ascii=False)


# ─── Dispatcher ───

# Map tool names to (handler_function, needs_client, needs_messages)
# needs_messages=True: sub-agent tools that reuse main agent's message prefix for KV cache
_TOOL_REGISTRY: dict[str, tuple] = {
    "check_problem":          (tool_check_problem, False, False),
    "read_solution":          (tool_read_solution, False, False),
    "find_problem_file":      (tool_find_problem_file, False, False),
    "search_workspace_files": (tool_search_workspace_files, False, False),
    "list_category_problems": (tool_list_category_problems, False, False),
    "append_solution":        (tool_append_solution, False, False),
    "search_problem":         (tool_search_problem, False, False),
    "pick_problem":           (tool_pick_problem, False, False),
    "start_problem":          (tool_start_problem, True, False),
    "read_memory":            (tool_read_memory, False, False),
    "write_memory":           (tool_write_memory, False, False),
    "get_daily_plan":         (tool_get_daily_plan, False, False),
    "get_hot_problems":       (tool_get_hot_problems, False, False),
    "web_search":             (tool_web_search, False, False),
    "update_user_memory":     (tool_update_user_memory, True, True),
    "find_similar_problems":  (tool_find_similar_problems, True, True),
    "analyze_and_memorize":   (tool_analyze_and_memorize, True, True),
}


def execute_tool(name: str, arguments: str, client: OpenAI,
                 messages: list[dict] | None = None) -> str:
    """Dispatch a tool call by name. Returns the result string.

    messages: the main agent's full messages list (for sub-agent KV cache reuse).
    Must be the exact same list object used in Agent.chat() so the prefix matches.
    """
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

    handler, needs_client, needs_messages = entry
    try:
        if needs_messages:
            return handler(**args, client=client, messages=messages or [])
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
