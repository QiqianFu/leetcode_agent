from __future__ import annotations

from rich.prompt import Prompt
from rich.panel import Panel

from lc import db, state
from lc.display import console, show_companies, show_tags

DIFFICULTY_CHOICES = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


# ─── Config helpers ───

def get_config(key: str) -> str | None:
    return db.get_session(f"cfg_{key}")


def set_config(key: str, value: str) -> None:
    db.set_session(f"cfg_{key}", value)


def handle_config() -> None:
    """Interactive config setup."""
    console.print()
    console.print("[bold]设置刷题偏好[/bold]\n")

    from lc.codetop_api import fetch_companies
    console.print("[dim]正在获取公司列表...[/dim]")
    companies = fetch_companies()
    if companies:
        show_companies(companies)

    current_company = get_config("company") or ""
    company = Prompt.ask(
        "目标公司（直接回车跳过）",
        default=current_company,
        show_default=bool(current_company),
    )
    if company.strip():
        valid_names = [c["name"] for c in companies]
        if company in valid_names:
            set_config("company", company)
            console.print(f"[green]公司已设置为: {company}[/green]")
        else:
            matches = [n for n in valid_names if company.lower() in n.lower()]
            if matches:
                set_config("company", matches[0])
                console.print(f"[green]公司已设置为: {matches[0]}[/green]")
            else:
                console.print(f"[red]未找到「{company}」，公司设置未更改。[/red]")
    else:
        console.print("[dim]公司: 跳过[/dim]")

    console.print()
    diff = Prompt.ask(
        "难度偏好",
        choices=["easy", "medium", "hard", "all"],
        default=get_config("difficulty") or "all",
    )
    if diff == "all":
        set_config("difficulty", "")
        console.print("[green]难度: 不限[/green]")
    else:
        set_config("difficulty", DIFFICULTY_CHOICES[diff])
        console.print(f"[green]难度已设置为: {DIFFICULTY_CHOICES[diff]}[/green]")

    # Mode selection
    console.print()
    current_mode = get_config("mode") or "default"
    mode = Prompt.ask(
        "刷题模式",
        choices=["default", "random", "tag"],
        default=current_mode,
    )
    set_config("mode", mode)

    if mode == "tag":
        from lc.codetop_api import fetch_tags
        console.print("[dim]正在获取标签列表...[/dim]")
        tags = fetch_tags()
        if tags:
            show_tags(tags)
        current_tag = get_config("tag") or ""
        tag_input = Prompt.ask(
            "目标标签（输入标签名称）",
            default=current_tag,
            show_default=bool(current_tag),
        )
        if tag_input.strip() and tags:
            tag_names = [t["name"] for t in tags]
            if tag_input in tag_names:
                set_config("tag", tag_input)
                console.print(f"[green]标签已设置为: {tag_input}[/green]")
            else:
                matches = [n for n in tag_names if tag_input.lower() in n.lower()]
                if matches:
                    set_config("tag", matches[0])
                    console.print(f"[green]标签已设置为: {matches[0]}[/green]")
                else:
                    console.print(f"[red]未找到「{tag_input}」，标签设置未更改。[/red]")
        else:
            console.print("[dim]标签: 跳过[/dim]")

    mode_labels = {"default": "按频率", "random": "随机", "tag": "按标签"}
    mode_display = mode_labels.get(mode, mode)
    if mode == "tag":
        mode_display += f" ({get_config('tag') or '未设置'})"
    console.print(f"[green]模式已设置为: {mode_display}[/green]")

    console.print()
    company_display = get_config("company") or "未设置"
    diff_display = get_config("difficulty") or "不限"
    console.print(Panel(
        f"公司: [cyan]{company_display}[/cyan]\n"
        f"难度: [cyan]{diff_display}[/cyan]\n"
        f"模式: [cyan]{mode_display}[/cyan]",
        title="当前设置",
        border_style="blue",
    ))
    console.print("[green]设置完成！[/green]\n")


# ─── Prompt session ───

SLASH_COMMANDS = [
    ("/today",  "今日计划（复习 + 新题）"),
    ("/submit", "提交当前题目"),
    ("/info",   "当前做题状态"),
    ("/similar", "相似题目"),
    ("/status", "刷题统计"),
    ("/review", "待复习列表"),
    ("/hot",    "高频面试题"),
    ("/undo",   "撤回上次提交"),
    ("/config", "设置公司、难度、刷题模式"),
    ("/help",   "显示帮助"),
    ("/quit",   "退出"),
]

