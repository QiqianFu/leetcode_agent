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
from lc.models import Problem

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
- 用户想看代码/要提示/要讲解 → 先 read_solution 读代码
- 用户想做某道题 → start_problem
- 用户说做完了/想提交 → 询问自评分(1-5)后 submit_result
- 用户要放弃当前题 → 直接 abandon_problem
- 查看计划/统计/复习/高频 → 对应的 get_ 工具

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
            "name": "write_solution",
            "description": "写入用户的解题文件（覆盖全部内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "完整代码内容"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_problem",
            "description": "开始做一道 LeetCode 题，获取题目并创建解题文件",
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
            "name": "submit_result",
            "description": "提交当前题目，记录自评分，安排复习",
            "parameters": {
                "type": "object",
                "properties": {
                    "rating": {"type": "integer", "description": "自评 1-5"},
                    "notes": {"type": "string", "description": "备注"},
                },
                "required": ["rating"],
            },
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
            "name": "get_daily_plan",
            "description": "获取今日刷题计划（复习 + 新题）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "获取刷题统计数据",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_reviews",
            "description": "获取待复习题目列表",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_problems",
            "description": "获取目标公司的高频面试题",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ─── Terminal helpers ───

def _flush_stdin():
    """Flush any pending terminal responses (e.g. CPR) from stdin."""
    import sys
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
        """Move cursor up and clear all selector lines."""
        # Move to start of first line, then clear to end of screen
        sys.stdout.write(f"\r\033[{total_lines - 1}A\033[J")

    total_lines = len(choices) + 2  # choices + blank + hint

    try:
        tty.setraw(fd)
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


# ─── File helpers ───

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text


_DATA_STRUCTURE_TAGS = {
    "array", "string", "hash table", "linked list", "stack", "queue",
    "tree", "binary tree", "binary search tree", "graph", "matrix",
    "doubly-linked list", "heap (priority queue)",
}


def _pick_category(tags: list[str]) -> str:
    """Pick an algorithm-type tag over data-structure tags for folder name."""
    for tag in tags:
        if tag.lower() not in _DATA_STRUCTURE_TAGS:
            return tag
    return tags[0] if tags else "other"


def _create_solution_file(problem: Problem) -> Path:
    category = _slugify(_pick_category(problem.tags))
    dir_path = Path.cwd() / category
    dir_path.mkdir(exist_ok=True)

    filename = f"{problem.id}_{_slugify(problem.title)}.py"
    file_path = dir_path / filename

    if file_path.exists():
        return file_path

    lines = [
        f"# {problem.id}. {problem.title}",
        f"# 难度: {problem.difficulty}",
    ]
    if problem.tags:
        lines.append(f'# 标签: {", ".join(problem.tags)}')
    lines.append(f"# https://leetcode.com/problems/{problem.title_slug}/")
    lines.append("#")

    if problem.description:
        lines.append("# --- 题目描述 ---")
        for desc_line in problem.description.splitlines():
            lines.append(f"# {desc_line}")
        lines.append("#")

    lines.append("")
    lines.append("")

    if problem.code_snippet:
        lines.append(problem.code_snippet)
    else:
        lines.append("class Solution:")
        lines.append("    pass")

    lines.append("")
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


# ─── Agent ───

