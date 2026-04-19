"""Tool dispatcher — the single entry point called by Agent.chat().

Schema definitions live in tool_defs.py.
Implementations are grouped in tool_impl/.
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI

from lc.tool_defs import TOOLS  # re-exported for agent.py
from lc.tool_impl import (
    tool_analyze_and_memorize,
    tool_append_solution,
    tool_check_problem,
    tool_display_problem,
    tool_fetch_problem_detail,
    tool_find_problem_file,
    tool_find_similar_problems,
    tool_let_user_pick,
    tool_list_hot_problems,
    tool_list_practiced,
    tool_read_memory,
    tool_read_solution,
    tool_search_leetcode,
    tool_start_problem,
    tool_update_user_memory,
    tool_web_search,
    tool_write_memory,
)

__all__ = ["TOOLS", "execute_tool"]

logger = logging.getLogger("lc.agent")

# (handler, needs_client, needs_messages)
_TOOL_REGISTRY: dict[str, tuple] = {
    "check_problem":          (tool_check_problem, False, False),
    "display_problem":        (tool_display_problem, False, False),
    "fetch_problem_detail":   (tool_fetch_problem_detail, False, False),
    "read_solution":          (tool_read_solution, False, False),
    "find_problem_file":      (tool_find_problem_file, False, False),
    "append_solution":        (tool_append_solution, False, False),
    "search_leetcode":        (tool_search_leetcode, False, False),
    "list_hot_problems":      (tool_list_hot_problems, False, False),
    "list_practiced":         (tool_list_practiced, False, False),
    "let_user_pick":          (tool_let_user_pick, False, False),
    "start_problem":          (tool_start_problem, True, False),
    "read_memory":            (tool_read_memory, False, False),
    "write_memory":           (tool_write_memory, False, False),
    "web_search":             (tool_web_search, False, False),
    "update_user_memory":     (tool_update_user_memory, True, True),
    "find_similar_problems":  (tool_find_similar_problems, True, True),
    "analyze_and_memorize":   (tool_analyze_and_memorize, True, True),
}


def execute_tool(name: str, arguments: str, client: OpenAI,
                 messages: list[dict] | None = None) -> str:
    """Dispatch a tool call by name. Returns the result string.

    messages: the main agent's full messages list (for sub-agent KV cache reuse).
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
