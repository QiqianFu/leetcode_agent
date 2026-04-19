from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from rich.theme import Theme

from lc.models import Problem

_THEME = Theme({
    "markdown.code": "bold cyan",
    "markdown.code_block": "cyan",
})
console = Console(theme=_THEME)

DIFFICULTY_COLORS = {
    "Easy": "green",
    "Medium": "yellow",
    "Hard": "red",
}


def show_problem(problem: Problem) -> None:
    diff_color = DIFFICULTY_COLORS.get(problem.difficulty, "white")
    title = f"[bold]{problem.id}. {problem.title}[/bold]  [{diff_color}]{problem.difficulty}[/{diff_color}]"
    tags = "  ".join(f"[dim]{t}[/dim]" for t in problem.tags)

    console.print()
    console.print(Panel(title, subtitle=tags, border_style="blue"))
    if problem.description:
        console.print()
        console.print(Markdown(problem.description))
    console.print()


def show_companies(companies: list[dict]) -> None:
    table = Table(title="支持的公司", border_style="cyan")
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("公司", style="white")
    for c in companies:
        table.add_row(str(c["id"]), c["name"])
    console.print(table)
    console.print()
    console.print("[dim]输入公司名称即可选择[/dim]")


def show_tags(tags: list[dict]) -> None:
    table = Table(title="支持的标签", border_style="cyan")
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("标签", style="white")
    for t in tags:
        table.add_row(str(t["id"]), t["name"])
    console.print(table)
    console.print()