class Agent:
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            console.print("[red]错误: 请在 .env 文件中设置 DEEPSEEK_API_KEY[/red]")
            raise SystemExit(1)
        self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self.messages: list[dict] = []

    def _build_system_prompt(self) -> str:
        parts = [SYSTEM_PROMPT]

        current = state.get_current()
        if current:
            pid, aid = current
            problem = db.get_problem(pid)
            attempt = db.get_attempt(aid)
            if problem:
                parts.append(f"\n[当前题目] {problem.id}. {problem.title} ({problem.difficulty})")
                parts.append(f"标签: {', '.join(problem.tags)}")
                fp = state.get_file_path()
                if fp:
                    parts.append(f"文件: {fp}")
                if attempt:
                    parts.append(f"已用提示: {attempt.hints_used}次, 讲解: {attempt.teach_used}次")
                if problem.description:
                    parts.append(f"\n题目描述:\n{problem.description}")
        else:
            parts.append("\n当前没有在做题。")

        return "\n".join(parts)

    def chat(self, user_input: str):
        """Process user message through the agent loop."""
        _flush_stdin()
        self.messages.append({"role": "user", "content": user_input})

        # Keep history manageable
        if len(self.messages) > 40:
            self.messages = self.messages[-30:]

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
            for tc in tool_calls:
                console.print(f"[dim]  ⚙ {tc['name']}[/dim]")
                result = self._execute_tool(tc["name"], tc["arguments"])
                tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                messages.append(tool_msg)
                self.messages.append(tool_msg)

    def _call_model(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Call DeepSeek with streaming. Returns (content, tool_calls)."""
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
            "write_solution": lambda: self._tool_write_solution(args.get("content", "")),
            "start_problem": lambda: self._tool_start_problem(args.get("problem_id")),
            "submit_result": lambda: self._tool_submit_result(args.get("rating"), args.get("notes")),
            "abandon_problem": lambda: self._tool_abandon(),
            "get_daily_plan": lambda: self._tool_get_daily_plan(),
            "get_status": lambda: self._tool_get_status(),
            "get_pending_reviews": lambda: self._tool_get_reviews(),
            "get_hot_problems": lambda: self._tool_get_hot_problems(),
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

    def _tool_write_solution(self, content: str) -> str:
        fp = state.get_file_path()
        if not fp:
            return "当前没有解题文件。"
        Path(fp).write_text(content, encoding="utf-8")
        return f"已写入 {fp}"

    def _tool_start_problem(self, problem_id: int) -> str:
        current = state.get_current()
        if current:
            pid, _ = current
            return f"你正在做第 {pid} 题，请先提交或放弃。"

        problem = db.get_problem(problem_id)
        if problem is None or problem.description is None:
            try:
                from lc.leetcode_api import fetch_problem
                problem = fetch_problem(problem_id)
                db.upsert_problem(problem)
            except Exception as e:
                return f"获取题目失败: {e}"

        file_path = _create_solution_file(problem)
        attempt_id = db.create_attempt(problem_id)
        state.set_current(problem_id, attempt_id, file_path=str(file_path))

        rel_path = file_path.relative_to(Path.cwd())
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

    def _tool_submit_result(self, rating: int, notes: str = None) -> str:
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
            db.complete_review(active_review.id)
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

        state.clear_current()

        return json.dumps(
            {
                "status": "submitted",
                "problem": f"{problem.id}. {problem.title}",
                "rating": rating,
                "time": time_str,
                "reviews_scheduled": reviews_scheduled,
                "hints_used": attempt.hints_used,
                "teach_used": attempt.teach_used,
            },
            ensure_ascii=False,
        )

    def _tool_abandon(self) -> str:
        current = state.get_current()
        if not current:
            return "当前没有在做题。"
        pid, _ = current
        state.clear_current()
        console.print(f"[dim]已放弃第 {pid} 题。[/dim]")

        # Offer next problem selection
        from lc.planner import generate_daily_plan
        company = db.get_session("cfg_company") or None
        difficulty = db.get_session("cfg_difficulty") or None
        plan = generate_daily_plan(company=company, difficulty=difficulty)

        choices: list[tuple[str, Problem]] = []
        for _, problem in plan.review_problems:
            choices.append((f"[复习] #{problem.id} {problem.title} ({problem.difficulty})", problem))
        for problem in plan.new_problems:
            choices.append((f"[新题] #{problem.id} {problem.title} ({problem.difficulty})", problem))

        if choices:
            console.print("[dim]选择下一道题：[/dim]")
            selected = _arrow_select(choices)
            if selected:
                return self._tool_start_problem(selected.id)
        return f"已放弃第 {pid} 题。"

    def _tool_get_daily_plan(self) -> str:
        from lc.planner import generate_daily_plan
        from lc.display import show_daily_plan

        company = db.get_session("cfg_company") or None
        difficulty = db.get_session("cfg_difficulty") or None
        plan = generate_daily_plan(company=company, difficulty=difficulty)

        # Show plan with Rich tables
        show_daily_plan(plan)

        # Collect all problems for selection
        choices: list[tuple[str, Problem]] = []
        for _, problem in plan.review_problems:
            label = f"[复习] #{problem.id} {problem.title} ({problem.difficulty})"
            choices.append((label, problem))
        for problem in plan.new_problems:
            label = f"[新题] #{problem.id} {problem.title} ({problem.difficulty})"
            choices.append((label, problem))

        if not choices:
            return "今天没有需要做的题目。"

        selected = _arrow_select(choices)
        if selected:
            return self._tool_start_problem(selected.id)
        return "已显示今日计划。"

    def _tool_get_status(self) -> str:
        stats = db.get_attempt_stats()
        weak_tags = db.get_weakest_tags(limit=5)
        result = {
            "total_solved": stats["total_solved"],
            "by_difficulty": stats["by_difficulty"],
            "avg_rating": round(stats["avg_rating"], 1),
            "pending_reviews": stats["pending_reviews"],
            "weak_tags": [
                {"tag": t.tag, "avg_rating": round(t.avg_rating, 1), "attempts": t.total_attempts}
                for t in weak_tags
            ],
        }
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_reviews(self) -> str:
        pending = db.get_pending_reviews()
        result = []
        for r in pending:
            problem = db.get_problem(r.problem_id)
            if problem:
                result.append(
                    {
                        "id": problem.id,
                        "title": problem.title,
                        "difficulty": problem.difficulty,
                        "interval_days": r.interval_days,
                        "due_date": r.due_date,
                    }
                )
        if not result:
            return "没有待复习的题目。"
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_hot_problems(self) -> str:
        from lc.codetop_api import fetch_hot_problems

        company = db.get_session("cfg_company") or None
        problems, total = fetch_hot_problems(company=company, page=1)
        if not problems:
            return "暂无数据。请先用 /config 设置公司。"
        solved_ids = db.get_solved_problem_ids()
        result = []
        for p in problems[:15]:
            result.append(
                {
                    "id": p.leetcode_id,
                    "title": p.title,
                    "difficulty": p.difficulty,
                    "frequency": p.frequency,
                    "solved": p.leetcode_id in solved_ids,
                }
            )
        return json.dumps(
            {"company": company or "全部", "total": total, "problems": result},
            ensure_ascii=False,
        )
