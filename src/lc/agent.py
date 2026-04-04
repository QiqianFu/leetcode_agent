from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from openai import OpenAI
from rich.live import Live
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from lc import db
from lc.config import (
    DATA_DIR,
    DEBUG,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    MAX_AGENT_HISTORY_MESSAGES,
)
from lc.display import console
from lc.models import CATEGORIES, Problem

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
            "description": "按用户 /config 中的配置抽题（公司、难度、标签、排序模式）。不接受参数，直接使用已有配置。如果用户用自然语言指定了想刷的题目类型，应使用 search_problem 而非此工具。",
            "parameters": {
                "type": "object",
                "properties": {},
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
]




# ─── Terminal helpers ───

def _flush_stdin():
    """Flush any pending terminal responses (e.g. CPR) from stdin."""
    import sys
    if sys.platform == "win32":
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        except Exception:
            pass
    else:
        import select
        try:
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        except Exception:
            pass


# ─── Rendering helpers ───

def _agent_renderable(content: str):
    """Render agent response with ⏺ prefix, content indented."""
    t = Table(show_header=False, show_edge=False, box=None, padding=0, expand=True)
    t.add_column(width=2, no_wrap=True)
    t.add_column()
    t.add_row(Text("⏺", style="blue"), Markdown(content))
    return t


# ─── Interactive helpers ───

def _arrow_select(choices: list[tuple[str, any]]) -> any | None:
    """Arrow-key selector using raw terminal input. Returns selected value or None."""
    import sys
    if sys.platform == "win32":
        return _arrow_select_windows(choices)
    import tty
    import termios

    _flush_stdin()

    selected = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _render():
        lines = []
        for i, (label, _) in enumerate(choices):
            if i == selected:
                lines.append(f"  \033[1;34m❯\033[0m \033[1m{label}\033[0m")
            else:
                lines.append(f"    \033[2m{label}\033[0m")
        lines.append("")
        lines.append("  \033[2m↑↓ 选择  Enter 确认  q 跳过\033[0m")
        return "\r\n".join(lines)

    def _clear():
        """Restore cursor to saved position and clear to end of screen."""
        sys.stdout.write("\033[u\033[J")

    try:
        tty.setraw(fd)
        # Flush any pending Rich/console output before raw mode rendering
        sys.stdout.flush()
        # Save cursor position, then render
        sys.stdout.write("\033[s")
        sys.stdout.write(_render())
        sys.stdout.flush()

        while True:
            ch = sys.stdin.read(1)

            if ch == "\r" or ch == "\n":  # Enter
                _clear()
                sys.stdout.flush()
                return choices[selected][1]

            if ch == "q" or ch == "\x1b":
                if ch == "\x1b":
                    next1 = sys.stdin.read(1)
                    if next1 == "[":
                        next2 = sys.stdin.read(1)
                        if next2 == "A":  # Up
                            selected = max(0, selected - 1)
                        elif next2 == "B":  # Down
                            selected = min(len(choices) - 1, selected + 1)
                        else:
                            pass
                    else:
                        # Plain Escape
                        _clear()
                        sys.stdout.flush()
                        return None
                else:
                    # 'q'
                    _clear()
                    sys.stdout.flush()
                    return None

            elif ch == "k":
                selected = max(0, selected - 1)
            elif ch == "j":
                selected = min(len(choices) - 1, selected + 1)

            # Re-render
            _clear()
            sys.stdout.write(_render())
            sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _arrow_select_windows(choices: list[tuple[str, any]]) -> any | None:
    """Windows fallback: numbered prompt instead of arrow keys."""
    import sys
    for i, (label, _) in enumerate(choices):
        print(f"  {i + 1}. {label}")
    print()
    try:
        raw = input("  输入编号 (q 跳过): ").strip()
        if raw.lower() == "q" or not raw:
            return None
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx][1]
    except (ValueError, EOFError):
        pass
    return None


# ─── File helpers ───

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text


