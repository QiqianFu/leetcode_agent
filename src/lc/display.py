from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from rich.theme import Theme

from lc.codetop_api import CodetopProblem
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


def show_daily_plan(plan) -> None:
    if not plan.new_problems:
        console.print("[green]今天没有需要做的题目！[/green]")
        return

    if plan.new_problems:
        table = Table(title="推荐题目", border_style="green")
        table.add_column("#", style="cyan", width=6)
        table.add_column("题目", style="white")
        table.add_column("难度", width=8)
        table.add_column("标签", style="dim")
        for problem in plan.new_problems:
            diff_color = DIFFICULTY_COLORS.get(problem.difficulty, "white")
            table.add_row(
                str(problem.id),
                problem.title,
                f"[{diff_color}]{problem.difficulty}[/{diff_color}]",
                ", ".join(problem.tags[:3]),
            )
        console.print(table)

    console.print()


def show_hot_problems(
    problems: list[CodetopProblem],
    practiced_ids: set[int],
    company: str | None = None,
) -> None:
    title = f"高频题 — {company}" if company else "高频题 — 全站"
    table = Table(title=title, border_style="magenta")
    table.add_column("#", style="cyan", width=6)
    table.add_column("题目", style="white")
    table.add_column("难度", width=8)
    table.add_column("频率", style="magenta", justify="right")
    table.add_column("状态", width=6, justify="center")
    for cp in problems:
        diff_color = DIFFICULTY_COLORS.get(cp.difficulty, "white")
        status = "[green]已做[/green]" if cp.leetcode_id in practiced_ids else "[dim]新题[/dim]"
        table.add_row(
            str(cp.leetcode_id),
            cp.title,
            f"[{diff_color}]{cp.difficulty}[/{diff_color}]",
            str(cp.frequency),
            status,
        )
    console.print(table)
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