HELP_TEXT = """
[bold]自然语言对话:[/bold]
  "帮我做第 146 题"  "给个提示"  "讲解一下"  "放弃"

[bold]做题中:[/bold]
  [cyan]/submit[/cyan]   提交当前题目
  [cyan]/info[/cyan]     查看当前题目、用时、提示次数
  [cyan]/similar[/cyan]  查找相似题目

[bold]快捷指令:[/bold]
  [cyan]/today[/cyan]   今日计划（复习 + 新题）
  [cyan]/status[/cyan]  刷题统计
  [cyan]/review[/cyan]  待复习列表
  [cyan]/hot[/cyan]     高频面试题
  [cyan]/undo[/cyan]    撤回上次提交
  [cyan]/config[/cyan]  设置公司、难度、刷题模式
  [cyan]/help[/cyan]    显示帮助
  [cyan]/quit[/cyan]    退出
""".strip()


def _build_prompt_session():
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style

    # Pad command names to equal width so descriptions align
    max_cmd_len = max(len(cmd) for cmd, _ in SLASH_COMMANDS)

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith("/"):
                for cmd, desc in SLASH_COMMANDS:
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=f"{cmd:<{max_cmd_len}}  {desc}",
                        )

    kb = KeyBindings()

    @kb.add("backspace")
    def _backspace(event):
        buf = event.current_buffer
        buf.delete_before_cursor()
        if buf.text:
            buf.start_completion(select_first=False)

    @kb.add("delete")
    def _delete(event):
        buf = event.current_buffer
        buf.delete()
        if buf.text:
            buf.start_completion(select_first=False)

    @kb.add("right")
    def _right_accept(event):
        """Right arrow accepts the current completion if menu is open."""
        buf = event.current_buffer
        if buf.complete_state:
            buf.apply_completion(buf.complete_state.current_completion)
        else:
            buf.cursor_right()

    style = Style.from_dict({
        "prompt": "bold ansiblue",
        "completion-menu": "bg:default noinherit",
        "completion-menu.completion": "bg:default ansiblue noinherit",
        "completion-menu.completion.current": "bg:default bold ansiblue noinherit",
        "scrollbar.background": "noinherit",
        "scrollbar.button": "noinherit",
        "bottom-toolbar": "noreverse noinherit",
        "bottom-toolbar.text": "#000000 noinherit",
    })

    # Remove 1-space left padding from completion menu items
    import prompt_toolkit.layout.menus as _ptk_menus
    from prompt_toolkit.formatted_text import to_formatted_text
    from prompt_toolkit.formatted_text.base import StyleAndTextTuples
    from typing import cast

    _orig_get_fragments = _ptk_menus._get_menu_item_fragments

    def _patched_get_fragments(completion, is_current_completion, width, space_after=False):
        if is_current_completion:
            style_str = f"class:completion-menu.completion.current {completion.style} {completion.selected_style}"
        else:
            style_str = "class:completion-menu.completion " + completion.style
        text, tw = _ptk_menus._trim_formatted_text(
            completion.display, width if not space_after else width - 1
        )
        padding = " " * max(0, width - tw)
        return to_formatted_text(
            cast(StyleAndTextTuples, []) + text + [("", padding)],
            style=style_str,
        )

    _ptk_menus._get_menu_item_fragments = _patched_get_fragments

    session = PromptSession(
        completer=SlashCompleter(),
        complete_while_typing=True,
        key_bindings=kb,
        style=style,
        reserve_space_for_menu=0,
    )

    # Shift completion menu to start at the beginning of typed text (not cursor)
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.containers import (
        Window,
        HSplit,
        Float,
        FloatContainer,
        ConditionalContainer,
    )
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.filters import Condition
    import shutil

    input_window = None
    for window in session.layout.find_all_windows():
        if isinstance(window.content, BufferControl) and window.content.buffer == session.default_buffer:
            input_window = window
            window.dont_extend_height = Condition(lambda: True)

            def _menu_pos():
                buf = session.default_buffer
                if buf.complete_state:
                    cs = buf.complete_state.current_completion or buf.complete_state.completions[0]
                    orig = buf.complete_state.original_document.cursor_position
                    return max(0, orig + cs.start_position)
                return None
            window.content.menu_position = _menu_pos
            break

    # Insert separator + conditional reserve space inside FloatContainer's HSplit
    def _sep_text():
        w = shutil.get_terminal_size().columns
        return [("class:bottom-toolbar.text", "─" * w)]

    def _should_reserve_menu_space() -> bool:
        buf = session.default_buffer
        text = buf.document.text_before_cursor
        if not text.startswith("/"):
            return buf.complete_state is not None
        return buf.complete_while_typing() or buf.complete_state is not None

    reserve_window = ConditionalContainer(
        Window(height=Dimension(min=len(SLASH_COMMANDS))),
        filter=Condition(_should_reserve_menu_space),
    )
    separator_spacer = Window(height=1, dont_extend_height=True)

    # Find the FloatContainer and inject into its content HSplit
    root_hsplit = session.layout.container
    for child in root_hsplit.children:
        if isinstance(child, FloatContainer):
            content_hsplit = child.content
            children = list(content_hsplit.children)
            children.append(separator_spacer)
            children.append(reserve_window)
            content_hsplit.children = children

            sep_float = None
            if input_window is not None:
                sep_float = Float(
                    left=0,
                    right=0,
                    height=1,
                    ycursor=True,
                    attach_to_window=input_window,
                    content=Window(
                        content=FormattedTextControl(_sep_text),
                        height=1,
                        dont_extend_height=True,
                    ),
                )
                child.floats.append(sep_float)

            # Shift completion menu floats down by 1 so they don't cover the separator
            for fl in child.floats:
                if fl is sep_float:
                    continue
                original_content = fl.content
                fl.content = HSplit([
                    Window(height=1),  # 1-line spacer
                    original_content,
                ])
            break

    return session


