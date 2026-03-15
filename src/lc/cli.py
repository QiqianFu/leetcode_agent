from __future__ import annotations

from rich.prompt import Prompt
from rich.panel import Panel

from lc import db, state
from lc.display import console, show_companies

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

    console.print()
    company_display = get_config("company") or "未设置"
    diff_display = get_config("difficulty") or "不限"
    console.print(Panel(
        f"公司: [cyan]{company_display}[/cyan]\n难度: [cyan]{diff_display}[/cyan]",
        title="当前设置",
        border_style="blue",
    ))
    console.print("[green]设置完成！[/green]\n")


# ─── Prompt session ───

SLASH_COMMANDS = [
    ("/config", "设置公司和难度偏好"),
    ("/help",   "显示帮助"),
    ("/quit",   "退出"),
]

HELP_TEXT = """
[bold]你可以直接用自然语言和我对话，比如:[/bold]

  "帮我做第 146 题"
  "给个提示"
  "讲解一下这道题"
  "我做完了"
  "放弃"
  "今天做什么"
  "看看我的统计"
  "有哪些高频题"

[bold]快捷指令:[/bold]
  [cyan]/config[/cyan]  设置公司和难度偏好
  [cyan]/help[/cyan]    显示帮助
  [cyan]/quit[/cyan]    退出
""".strip()


def _build_prompt_session():
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith("/"):
                for cmd, desc in SLASH_COMMANDS:
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
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

    style = Style.from_dict({
        "prompt": "bold ansiblue",
        "completion-menu": "bg:default",
        "completion-menu.completion": "bg:default ansiblue",
        "completion-menu.completion.current": "bg:default bold ansiblue underline",
        "completion-menu.meta.completion": "bg:default ansigray italic",
        "completion-menu.meta.completion.current": "bg:default ansigray italic underline",
        "completion-menu.multi-column-meta": "bg:default ansigray",
        "scrollbar.background": "bg:default",
        "scrollbar.button": "bg:ansigray",
    })

    return PromptSession(
        completer=SlashCompleter(),
        complete_while_typing=True,
        key_bindings=kb,
        style=style,
    )


# ─── Welcome & main loop ───

def show_welcome() -> None:
    current = state.get_current()
    if current:
        pid, _ = current
        problem = db.get_problem(pid)
        title = f"{problem.title}" if problem else ""
        console.print(f"\n[yellow]上次未完成: 第 {pid} 题 {title}[/yellow]")
        fp = state.get_file_path()
        if fp:
            console.print(f"[dim]解题文件: {fp}[/dim]")
        console.print("[dim]继续对话即可获取提示或提交。[/dim]\n")
    else:
        company = get_config("company")
        if company:
            console.print(f"\n[dim]当前目标: {company} | 直接对话开始刷题[/dim]\n")
        else:
            console.print("\n[dim]首次使用？输入 /config 设置目标公司和难度。[/dim]\n")


def app() -> None:
    """Main REPL entry point."""
    db.init_db()

    console.print(Panel(
        "[bold]LeetCode 刷题助手[/bold]\n[dim]智能复习 + AI 辅导[/dim]",
        border_style="blue",
    ))
    show_welcome()

    from lc.agent import Agent
    agent = Agent()
    session = _build_prompt_session()

    while True:
        try:
            user_input = session.prompt("> ")
            text = user_input.strip()
            if not text:
                continue

            # Only these stay as direct commands
            if text in ("/quit", "/exit", "/q", "退出", "再见"):
                console.print("[dim]再见！[/dim]")
                break
            if text in ("/config", "设置"):
                handle_config()
                continue
            if text in ("/help", "帮助", "?", "？"):
                console.print(HELP_TEXT)
                continue

            # Everything else → agent
            agent.chat(text)

        except KeyboardInterrupt:
            console.print("\n[dim]Ctrl+C 退出[/dim]")
            break
        except EOFError:
            break


def main():
    app()