def _detect_imports(snippet: str) -> str:
    """Detect typing and data structure imports needed by the code snippet."""
    typing_types = ["List", "Optional", "Dict", "Set", "Tuple", "Deque"]
    needed_typing = [t for t in typing_types if re.search(rf'\b{t}\b', snippet)]

    lines = []
    if needed_typing:
        lines.append(f"from typing import {', '.join(needed_typing)}")
    if "collections." in snippet or re.search(r'\b(deque|defaultdict|Counter|OrderedDict)\b', snippet):
        lines.append("import collections")
    if re.search(r'\bheapq\b', snippet):
        lines.append("import heapq")

    return "\n".join(lines)


def _workspace_root() -> Path:
    """Readonly workspace root for local lookup tools."""
    return Path.cwd().resolve()


def _problem_files_in_workspace() -> list[Path]:
    root = _workspace_root()
    return sorted(
        (p for p in root.rglob("*.py") if p.is_file()),
        key=lambda p: str(p.relative_to(root)),
    )


def _relative_workspace_path(path: Path) -> str:
    return str(path.resolve().relative_to(_workspace_root()))


def _extract_problem_id(path: Path) -> int | None:
    m = re.match(r"^(\d+)_", path.stem)
    return int(m.group(1)) if m else None


def _workspace_file_payload(path: Path) -> dict:
    payload = {"file_path": _relative_workspace_path(path)}
    problem_id = _extract_problem_id(path)
    if problem_id is not None:
        payload["problem_id"] = problem_id
    return payload


_llm_client: OpenAI | None = None

def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60)
    return _llm_client


def _classify_problem(problem: Problem) -> str:
    """Use AI to classify a problem into one of the predefined categories."""
    categories_str = ", ".join(CATEGORIES)
    prompt = (
        f"将这道 LeetCode 题分类到以下类别之一（只回复类别名，不要其他内容）：\n"
        f"{categories_str}\n\n"
        f"题目: {problem.id}. {problem.title}\n"
        f"难度: {problem.difficulty}\n"
        f"LeetCode 标签: {', '.join(problem.tags)}\n"
    )
    if problem.description:
        # Only send first 200 chars to save tokens
        prompt += f"描述: {problem.description[:200]}\n"

    try:
        resp = _get_llm_client().chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        answer = resp.choices[0].message.content.strip().lower()
        # Match against valid categories
        for cat in CATEGORIES:
            if cat in answer:
                return cat
    except Exception:
        pass
    # Fallback: old heuristic
    return _pick_category_heuristic(problem.tags)


_TAG_TO_CATEGORY = {
    # dp
    "dynamic programming": "dp", "memoization": "dp",
    # greedy
    "greedy": "greedy",
    # binary_search
    "binary search": "binary_search",
    # two_pointers
    "two pointers": "two_pointers", "sliding window": "two_pointers",
    # dfs_bfs
    "depth-first search": "dfs_bfs", "breadth-first search": "dfs_bfs",
    "backtracking": "dfs_bfs", "recursion": "dfs_bfs",
    # sorting
    "sorting": "sorting", "heap (priority queue)": "sorting",
    "merge sort": "sorting", "quickselect": "sorting", "counting sort": "sorting",
    "bucket sort": "sorting", "radix sort": "sorting",
    # stack_queue
    "stack": "stack_queue", "queue": "stack_queue",
    "monotonic stack": "stack_queue", "monotonic queue": "stack_queue",
    # tree
    "tree": "tree", "binary tree": "tree", "binary search tree": "tree",
    "trie": "tree", "segment tree": "tree", "binary indexed tree": "tree",
    # graph
    "graph": "graph", "topological sort": "graph", "union find": "graph",
    "shortest path": "graph", "minimum spanning tree": "graph",
    # design
    "design": "design",
    # math_bit
    "math": "math_bit", "bit manipulation": "math_bit",
    "number theory": "math_bit", "combinatorics": "math_bit", "geometry": "math_bit",
    # string
    "string": "string", "string matching": "string",
}


def _pick_category_heuristic(tags: list[str]) -> str:
    """Fallback: map LeetCode tags to one of the 12 categories."""
    for tag in tags:
        cat = _TAG_TO_CATEGORY.get(tag.lower())
        if cat:
            return cat
    return "dp"


