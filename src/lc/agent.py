from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from rich.live import Live
from rich.markdown import Markdown

from lc.config import (
    DATA_DIR,
    DEBUG,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    HISTORY_WARNING_THRESHOLD,
    MAX_AGENT_HISTORY_MESSAGES,
)
from lc.display import console
from lc.tools import TOOLS, execute_tool
from lc.ui import agent_renderable, flush_stdin

# ─── Logging setup ───

logger = logging.getLogger("lc.agent")


def _setup_logging():
    if not DEBUG:
        logger.setLevel(logging.WARNING)
        return
    logger.setLevel(logging.DEBUG)
    log_file = DATA_DIR / "agent.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.debug("=== session start ===")


_setup_logging()

# ─── System prompt ───

SYSTEM_PROMPT = """\
你是一个 LeetCode 刷题助手，在终端中和用户自由对话。用中文回答，简洁直接。

## 角色
- 帮用户选题、做题、复习
- 给提示时先引导思考，用户明确要求讲解时才给完整思路
- 用户意图明确时直接执行，不要反复确认

## 可用工具
你可以自主决定何时、以什么顺序调用工具。每轮你可以思考、调用工具、观察结果，然后决定下一步。

## 工具协作
- pick_problem / search_problem 返回的是用户选中的题目信息（selected_id），你需要接着调 start_problem 来真正开始做题（创建本地文件等）
- start_problem 返回 problem_id、file 路径和 memory_file 路径。后续如果忘了 file_path，可先调 find_problem_file 按 problem_id 找回
- 用户提到某道已存在的题、或想继续之前的题时，先调 check_problem 获取题目状态；需要文件时再调 find_problem_file
- read_solution / append_solution 需要 file_path 参数
- 如果只记得题号，可用 find_problem_file 找回本地文件
- 如果只记得题目名关键词，可用 search_workspace_files 搜当前工作区里的题目文件
- 如果只记得题型/文件夹，可用 list_category_problems 查看当前工作区对应分类目录

## 记忆系统
每道题都有一个对应的 markdown 记忆文件。你可以用 read_memory / write_memory 来读写题目的记忆。
- 做题过程中的提示、讲解、心得、难点、错误思路等，都应该记录到记忆文件中
- 用户说「提交」或做完题时，用 write_memory 把做题总结写入记忆文件
- 用户问复习、回顾时，读取相关题目的记忆文件来判断

## 注意事项
- search_problem 只支持英文关键词，需要时自行翻译
- 本地文件搜索范围严格限制在当前工作区（当前 CLI 启动目录）内
- 用户想看今日计划、高频题时，直接调用对应工具（get_daily_plan, get_hot_problems）"""

# ─── LLM client singleton ───

_llm_client: OpenAI | None = None


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60)
    return _llm_client


# ─── Agent ───

