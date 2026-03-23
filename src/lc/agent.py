from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from lc import db, state
from lc.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from lc.models import CATEGORIES, Problem

_THEME = Theme({
    "markdown.code": "bold cyan",
    "markdown.code_block": "cyan",
})
console = Console(theme=_THEME)

SYSTEM_PROMPT = """\
你是一个 LeetCode 刷题助手，在终端中和用户自由对话。

你的职责：
- 帮用户选题、开始做题
- 阅读用户写的代码，给出提示（先引导思考，不要直接给答案）
- 用户明确要求讲解时，才给出完整解题思路
- 帮用户提交结果、管理复习计划

重要原则：
- 用户的意图明确时，直接执行，不要反复确认。比如用户说"放弃"就直接放弃，说"提交"就直接问评分然后提交。
- 不要做多余的 double check，用户既然说了就是确定了。

使用工具的时机：
- 用户要提示 → 先 read_solution 读代码，然后调 count_hint 记录，再给提示
- 用户要讲解 → 先 read_solution 读代码，然后调 count_teach 记录，再给讲解
- 用户想看代码 → read_solution
- 用户想做某道题（给了题号） → start_problem
- 用户提到了题目名称但没给题号（如"走楼梯那题"、"两数之和"、"LRU缓存"） → 先用 search_problem 搜索（关键词必须用英文，你自行翻译），搜到结果后让用户选择
- 用户想刷题但没指定题号（如"开始"、"来一道"、"刷题"等） → 直接调 pick_problem，不要反问
- 用户想刷特定类型的题（如"来一道堆的题"、"给我一道动态规划"） → 如果用户没有指定难度，必须先反问"想要什么难度？Easy / Medium / Hard / 不限"，拿到回答后再调 pick_problem 传 tag（和 difficulty）
- 用户说做完了/结束/想提交/完成了 → 直接调 finish_problem 触发提交流程
- 用户要放弃当前题 → 直接 abandon_problem
- 查看计划/统计/复习/高频 → 告诉用户用斜杠命令：/today, /status, /review, /hot

自评分标准：1=轻松搞定 2=稍有思考 3=想了一阵 4=很吃力 5=没做出来

用中文回答。简洁直接。"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_solution",
            "description": "读取用户当前的解题代码文件",
            "parameters": {"type": "object", "properties": {}},
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
                    "content": {"type": "string", "description": "参考解法代码"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pick_problem",
            "description": "抽题并开始。无参数时按用户配置抽题；传 tag 时无视配置，按频率抽该标签的题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "指定标签（如 堆、动态规划、链表），按频率抽该标签的题",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["Easy", "Medium", "Hard"],
                        "description": "指定难度，用户不需要时不传",
                    },
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
            "name": "finish_problem",
            "description": "结束当前题目，触发评分提交流程。用户说做完了、结束、完成了、想提交时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abandon_problem",
            "description": "放弃当前题目",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_hint",
            "description": "记录一次提示使用（给提示前必须调用）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_teach",
            "description": "记录一次讲解使用（给讲解前必须调用）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# Tools that don't need an AI follow-up response
_SELF_CONTAINED_TOOLS = {
    "abandon_problem", "pick_problem", "finish_problem",
}


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
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=30)
        resp = client.chat.completions.create(
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


_DATA_STRUCTURE_TAGS = {
    "array", "string", "hash table", "linked list", "stack", "queue",
    "tree", "binary tree", "binary search tree", "graph", "matrix",
    "doubly-linked list", "heap (priority queue)",
}


def _pick_category_heuristic(tags: list[str]) -> str:
    """Fallback: pick an algorithm-type tag over data-structure tags for folder name."""
    for tag in tags:
        if tag.lower() not in _DATA_STRUCTURE_TAGS:
            return tag
    return tags[0] if tags else "other"


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


# ─── Shared actions ───

def submit_current_problem(rating: int, notes: str = None) -> str:
    """Submit current problem with rating. Used by both Agent and /submit command."""
    current = state.get_current()
    if not current:
        return "当前没有在做题。"
    if not rating or rating < 1 or rating > 5:
        return "评分需要在 1-5 之间。"

    pid, aid = current
    problem = db.get_problem(pid)
    attempt = db.get_attempt(aid)
    if not problem or not attempt:
        return "数据异常。"

    db.finish_attempt(aid, rating, notes)
    attempt = db.get_attempt(aid)

    from lc.scheduler import handle_review_submit, schedule_review

    active_review = db.get_active_review_for_problem(pid)
    reviews_scheduled = 0

    if active_review:
        # One review session should clear all overdue review entries for the same problem.
        db.complete_due_reviews(pid)
        new_reviews, should_cancel = handle_review_submit(active_review, rating)
        if should_cancel:
            db.cancel_future_reviews(pid)
        if new_reviews:
            db.insert_reviews(new_reviews)
            reviews_scheduled = len(new_reviews)
    else:
        reviews = schedule_review(pid, rating, attempt.hints_used, attempt.teach_used)
        if reviews:
            db.insert_reviews(reviews)
            reviews_scheduled = len(reviews)

    db.update_tag_stats(pid)

    started = datetime.fromisoformat(attempt.started_at)
    elapsed = datetime.utcnow() - started
    minutes = int(elapsed.total_seconds() // 60)
    time_str = f"{minutes} 分钟" if minutes > 0 else "< 1 分钟"

    # Save undo info before clearing state
    fp = state.get_file_path() or ""
    db.set_session("last_submit", json.dumps({
        "problem_id": pid,
        "attempt_id": aid,
        "rating": rating,
        "file_path": fp,
    }))

    state.clear_current()

    from lc.display import show_submit_summary
    show_submit_summary(problem, rating, reviews_scheduled, time_str)
    return "已提交。"


def start_problem(problem_id: int) -> tuple[Problem, Path] | str:
    """Start a problem. Returns (problem, rel_path) on success, error str on failure."""
    state.clear_current()

    problem = db.get_problem(problem_id)
    if problem is None or problem.description is None:
        try:
            from lc.leetcode_api import fetch_problem
            with console.status("[bold cyan]正在获取题目...[/bold cyan]"):
                problem = fetch_problem(problem_id)
                db.upsert_problem(problem)
        except Exception as e:
            return f"获取题目失败: {e}"

    # AI classify if not already categorized
    if not problem.category:
        with console.status("[bold cyan]分类中...[/bold cyan]"):
            problem.category = _classify_problem(problem)
            db.set_problem_category(problem.id, problem.category)

    file_path = _create_solution_file(problem)
    attempt_id = db.create_attempt(problem_id)
    state.set_current(problem_id, attempt_id, file_path=str(file_path))

    url = f"https://leetcode.com/problems/{problem.title_slug}/"
    rel_path = file_path.relative_to(Path.cwd())
    console.print(f"[green]已开始: {problem.id}. {problem.title} ({problem.difficulty})[/green]")
    console.print(f"[dim]🔗 {url}[/dim]")
    console.print(f"[dim]📄 {rel_path}[/dim]")
    console.print(f"[dim]输入「提示」「讲解」获取帮助，/submit 提交，「放弃」跳过[/dim]")

    return problem, rel_path


# ─── Agent ───

class Agent:
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            console.print("[red]错误: 请在 .env 文件中设置 DEEPSEEK_API_KEY[/red]")
            raise SystemExit(1)
        self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60)
        self.messages: list[dict] = []
        self._pending_clear = False

    def _build_system_prompt(self) -> str:
        parts = [SYSTEM_PROMPT]

        current = state.get_current()
        if current:
            pid, aid = current
            problem = db.get_problem(pid)
            attempt = db.get_attempt(aid)
            if problem:
                parts.append(f"\n[当前题目] {problem.id}. {problem.title} ({problem.difficulty})")
                from lc.models import CATEGORY_LABELS
                cat_label = CATEGORY_LABELS.get(problem.category, "") if problem.category else ""
                if cat_label:
                    parts.append(f"题型: {cat_label}")
                parts.append(f"标签: {', '.join(problem.tags)}")
                fp = state.get_file_path()
                if fp:
                    parts.append(f"文件: {fp}")
                if attempt:
                    parts.append(f"已用提示: {attempt.hints_used}次, 讲解: {attempt.teach_used}次")
                if problem.description:
                    parts.append(f"\n题目描述:\n{problem.description}")
        else:
            parts.append("\n当前没有在做题。用户说开始/刷题等，直接调 pick_problem。")

        return "\n".join(parts)

    def chat(self, user_input: str):
        """Process user message through the agent loop."""
        _flush_stdin()
        if self._pending_clear:
            self.messages.clear()
            self._pending_clear = False
        self.messages.append({"role": "user", "content": user_input})

        # Keep history manageable — find safe truncation point
        if len(self.messages) > 40:
            # Start from position -30 and scan forward to find a safe cut point
            # (not in the middle of a tool_call/tool_result pair)
            cut = len(self.messages) - 30
            while cut < len(self.messages):
                msg = self.messages[cut]
                if msg["role"] in ("tool",):
                    # Don't start with an orphan tool result — move forward
                    cut += 1
                elif msg["role"] == "assistant" and msg.get("tool_calls"):
                    # Don't start with an assistant tool_call without its results
                    cut += 1
                else:
                    break
            self.messages = self.messages[cut:]

        messages = [{"role": "system", "content": self._build_system_prompt()}] + self.messages

        for _ in range(8):  # max tool-call iterations
            content, tool_calls = self._call_model(messages)

            if not tool_calls:
                self.messages.append({"role": "assistant", "content": content})
                return

            # Add assistant message with tool calls
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

            # Execute each tool
            all_self_contained = True
            for tc in tool_calls:
                console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                result = self._execute_tool(tc["name"], tc["arguments"])
                tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                messages.append(tool_msg)
                self.messages.append(tool_msg)
                if tc["name"] not in _SELF_CONTAINED_TOOLS:
                    all_self_contained = False

            # Self-contained tools don't need AI follow-up
            if all_self_contained:
                return

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

    def _call_model(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Call DeepSeek with streaming. Returns (content, tool_calls)."""
        messages = self._sanitize_messages(messages)
        stream = self.client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
            stream=True,
            temperature=0.3,
            max_tokens=4096,
        )

        content = ""
        tool_calls_map: dict[int, dict] = {}
        live = None

        try:
            for chunk in stream:
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

        tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map)] if tool_calls_map else []
        return content, tool_calls

    def _execute_tool(self, name: str, arguments: str) -> str:
        args = json.loads(arguments) if arguments else {}
        handlers = {
            "read_solution": lambda: self._tool_read_solution(),
            "append_solution": lambda: self._tool_append_solution(args.get("content", "")),
            "search_problem": lambda: self._tool_search_problem(args.get("keyword", "")),
            "pick_problem": lambda: self._tool_pick_problem(tag=args.get("tag"), difficulty=args.get("difficulty")),
            "start_problem": lambda: self._tool_start_problem(args.get("problem_id")),
            "finish_problem": lambda: self._tool_finish_problem(),
            "abandon_problem": lambda: self._tool_abandon(),
            "count_hint": lambda: self._tool_count_hint(),
            "count_teach": lambda: self._tool_count_teach(),
        }
        handler = handlers.get(name)
        if not handler:
            return f"未知工具: {name}"
        try:
            return handler()
        except Exception as e:
            return f"错误: {e}"

    # ─── Tool implementations ───

    def _tool_read_solution(self) -> str:
        fp = state.get_file_path()
        if not fp:
            return "当前没有解题文件。请先开始一道题。"
        p = Path(fp)
        if not p.exists():
            return f"文件不存在: {fp}"
        return p.read_text(encoding="utf-8")

    def _tool_append_solution(self, content: str) -> str:
        fp = state.get_file_path()
        if not fp:
            return "当前没有解题文件。"
        p = Path(fp)
        if not p.exists():
            return f"文件不存在: {fp}"
        with p.open("a", encoding="utf-8") as f:
            f.write("\n\n# ─── 参考解法 ───\n\n")
            f.write(content)
            f.write("\n")
        console.print(f"[dim]参考解法已追加到 {fp}[/dim]")
        return f"已追加到 {fp}"


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
        if selected:
            result = start_problem(selected.id)
            if not isinstance(result, str):
                self._pending_clear = True
                return f"已开始: {selected.id}. {selected.title}"
            return result
        return "未选题。"

    def _tool_pick_problem(self, tag: str | None = None, difficulty: str | None = None) -> str:
        """Auto-pick a problem. If tag is given, pick by tag ignoring config."""
        if tag:
            return self._tool_pick_by_tag(tag, difficulty)
        from lc.cli import handle_today
        handle_today()
        current = state.get_current()
        if current:
            self._pending_clear = True
            pid, _ = current
            problem = db.get_problem(pid)
            if problem:
                return f"已开始: {problem.id}. {problem.title}"
        return "未选题。"

    def _tool_pick_by_tag(self, tag: str, difficulty: str | None = None) -> str:
        """Pick a problem by tag, ignoring config, ordered by frequency."""
        from lc.planner import _pick_from_codetop
        problems = _pick_from_codetop(tag=tag, difficulty=difficulty, limit=5, randomize=False)
        if not problems:
            return f"没有找到标签为「{tag}」的未做题目。"

        choices = [
            (f"#{p.id} {p.title} ({p.difficulty})", p)
            for p in problems
        ]
        selected = _arrow_select(choices)
        if selected:
            start_problem(selected.id)
            current = state.get_current()
            if current:
                self._pending_clear = True
                problem = db.get_problem(selected.id)
                if problem:
                    return f"已开始: {problem.id}. {problem.title}"
        return "未选题。"

    def _tool_start_problem(self, problem_id: int) -> str:
        result = start_problem(problem_id)
        if isinstance(result, str):
            return result  # error message
        self._pending_clear = True
        problem, rel_path = result
        return json.dumps(
            {
                "status": "started",
                "problem": f"{problem.id}. {problem.title}",
                "difficulty": problem.difficulty,
                "tags": problem.tags,
                "file": str(rel_path),
                "description": problem.description or "",
            },
            ensure_ascii=False,
        )

    def _tool_finish_problem(self) -> str:
        from lc.cli import handle_submit
        current = state.get_current()
        if not current:
            return "当前没有在做题。"
        handle_submit()
        return "已完成提交流程。"

    def _tool_abandon(self) -> str:
        current = state.get_current()
        if not current:
            return "当前没有在做题。"
        pid, _ = current
        state.clear_current()
        console.print(f"[dim]已放弃第 {pid} 题。输入 /today 选择下一道题。[/dim]")
        return f"已放弃第 {pid} 题。"

    def _tool_count_hint(self) -> str:
        current = state.get_current()
        if not current:
            return "当前没有在做题。"
        _, aid = current
        db.increment_hints(aid)
        return "已记录提示。"

    def _tool_count_teach(self) -> str:
        current = state.get_current()
        if not current:
            return "当前没有在做题。"
        _, aid = current
        db.increment_teach(aid)
        return "已记录讲解。"