def _create_solution_file(problem: Problem) -> Path:
    category = _slugify(problem.category or _pick_category_heuristic(problem.tags))
    dir_path = Path.cwd() / category
    dir_path.mkdir(exist_ok=True)

    filename = f"{problem.id}_{_slugify(problem.title)}.py"
    file_path = dir_path / filename

    if file_path.exists():
        return file_path

    lines = [
        f"# {problem.id}. {problem.title}",
        f"# https://leetcode.com/problems/{problem.title_slug}/",
        "",
    ]

    # Add problem description as comments
    if problem.description:
        lines.append('"""')
        for desc_line in problem.description.strip().splitlines():
            lines.append(desc_line)
        lines.append('"""')
        lines.append("")

    # Auto-detect needed imports from code snippet
    snippet = problem.code_snippet or ""
    imports = _detect_imports(snippet)
    if imports:
        lines.append(imports)
    lines.append("")

    if snippet:
        lines.append(snippet)
    else:
        lines.append("class Solution:")
        lines.append("    pass")

    lines.append("")
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def _memory_dir() -> Path:
    """Directory for problem memory markdown files."""
    d = Path.cwd() / ".memories"
    d.mkdir(exist_ok=True)
    return d


def _get_memory_path(problem: Problem) -> Path:
    """Get the memory file path for a problem."""
    return _memory_dir() / f"{problem.id}_{_slugify(problem.title)}.md"


def _create_memory_file(problem: Problem) -> Path:
    """Create an initial memory file for a problem."""
    memory_path = _get_memory_path(problem)
    if memory_path.exists():
        return memory_path

    lines = [
        f"# {problem.id}. {problem.title}",
        f"- 难度: {problem.difficulty}",
        f"- 标签: {', '.join(problem.tags)}",
        f"- 链接: https://leetcode.com/problems/{problem.title_slug}/",
        "",
    ]
    memory_path.write_text("\n".join(lines), encoding="utf-8")
    return memory_path


# ─── Shared actions ───