# ─── Welcome & main loop ───

def show_welcome() -> None:
    company = get_config("company")
    difficulty = get_config("difficulty") or "不限"
    mode = get_config("mode") or "default"
    mode_labels = {"default": "按频率", "random": "随机", "tag": "按标签"}
    mode_display = mode_labels.get(mode, mode)
    if mode == "tag":
        mode_display += f" ({get_config('tag') or '未设置'})"
    if company:
        console.print(f"\n[dim]当前目标: {company} | 难度: {difficulty} | 模式: {mode_display}[/dim]\n")
    else:
        console.print("\n[dim]首次使用？输入 /config 设置目标公司和难度。[/dim]\n")



def handle_today() -> None:
    """Show daily plan and let user pick a problem."""
    from lc.planner import generate_daily_plan
    from lc.display import show_daily_plan
    from lc.agent import _arrow_select, start_problem

    company = get_config("company") or None
    difficulty = get_config("difficulty") or None
    mode = get_config("mode") or "default"
    tag = get_config("tag") if mode == "tag" else None
    plan = generate_daily_plan(
        company=company, difficulty=difficulty, tag=tag, randomize=(mode == "random"),
    )
    show_daily_plan(plan)

    choices = []
    for _, problem in plan.review_problems:
        choices.append((f"[复习] #{problem.id} {problem.title} ({problem.difficulty})", problem))
    for problem in plan.new_problems:
        choices.append((f"[新题] #{problem.id} {problem.title} ({problem.difficulty})", problem))

    if choices:
        selected = _arrow_select(choices)
        if selected:
            start_problem(selected.id)


