from __future__ import annotations

from rich.prompt import Prompt
from rich.panel import Panel

from lc import db
from lc.config import DATA_DIR
from lc.display import DIFFICULTY_COLORS, console, show_companies, show_tags

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

    # ── 公司 ──
    from lc.codetop_api import fetch_companies
    console.print("[dim]正在获取公司列表...[/dim]")
    companies = fetch_companies()
    if companies:
        show_companies(companies)

    current_company = get_config("company") or ""
    prompt_hint = f"目标公司（当前: {current_company}，直接回车清除）" if current_company else "目标公司（直接回车跳过）"
    company = Prompt.ask(prompt_hint, default="")
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
        if current_company:
            set_config("company", "")
            console.print("[green]公司限制已清除[/green]")
        else:
            console.print("[dim]公司: 跳过[/dim]")

    # ── 难度 ──
    console.print()
    # Map stored value (e.g. "Medium") back to choice key (e.g. "medium")
    _diff_reverse = {v.lower(): k for k, v in DIFFICULTY_CHOICES.items()}
    stored_diff = (get_config("difficulty") or "").lower()
    diff_default = _diff_reverse.get(stored_diff, "all")
    diff = Prompt.ask(
        "难度偏好",
        choices=["easy", "medium", "hard", "all"],
        default=diff_default,
    )
    if diff == "all":
        set_config("difficulty", "")
        console.print("[green]难度: 不限[/green]")
    else:
        set_config("difficulty", DIFFICULTY_CHOICES[diff])
        console.print(f"[green]难度已设置为: {DIFFICULTY_CHOICES[diff]}[/green]")

    # ── 排序方式 ──
    console.print()
    current_mode = get_config("mode") or "default"
    if current_mode == "tag":
        current_mode = "default"  # migrate old "tag" mode
    mode = Prompt.ask(
        "排序方式",
        choices=["default", "random"],
        default=current_mode,
    )
    set_config("mode", mode)
    mode_labels = {"default": "按频率", "random": "随机"}
    console.print(f"[green]排序: {mode_labels[mode]}[/green]")

    # ── 标签过滤（独立于排序） ──
    console.print()
    current_tag = get_config("tag") or ""
    tag_prompt = f"标签过滤（当前: {current_tag}，直接回车清除）" if current_tag else "标签过滤（直接回车跳过）"
    from lc.codetop_api import fetch_tags
    console.print("[dim]正在获取标签列表...[/dim]")
    tags = fetch_tags()
    if tags:
        show_tags(tags)
    tag_input = Prompt.ask(tag_prompt, default="")
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
        if current_tag:
            set_config("tag", "")
            console.print("[green]标签过滤已清除[/green]")
        else:
            console.print("[dim]标签: 跳过[/dim]")

    # ── 汇总 ──
    console.print()
    company_display = get_config("company") or "不限"
    diff_display = get_config("difficulty") or "不限"
    mode_display = mode_labels.get(get_config("mode") or "default", "按频率")
    tag_display = get_config("tag") or "不限"
    console.print(Panel(
        f"公司: [cyan]{company_display}[/cyan]\n"
        f"难度: [cyan]{diff_display}[/cyan]\n"
        f"排序: [cyan]{mode_display}[/cyan]\n"
        f"标签: [cyan]{tag_display}[/cyan]",
        title="当前设置",
        border_style="blue",
    ))
    console.print("[green]设置完成！[/green]\n")


# ─── Prompt session ───

SLASH_COMMANDS = [
    ("/config", "设置公司、难度、排序、标签"),
    ("/clear",  "清屏 + 清除对话历史"),
    ("/help",   "显示帮助"),
    ("/quit",   "退出"),
]

HELP_TEXT = """
[bold]自然语言对话:[/bold]
  "帮我做第 146 题"  "给个提示"  "讲解一下"
  "今天做什么"  "推荐热门题"  "回顾一下之前做的题"

[bold]快捷指令:[/bold]
  [cyan]/config[/cyan]  设置公司、难度、排序、标签
  [cyan]/clear[/cyan]   清屏 + 清除对话历史
  [cyan]/help[/cyan]    显示帮助
  [cyan]/quit[/cyan]    退出

[bold]记忆系统:[/bold]
  [dim]LeetCode.md[/dim]   在工作区根目录创建，写入你的自定义指令和偏好
  [dim]用户偏好[/dim]      AI 自动记录你的编码习惯和薄弱点（~/.leetcode_agent/user_memory.md）
  [dim]题目记忆[/dim]      每道题的 .memories/ 文件，记录做题心得和难点
""".strip()


def _build_prompt_session():
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
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

    @kb.add("enter")
    def _enter_submit(event):
        """Enter submits the input (override multiline default)."""
        event.current_buffer.validate_and_handle()

    @kb.add("c-j")  # Ctrl+Enter sends Ctrl+J
    def _newline(event):
        """Ctrl+Enter inserts a newline for multi-line input."""
        event.current_buffer.insert_text("\n")

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

    history_path = str(DATA_DIR / "history")
    session = PromptSession(
        completer=SlashCompleter(),
        complete_while_typing=True,
        key_bindings=kb,
        style=style,
        reserve_space_for_menu=0,
        history=FileHistory(history_path),
        multiline=True,
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
    from importlib.metadata import version as pkg_version
    from pathlib import Path
    from lc.config import DEEPSEEK_MODEL

    try:
        ver = pkg_version("leetcode-agent")
    except Exception:
        ver = "0.1.0"
    cwd = Path.cwd()

    company = get_config("company")
    difficulty = get_config("difficulty") or "不限"
    mode = get_config("mode") or "default"
    mode_labels = {"default": "按频率", "random": "随机"}
    mode_display = mode_labels.get(mode, mode)
    tag = get_config("tag")
    if tag:
        mode_display += f" | 标签: {tag}"
    company_display = company or "不限"
    config_line = f"目标: {company_display} | 难度: {difficulty} | {mode_display}"

    c = "dark_goldenrod"
    logo = (
        f"[{c}]▄    ▄███▄  ▄▄▄[/]   [bold]LeetCode Agent[/bold] v{ver}\n"
        f"[{c}]█   ██ █ █  █[/]    [dim]{DEEPSEEK_MODEL} · {cwd}[/dim]\n"
        f"[{c}]█▄▄  ▀█▀█▀  █▄▄[/]   [dim]{config_line}[/dim]"
    )
    console.print(logo)



def app() -> None:
    """Main REPL entry point."""
    db.init_db()
    show_welcome()

    from lc.agent import Agent
    agent = Agent()
    session = _build_prompt_session()
    empty_count = 0
    ctrl_c_pending = False

    while True:
        try:
            prompt_text = "> "
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
            if text in ("/clear",):
                console.clear()
                agent.messages.clear()
                continue

            # Everything else → agent
            agent.chat(text)

        except KeyboardInterrupt:
            if ctrl_c_pending:
                console.print("\n[dim]再见！[/dim]")
                break
            ctrl_c_pending = True
            console.print(f"\n[dim]再按一次 Ctrl+C 退出[/dim]")
            continue
        except EOFError:
            break


def main():
    app()