def start_problem(problem_id: int) -> tuple[Problem, Path, Path] | str:
    """Start a problem. Returns (problem, solution_path, memory_path) on success, error str on failure."""
    try:
        from lc.leetcode_api import fetch_problem
        with console.status("[bold cyan]正在获取题目...[/bold cyan]"):
            problem = fetch_problem(problem_id)
    except Exception as e:
        return f"获取题目失败: {e}"

    # AI classify
    with console.status("[bold cyan]分类中...[/bold cyan]"):
        problem.category = _classify_problem(problem)

    file_path = _create_solution_file(problem)
    memory_path = _create_memory_file(problem)

    # Register in memory index
    rel_memory = str(memory_path.relative_to(Path.cwd()))
    db.upsert_memory(problem.id, problem.title, rel_memory,
                     difficulty=problem.difficulty,
                     tags=", ".join(problem.tags))

    rel_path = file_path.relative_to(Path.cwd())
    return problem, rel_path, memory_path


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
        _flush_stdin()

        if len(self.messages) >= MAX_AGENT_HISTORY_MESSAGES:
            console.print(
                f"[yellow]当前会话已达到长度上限（{MAX_AGENT_HISTORY_MESSAGES} 条消息），"
                "请使用 /clear 开启新会话后继续。[/yellow]"
            )
            logger.warning("history limit reached: %d messages", len(self.messages))
            return

        self.messages.append({"role": "user", "content": user_input})
        logger.debug("user: %s", user_input)

        # Static system prompt → KV cache prefix stays stable across calls
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages

        # ReAct loop: think → act → observe → repeat until no more tool calls
        for step in range(16):  # safety limit
            content, tool_calls, usage = self._call_model(messages)
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

            # Execute each tool and feed results back
            for tc in tool_calls:
                console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                t0 = time.time()
                result = self._execute_tool(tc["name"], tc["arguments"])
                elapsed = time.time() - t0
                logger.debug("tool %s(%s) → %.1fs | result: %s",
                             tc["name"], tc["arguments"],
                             elapsed,
                             (result[:200] + "...") if len(result) > 200 else result)
                tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                messages.append(tool_msg)
                self.messages.append(tool_msg)

            # Loop continues — model will see tool results and decide next step

        logger.warning("ReAct loop hit 16-step limit")
        console.print("[yellow]（已达到单轮推理上限，请继续对话）[/yellow]")

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

    def _call_model(self, messages: list[dict]) -> tuple[str, list[dict], dict]:
        """Call DeepSeek with streaming. Returns (content, tool_calls, usage)."""
        messages = self._sanitize_messages(messages)
        logger.debug("calling model with %d messages", len(messages))
        if DEBUG:
            logger.debug("messages dump:\n%s", json.dumps(messages, ensure_ascii=False, indent=2))
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
                    # Include cache info if available
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
                    live.update(_agent_renderable(content))

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

    def _execute_tool(self, name: str, arguments: str) -> str:
        args = json.loads(arguments) if arguments else {}
        handlers = {
            "check_problem": lambda: self._tool_check_problem(problem_id=args.get("problem_id")),
            "read_solution": lambda: self._tool_read_solution(args.get("file_path", "")),
            "find_problem_file": lambda: self._tool_find_problem_file(args.get("problem_id")),
            "search_workspace_files": lambda: self._tool_search_workspace_files(args.get("keyword", "")),
            "list_category_problems": lambda: self._tool_list_category_problems(args.get("category", "")),
            "append_solution": lambda: self._tool_append_solution(
                args.get("file_path", ""), args.get("content", "")),
            "search_problem": lambda: self._tool_search_problem(args.get("keyword", "")),
            "pick_problem": lambda: self._tool_pick_problem(),
            "start_problem": lambda: self._tool_start_problem(args.get("problem_id")),
            "read_memory": lambda: self._tool_read_memory(args.get("problem_id")),
            "write_memory": lambda: self._tool_write_memory(
                args.get("problem_id"), args.get("content", ""), args.get("mode", "append")),
            "get_daily_plan": lambda: self._tool_get_daily_plan(),
            "get_hot_problems": lambda: self._tool_get_hot_problems(
                company=args.get("company"), tag=args.get("tag")),
        }
        handler = handlers.get(name)
        if not handler:
            return f"未知工具: {name}"
        try:
            return handler()
        except Exception as e:
            return f"错误: {e}"

    # ─── Tool implementations ───

    def _tool_check_problem(self, problem_id: int | None = None) -> str:
        """Look up problem metadata by problem ID."""
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
            # Try fetching from LeetCode API
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

    def _tool_read_solution(self, file_path: str) -> str:
        if not file_path:
            return "请传入 file_path 参数。"
        p = Path(file_path).resolve()
        if not str(p).startswith(str(_workspace_root())):
            return f"路径不在工作区内: {file_path}"
        if not p.exists():
            return f"文件不存在: {file_path}"
        return p.read_text(encoding="utf-8")

    def _tool_find_problem_file(self, problem_id: int | None = None) -> str:
        if not problem_id:
            return "请传入 problem_id。"
        matches = list(_workspace_root().glob(f"**/{problem_id}_*.py"))
        if not matches:
            return json.dumps(
                {"problem_id": problem_id, "found": False, "message": f"当前工作区内未找到第 {problem_id} 题的本地文件。"},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "problem_id": problem_id,
                "found": True,
                "file": _relative_workspace_path(matches[0]),
            },
            ensure_ascii=False,
        )

    def _tool_search_workspace_files(self, keyword: str) -> str:
        keyword = (keyword or "").strip()
        if not keyword:
            return "请传入 keyword。"

        needle = keyword.lower().replace(" ", "_")
        matches = []
        for path in _problem_files_in_workspace():
            rel = _relative_workspace_path(path)
            haystacks = {
                path.stem.lower(),
                rel.lower(),
                path.parent.name.lower(),
            }
            if any(needle in h or keyword.lower() in h for h in haystacks):
                matches.append(_workspace_file_payload(path))
            if len(matches) >= 10:
                break

        return json.dumps(
            {
                "keyword": keyword,
                "matches": matches,
                "count": len(matches),
            },
            ensure_ascii=False,
        )

    def _tool_list_category_problems(self, category: str) -> str:
        category = (category or "").strip()
        if not category:
            return "请传入 category。"

        root = _workspace_root()
        raw = category.lower()
        normalized = _slugify(category)
        matched_dirs = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name == raw or name == normalized or raw in name or normalized in name:
                matched_dirs.append(child)

        if not matched_dirs:
            return json.dumps(
                {"category": category, "matches": [], "count": 0, "message": "当前工作区内未找到匹配的分类目录。"},
                ensure_ascii=False,
            )

        directory = sorted(matched_dirs, key=lambda p: p.name)[0]
        files = sorted(
            (p for p in directory.glob("*.py") if p.is_file()),
            key=lambda p: p.name,
        )
        matches = [_workspace_file_payload(path) for path in files[:50]]
        return json.dumps(
            {
                "category": category,
                "directory": _relative_workspace_path(directory),
                "matches": matches,
                "count": len(matches),
            },
            ensure_ascii=False,
        )

    def _tool_append_solution(self, file_path: str, content: str) -> str:
        if not file_path:
            return "请传入 file_path 参数。"
        p = Path(file_path).resolve()
        if not str(p).startswith(str(_workspace_root())):
            return f"路径不在工作区内: {file_path}"
        if not p.exists():
            return f"文件不存在: {file_path}"
        with p.open("a", encoding="utf-8") as f:
            f.write("\n\n# ─── 参考解法 ───\n\n")
            f.write(content)
            f.write("\n")
        console.print(f"[dim]参考解法已追加到 {file_path}[/dim]")
        return f"已追加到 {file_path}"


    def _tool_search_problem(self, keyword: str) -> str:
        from lc.leetcode_api import search_problems
        results = search_problems(keyword, limit=5)
        if not results:
            return f"没有找到与「{keyword}」相关的题目。"

        choices = [
            (f"#{p.id} {p.title} ({p.difficulty})", p)
            for p in results
        ]
        selected = _arrow_select(choices)
        if not selected:
            return "用户未选择题目。"
        return json.dumps({
            "selected_id": selected.id,
            "title": selected.title,
            "difficulty": selected.difficulty,
        }, ensure_ascii=False)

    def _tool_pick_problem(self) -> str:
        """Recommend problems based on user's /config settings."""
        from lc.planner import generate_daily_plan
        from lc.cli import get_config
        plan = generate_daily_plan(
            company=get_config("company"),
            difficulty=get_config("difficulty"),
            tag=get_config("tag"),
            randomize=get_config("mode") == "random",
        )
        problems = plan.new_problems

        if not problems:
            return "没有找到合适的题目。"

        choices = [
            (f"#{p.id} {p.title} ({p.difficulty})", p)
            for p in problems[:8]
        ]
        selected = _arrow_select(choices)
        if not selected:
            return "用户未选择题目。"
        return json.dumps({
            "selected_id": selected.id,
            "title": selected.title,
            "difficulty": selected.difficulty,
        }, ensure_ascii=False)

    def _tool_start_problem(self, problem_id: int) -> str:
        result = start_problem(problem_id)
        if isinstance(result, str):
            return result  # error message
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

    def _tool_read_memory(self, problem_id: int | None = None) -> str:
        if not problem_id:
            return "请传入 problem_id。"
        memory = db.get_memory(problem_id)
        if not memory:
            return f"第 {problem_id} 题没有记忆文件。"
        memory_path = Path(memory["memory_file"])
        if not memory_path.exists():
            return f"记忆文件不存在: {memory['memory_file']}"
        return memory_path.read_text(encoding="utf-8")

    def _tool_write_memory(self, problem_id: int | None = None,
                            content: str = "", mode: str = "append") -> str:
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
        return f"已写入记忆文件。"

    def _tool_get_daily_plan(self) -> str:
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

    def _tool_get_hot_problems(self, company: str | None = None, tag: str | None = None) -> str:
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