def handle_info() -> None:
    from datetime import datetime
    from rich.panel import Panel

    current = state.get_current()
    if not current:
        console.print("[yellow]当前没有在做题。[/yellow]")
        return

    pid, aid = current
    problem = db.get_problem(pid)
    attempt = db.get_attempt(aid)
    if not problem or not attempt:
        console.print("[red]数据异常。[/red]")
        return

    started = datetime.fromisoformat(attempt.started_at)
    elapsed = datetime.utcnow() - started
    minutes = int(elapsed.total_seconds() // 60)
    time_str = f"{minutes} 分钟" if minutes > 0 else "< 1 分钟"

    diff_colors = {"Easy": "green", "Medium": "yellow", "Hard": "red"}
    dc = diff_colors.get(problem.difficulty, "white")
    fp = state.get_file_path() or ""

    info = (
        f"题目: [bold]{problem.id}. {problem.title}[/bold] [{dc}]{problem.difficulty}[/{dc}]\n"
        f"标签: [dim]{', '.join(problem.tags)}[/dim]\n"
        f"用时: {time_str}\n"
        f"提示: {attempt.hints_used} 次  讲解: {attempt.teach_used} 次\n"
        f"文件: [dim]{fp}[/dim]"
    )
    console.print(Panel(info, title="当前做题", border_style="blue"))


def handle_undo() -> None:
    import json as _json

    raw = db.get_session("last_submit")
    if not raw:
        console.print("[yellow]没有可撤回的提交。[/yellow]")
        return

    try:
        info = _json.loads(raw)
    except Exception:
        console.print("[red]撤回数据损坏。[/red]")
        return

    pid = info["problem_id"]
    aid = info["attempt_id"]
    fp = info.get("file_path", "")

    problem = db.get_problem(pid)
    attempt = db.get_attempt(aid)
    if not problem or not attempt:
        console.print("[red]数据异常，无法撤回。[/red]")
        return

    if attempt.self_rating is None:
        console.print("[yellow]该提交已经被撤回过了。[/yellow]")
        return

    # Undo: revert attempt, delete associated reviews, restore state
    created_at = attempt.finished_at or attempt.started_at
    db.undo_finish_attempt(aid)
    db.delete_reviews_for_attempt(pid, created_at)
    db.update_tag_stats(pid)
    state.set_current(pid, aid, file_path=fp)
    db.delete_session("last_submit")

    console.print(f"[green]已撤回第 {pid} 题 {problem.title} 的提交（原评分: {attempt.self_rating}）[/green]")
    console.print(f"[dim]已恢复做题状态，可以继续或重新 /submit。[/dim]")


def handle_similar() -> None:
    from lc.agent import _arrow_select, start_problem
    from lc.display import show_similar
    from lc.leetcode_api import fetch_similar_problems
    from lc.models import Problem

    current = state.get_current()
    if not current:
        console.print("[yellow]当前没有在做题，无法查找相似题目。[/yellow]")
        return

    pid, _ = current
    problem = db.get_problem(pid)
    if not problem:
        console.print("[red]数据异常。[/red]")
        return

    console.print(f"[dim]正在查找与 {problem.id}. {problem.title} 相似的题目...[/dim]")
    try:
        similar_raw = fetch_similar_problems(problem.title_slug)
    except Exception as e:
        console.print(f"[red]获取失败: {e}[/red]")
        return

    if not similar_raw:
        console.print("[yellow]没有找到相似题目。[/yellow]")
        return

    similar_problems = []
    for s in similar_raw:
        diff = s.get("difficulty", "Unknown")
        similar_problems.append(Problem(
            id=0,
            title=s.get("title", ""),
            title_slug=s.get("titleSlug", ""),
            difficulty=diff,
        ))
    show_similar(similar_problems)

    choices = [
        (f"{p.title} ({p.difficulty})", p)
        for p in similar_problems if p.title_slug
    ]
    if choices:
        selected = _arrow_select(choices)
        if selected:
            from lc.leetcode_api import fetch_problem_by_slug
            try:
                full = fetch_problem_by_slug(selected.title_slug)
                start_problem(full.id)
            except Exception:
                console.print(f"[dim]请手动开始: 做 {selected.title}[/dim]")


def handle_status() -> None:
    from lc.display import show_status
    stats = db.get_attempt_stats()
    weak_tags = db.get_weakest_tags(limit=5)
    show_status(stats, weak_tags)


def handle_review() -> None:
    from lc.display import show_review_list
    from lc.agent import _arrow_select, start_problem

    pending = db.get_pending_reviews()
    reviews_with_problems = []
    for r in pending:
        problem = db.get_problem(r.problem_id)
        if problem:
            reviews_with_problems.append((r, problem))
    show_review_list(reviews_with_problems)

    if reviews_with_problems:
        choices = [
            (f"#{p.id} {p.title} ({p.difficulty}) — {r.interval_days}天复习", p)
            for r, p in reviews_with_problems
        ]
        selected = _arrow_select(choices)
        if selected:
            start_problem(selected.id)


def handle_submit() -> None:
    from lc.agent import _arrow_select, submit_current_problem

    current = state.get_current()
    if not current:
        console.print("[yellow]当前没有在做题。[/yellow]")
        return

    pid, _ = current
    problem = db.get_problem(pid)
    title = f"{problem.id}. {problem.title}" if problem else f"#{pid}"

    console.print(f"[dim]提交: {title}[/dim]")
    console.print("[dim]自评: 1=轻松搞定 2=稍有思考 3=想了一阵 4=很吃力 5=没做出来[/dim]")

    choices = [
        ("1 - 轻松搞定", 1),
        ("2 - 稍有思考", 2),
        ("3 - 想了一阵", 3),
        ("4 - 很吃力", 4),
        ("5 - 没做出来", 5),
    ]
    rating = _arrow_select(choices)
    if rating is None:
        console.print("[dim]已取消提交。[/dim]")
        return

    submit_current_problem(rating)


def handle_hot() -> None:
    from lc.codetop_api import fetch_hot_problems
    from lc.display import show_hot_problems
    from lc.agent import _arrow_select, start_problem

    company = get_config("company") or None
    problems, total = fetch_hot_problems(company=company, page=1)
    if not problems:
        console.print("[yellow]暂无数据。请先用 /config 设置公司。[/yellow]")
        return
    solved_ids = db.get_solved_problem_ids()
    show_hot_problems(problems[:15], solved_ids, company=company)

    from lc.models import Problem
    choices = [
        (f"#{cp.leetcode_id} {cp.title} ({cp.difficulty})",
         Problem(id=cp.leetcode_id, title=cp.title, title_slug=cp.title_slug, difficulty=cp.difficulty))
        for cp in problems[:15]
    ]
    selected = _arrow_select(choices)
    if selected:
        start_problem(selected.id)


def _get_prompt() -> str:
    current = state.get_current()
    if current:
        pid, _ = current
        problem = db.get_problem(pid)
        if problem:
            return f"{pid} {problem.title} > "
    return "> "


def app() -> None:
    """Main REPL entry point."""
    db.init_db()
    state.clear_current()

    from importlib.metadata import version as pkg_version
    from pathlib import Path
    from lc.config import DEEPSEEK_MODEL
    try:
        ver = pkg_version("leetcode-agent")
    except Exception:
        ver = "0.1.0"
    cwd = Path.cwd()
    console.print(
        f"[bold]LeetCode Agent[/bold] v{ver}  "
        f"[dim]{DEEPSEEK_MODEL} · {cwd}[/dim]"
    )
    show_welcome()

    from lc.agent import Agent
    agent = Agent()
    session = _build_prompt_session()
    empty_count = 0
    ctrl_c_pending = False

    while True:
        try:
            prompt_text = _get_prompt()
            w = console.size.width
            console.print(f"[#000000]{'─' * w}[/#000000]")
            user_input = session.prompt(prompt_text)
            ctrl_c_pending = False
            text = user_input.strip()
            if not text:
                empty_count += 1
                if empty_count >= 2:
                    console.print("[dim]输入 /help 查看帮助[/dim]")
                    empty_count = 0
                continue
            empty_count = 0

            # Direct commands — no AI needed
            if text in ("/quit", "/exit", "/q", "退出", "再见"):
                console.print("[dim]再见！[/dim]")
                break
            if text in ("/config", "设置"):
                handle_config()
                continue
            if text in ("/help", "帮助", "?", "？"):
                console.print(HELP_TEXT)
                continue
            if text in ("/today", "/plan"):
                handle_today()
                continue
            if text in ("/submit", "提交"):
                handle_submit()
                continue
            if text in ("/info",):
                handle_info()
                continue
            if text in ("/similar",):
                handle_similar()
                continue
            if text in ("/undo",):
                handle_undo()
                continue
            if text in ("/status", "/stats"):
                handle_status()
                continue
            if text in ("/review",):
                handle_review()
                continue
            if text in ("/hot",):
                handle_hot()
                continue

            # Everything else → agent
            agent.chat(text)

        except KeyboardInterrupt:
            if ctrl_c_pending or not state.get_current():
                console.print("\n[dim]再见！[/dim]")
                break
            ctrl_c_pending = True
            console.print(f"\n[dim]再按一次 Ctrl+C 退出，输入 /submit 提交[/dim]")
            continue
        except EOFError:
            break


def main():
    app()
