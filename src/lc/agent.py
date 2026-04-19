from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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
    USER_MEMORY_PATH,
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
- 指导风格：用户刚开始做题时给提示引导思考；用户主动求助或明确表示困难时直接讲解
- 用户意图明确时直接执行，不反复确认

## 工具能力（你自主推理何时、如何组合）
以下只说明每个工具"做什么"，不规定调用时机和顺序。请结合对话上下文和 L1/L2 记忆自行判断。

**题库查询（只读，不弹 UI）**
- `search_leetcode(keyword, limit)` — 英文关键词搜 LeetCode 全站，返回候选列表
- `list_hot_problems(tag, difficulty, company, limit, randomize)` — CodeTop 高频题列表，自动过滤用户已做。未传参数会 fallback 到 /config，返回 `used_filters` 告知实际应用的筛选

**用户交互**
- `let_user_pick(choices, prompt)` — 把候选列表展示给用户，箭头选择器返回 `selected_id`

**开题与代码**
- `start_problem(id)` — 重型复合动作：拉题 + AI 分类 + 建 solution 文件 + 建 memory 文件 + 注册 DB
- `check_problem(id)` — 查题目元信息和是否做过（不返回 description）
- `find_problem_file(id)` — 按题号找本地解题文件路径
- `read_solution(file_path | problem_id)` — 读本地解题代码
- `append_solution(file_path, content)` — 追加参考解法到解题文件末尾

**记忆操作**
- `read_memory(id)` — 读 L3 题目记忆文件
- `write_memory(id, content, mode)` — 手动写 L3 记忆（你提供具体 content）
- `analyze_and_memorize(id)` — 触发子 agent 从对话上下文生成 L3 做题总结（内容由子 agent 决定）
- `update_user_memory()` — 触发子 agent 从对话上下文合并更新 L2 用户偏好（零参数）
- `find_similar_problems(id)` — 子 agent 从用户已做题中挑算法相似的题，返回它们的 L3 记忆

**外部**
- `web_search(query, max_results)` — 联网搜索

## 记忆系统
- **L1**: 工作区 `LeetCode.md`（用户手写指令，若存在会自动附在本 prompt 末尾）
- **L2**: `~/.leetcode_agent/user_memory.md`（跨会话用户偏好：编码风格、辅导偏好、薄弱点、已掌握模式；若存在会自动附在本 prompt 末尾）
- **L3**: 每题一份 `.memories/id_title.md`（通过 `read_memory` 按需读取）

L2 是个性化推荐和辅导的关键输入——出题时参考薄弱点/擅长点，讲解时参考偏好风格。

## 硬约束
- `search_leetcode` 只接受英文关键词，必要时自行翻译
- 所有本地文件搜索严格限制在当前工作区（CLI 启动目录）内
- `write_memory` 和 `analyze_and_memorize` 职责不同：前者你主动写具体内容，后者启动子 agent 根据对话上下文自动生成。不要混用
"""

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

        # Snapshot pre-turn message count for rollback on mid-loop API failure.
        # Prevents leaving orphaned assistant.tool_calls without matching tool responses,
        # which would cause DeepSeek to reject the next request with 400.
        pre_turn_count = len(self.messages)

        self.messages.append({"role": "user", "content": user_input})
        logger.debug("user: %s", user_input)

        messages = [{"role": "system", "content": self._build_system_prompt()}] + self.messages

        # ReAct loop: think → act → observe → repeat until no more tool calls
        for step in range(30):  # safety limit
            try:
                content, tool_calls, usage = self._call_model(messages)
            except self._RETRYABLE_ERRORS as e:
                console.print(f"[red]API 调用失败: {e}[/red]")
                console.print("[yellow]请稍后重试，或使用 /clear 开启新会话。[/yellow]")
                # Roll back entire turn — drop user msg + any partial assistant/tool msgs
                del self.messages[pre_turn_count:]
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

            # Execute tools — parallel when all are non-interactive and non-dependent
            _INTERACTIVE_TOOLS = {"let_user_pick"}
            # Tools with shared mutable state (DB rows, global L2 file) or expensive
            # sub-agent LLM calls stay serial. write_memory is per-problem file I/O,
            # no shared state → safe to parallelize.
            _SERIAL_TOOLS = {
                "start_problem",
                "find_similar_problems",
                "update_user_memory",
                "analyze_and_memorize",
            }
            _FORCE_SERIAL = _INTERACTIVE_TOOLS | _SERIAL_TOOLS
            can_parallel = (
                len(tool_calls) > 1
                and not any(tc["name"] in _FORCE_SERIAL for tc in tool_calls)
            )

            if can_parallel:
                for tc in tool_calls:
                    console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                t0 = time.time()
                with ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
                    futures = {
                        pool.submit(execute_tool, tc["name"], tc["arguments"],
                                    self.client, messages): tc
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
                    result = execute_tool(tc["name"], tc["arguments"],
                                         self.client, messages)
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

    @staticmethod
    def _build_system_prompt() -> str:
        """Build system prompt with L1 (LeetCode.md) and L2 (user_memory) context."""
        parts = [SYSTEM_PROMPT]

        # L1: LeetCode.md (workspace-local user instructions)
        leetcode_md = Path.cwd() / "LeetCode.md"
        if leetcode_md.exists():
            try:
                content = leetcode_md.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"\n\n## 用户自定义指令 (LeetCode.md)\n以下是用户的自定义指令，你必须遵守：\n\n{content}")
            except Exception:
                pass

        # L2: User preference memory (global)
        if USER_MEMORY_PATH.exists():
            try:
                user_mem = USER_MEMORY_PATH.read_text(encoding="utf-8").strip()
                if user_mem:
                    parts.append(f"\n\n## 用户偏好记忆\n以下是你之前记录的用户偏好，请参考：\n\n{user_mem}")
            except Exception:
                pass

        return "".join(parts)

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
