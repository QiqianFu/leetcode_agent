"""Sub-agent tools and web search."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.config import DEEPSEEK_MODEL, USER_MEMORY_PATH
from lc.display import console
from lc.workspace import workspace_root

logger = logging.getLogger("lc.agent")


# ─── Sub-agent infrastructure ───

def _sub_agent_call(client: OpenAI, main_messages: list[dict],
                    task_instruction: str, max_tokens: int = 2048) -> str:
    """Sub-agent call that reuses main agent's message prefix for KV cache.

    Strips the trailing assistant message (containing tool_calls) to recover
    the exact prefix that was sent to _call_model — this maximises provider-side
    KV cache hits. Passes tools=TOOLS with tool_choice="none" so the tools
    portion of the prompt hash matches the main agent request.
    """
    from lc.tool_defs import TOOLS
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


def _has_l3_content(memory_file: str) -> bool:
    """Return True if the memory file has actual L3 content beyond the initial header.

    The initial template from create_memory_file() only has title/difficulty/tags/link.
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


# ─── Tool implementations ───

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


def tool_update_user_memory(*, client: OpenAI, messages: list[dict], **_) -> str:
    existing = ""
    if USER_MEMORY_PATH.exists():
        existing = USER_MEMORY_PATH.read_text(encoding="utf-8").strip()

    task = (
        "你现在的任务是更新用户偏好记忆文件。"
        "根据上面的对话上下文，提取用户表达的编码偏好、辅导偏好、习惯等个人偏好信息。\n\n"
        f"现有记忆文件内容：\n{existing or '（空）'}\n\n"
        "规则：\n"
        "- 输出完整的最终版记忆文件，你的输出会直接覆盖旧文件\n"
        "- 保留现有记忆中仍然有效的内容，整合新信息，矛盾时以新信息为准\n"
        "- 每个主题只出现一次，不要有重复段落\n"
        "- 用 markdown 格式，分类记录（编码风格、辅导偏好、薄弱点、已掌握模式等）\n"
        "- 保持简洁\n"
        "- 直接输出内容，不要加任何解释"
    )
    result = _sub_agent_call(client, messages, task)
    if not result:
        return "更新用户偏好记忆失败（子 agent 无响应）。"

    USER_MEMORY_PATH.write_text(result, encoding="utf-8")
    return "已更新用户偏好记忆。"


def tool_find_similar_problems(problem_id: int | None = None,
                               *, client: OpenAI, messages: list[dict], **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。"

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

    result_data: dict = {"problem_id": problem_id, "similar_problems": similar_results}
    if similar_results:
        result_data["instruction"] = (
            "请告诉用户这道题与以下已做过的题目思路相似，可以从类似方向思考。"
            "同时根据相似题的历史记忆，分析用户是否有进步/退步/风格变化，"
            "如果发现有值得记录的变化，请调用 update_user_memory。"
        )
    return json.dumps(result_data, ensure_ascii=False)


def tool_analyze_and_memorize(problem_id: int | None = None,
                              *, client: OpenAI, messages: list[dict], **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"

    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。请先用 start_problem 开始做题。"

    matches = list(workspace_root().glob(f"**/{problem_id}_*.py"))
    solution_code = ""
    if matches:
        solution_code = matches[0].read_text(encoding="utf-8")

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
        "- 输出完整的最终版记忆文件，你的输出会直接覆盖旧文件\n"
        "- 保留现有记忆中有价值的部分，整合新信息，每个 ## 标题只出现一次\n"
        "- 简洁直接，每个部分 2-3 句话\n"
        "- 直接输出内容，不要加任何解释"
    )
    l3_result = _sub_agent_call(client, messages, task)

    if not l3_result:
        return json.dumps({"l3_written": False, "problem_id": problem_id,
                           "message": "总结生成失败。"}, ensure_ascii=False)

    memory_path.write_text(l3_result, encoding="utf-8")
    return json.dumps({"l3_written": True, "problem_id": problem_id}, ensure_ascii=False)