class Agent:
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            console.print("[red]错误: 请在 .env 文件中设置 DEEPSEEK_API_KEY[/red]")
            raise SystemExit(1)
        self.client = _get_llm_client()
        self.messages: list[dict] = []

    def chat(self, user_input: str):
        """Process user message through the agent loop."""
        flush_stdin()

        msg_count = len(self.messages)
        if msg_count >= MAX_AGENT_HISTORY_MESSAGES:
            remaining_memories = self._summarize_session_context()
            console.print(
                f"\n[bold yellow]⚠ 会话已达上限（{msg_count}/{MAX_AGENT_HISTORY_MESSAGES} 条消息）[/bold yellow]\n"
                "[yellow]当前对话历史过长，继续对话可能导致质量下降。[/yellow]\n"
                "[yellow]请使用 [bold]/clear[/bold] 开启新会话。[/yellow]"
            )
            if remaining_memories:
                console.print(
                    "[dim]提示：你的做题记忆已保存在 .memories/ 目录中，不会因清除会话而丢失。[/dim]"
                )
            logger.warning("history limit reached: %d messages", msg_count)
            return
        # Warn when approaching the limit
        warning_threshold = int(MAX_AGENT_HISTORY_MESSAGES * HISTORY_WARNING_THRESHOLD)
        if msg_count == warning_threshold:
            remaining = MAX_AGENT_HISTORY_MESSAGES - msg_count
            console.print(
                f"\n[yellow]💡 会话已使用 {msg_count}/{MAX_AGENT_HISTORY_MESSAGES} 条消息，"
                f"剩余约 {remaining} 条。建议适时 /clear 开启新会话。[/yellow]\n"
            )

        self.messages.append({"role": "user", "content": user_input})
        logger.debug("user: %s", user_input)

        # Static system prompt → KV cache prefix stays stable across calls
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages

        # ReAct loop: think → act → observe → repeat until no more tool calls
        for step in range(30):  # safety limit
            try:
                content, tool_calls, usage = self._call_model(messages)
            except self._RETRYABLE_ERRORS as e:
                console.print(f"[red]API 调用失败: {e}[/red]")
                console.print("[yellow]请稍后重试，或使用 /clear 开启新会话。[/yellow]")
                # Remove the user message we just appended so user can retry
                self.messages.pop()
                return
            logger.debug("step %d | tokens: %s | tools: %s | response: %s",
                         step, usage,
                         [tc["name"] for tc in tool_calls] if tool_calls else "none",
                         (content[:100] + "...") if content and len(content) > 100 else content)

            if not tool_calls:
                # No tool calls — final response, done
                self.messages.append({"role": "assistant", "content": content})
                return

            # Add assistant message with thinking + tool calls
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            self.messages.append(assistant_msg)

            # Execute tools — parallel when all are non-interactive
            _INTERACTIVE_TOOLS = {"pick_problem", "search_problem"}
            can_parallel = (
                len(tool_calls) > 1
                and not any(tc["name"] in _INTERACTIVE_TOOLS for tc in tool_calls)
            )

            if can_parallel:
                for tc in tool_calls:
                    console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                t0 = time.time()
                with ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
                    futures = {
                        pool.submit(execute_tool, tc["name"], tc["arguments"], self.client): tc
                        for tc in tool_calls
                    }
                    results_map: dict[str, str] = {}
                    for future in as_completed(futures):
                        tc = futures[future]
                        results_map[tc["id"]] = future.result()
                elapsed = time.time() - t0
                for tc in tool_calls:
                    result = results_map[tc["id"]]
                    logger.debug("tool %s(%s) → %.1fs (parallel) | result: %s",
                                 tc["name"], tc["arguments"], elapsed,
                                 (result[:200] + "...") if len(result) > 200 else result)
                    tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                    messages.append(tool_msg)
                    self.messages.append(tool_msg)
            else:
                for tc in tool_calls:
                    console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                    t0 = time.time()
                    result = execute_tool(tc["name"], tc["arguments"], self.client)
                    elapsed = time.time() - t0
                    logger.debug("tool %s(%s) → %.1fs | result: %s",
                                 tc["name"], tc["arguments"],
                                 elapsed,
                                 (result[:200] + "...") if len(result) > 200 else result)
                    tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                    messages.append(tool_msg)
                    self.messages.append(tool_msg)

            # Loop continues — model will see tool results and decide next step

        logger.warning("ReAct loop hit 30-step limit")
        console.print("[yellow]（已达到单轮推理上限，请继续对话）[/yellow]")

    def _summarize_session_context(self) -> bool:
        """Check if there are memory files referenced in this session.

        Returns True if any write_memory tool calls were made (meaning
        user has persisted memories that survive /clear).
        """
        for msg in self.messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    if fn.get("name") == "write_memory":
                        return True
        return False

    @staticmethod
    def _sanitize_messages(messages: list[dict]) -> list[dict]:
        """Remove surrogate characters that break UTF-8 encoding."""
        def clean(s):
            if not isinstance(s, str):
                return s
            return s.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")

        sanitized = []
        for msg in messages:
            msg = dict(msg)
            if "content" in msg and isinstance(msg["content"], str):
                msg["content"] = clean(msg["content"])
            sanitized.append(msg)
        return sanitized

    _RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
    _MAX_RETRIES = 2

    def _call_model(self, messages: list[dict]) -> tuple[str, list[dict], dict]:
        """Call DeepSeek with streaming and retry. Returns (content, tool_calls, usage)."""
        messages = self._sanitize_messages(messages)
        logger.debug("calling model with %d messages", len(messages))
        if DEBUG:
            logger.debug("messages dump:\n%s", json.dumps(messages, ensure_ascii=False, indent=2))

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                return self._call_model_once(messages)
            except self._RETRYABLE_ERRORS as e:
                if attempt < self._MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning("model call failed (attempt %d/%d): %s — retrying in %ds",
                                   attempt + 1, self._MAX_RETRIES + 1, e, wait)
                    console.print(f"[yellow]API 请求失败，{wait}s 后重试…[/yellow]")
                    time.sleep(wait)
                else:
                    logger.error("model call failed after %d attempts: %s",
                                 self._MAX_RETRIES + 1, e)
                    raise

        # Unreachable, but keeps type checker happy
        raise RuntimeError("unreachable")

    def _call_model_once(self, messages: list[dict]) -> tuple[str, list[dict], dict]:
        """Single attempt to call DeepSeek with streaming."""
        t0 = time.time()
        stream = self.client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
            stream=True,
            stream_options={"include_usage": True},
            temperature=0.3,
            max_tokens=4096,
        )

        content = ""
        tool_calls_map: dict[int, dict] = {}
        usage = {}
        live = None

        try:
            for chunk in stream:
                # Capture usage from the final chunk
                if chunk.usage:
                    usage = {
                        "prompt": chunk.usage.prompt_tokens,
                        "completion": chunk.usage.completion_tokens,
                        "total": chunk.usage.total_tokens,
                    }
                    if hasattr(chunk.usage, "prompt_cache_hit_tokens"):
                        usage["cache_hit"] = chunk.usage.prompt_cache_hit_tokens

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    if live is None:
                        live = Live(Markdown(""), console=console, refresh_per_second=8)
                        live.start()
                    content += delta.content
                    live.update(agent_renderable(content))

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_map[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_map[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_map[idx]["arguments"] += tc.function.arguments
        finally:
            if live is not None:
                live.stop()

        elapsed = time.time() - t0
        logger.debug("model responded in %.1fs | usage: %s", elapsed, usage)

        tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map)] if tool_calls_map else []
        return content, tool_calls, usage
