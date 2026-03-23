from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from lc.codetop_api import CodetopProblem
from lc.models import CATEGORY_LABELS, Problem, Review, TagStat
from lc.planner import DailyPlan

console = Console()

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


def show_daily_plan(plan: DailyPlan) -> None:
    if not plan.review_problems and not plan.new_problems:
        console.print("[green]今天没有需要做的题目！[/green]")
        return

    if plan.review_problems:
        table = Table(title="复习题目", border_style="yellow")
        table.add_column("#", style="cyan", width=6)
        table.add_column("题目", style="white")
        table.add_column("难度", width=8)
        table.add_column("标签", style="dim")
        for review, problem in plan.review_problems:
            diff_color = DIFFICULTY_COLORS.get(problem.difficulty, "white")
            table.add_row(
                str(problem.id),
                problem.title,
                f"[{diff_color}]{problem.difficulty}[/{diff_color}]",
                ", ".join(problem.tags[:3]),
            )
        console.print(table)
        console.print()

    if plan.new_problems:
        table = Table(title="新题推荐", border_style="green")
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


def show_status(stats: dict, weak_tags: list[TagStat]) -> None:
    console.print()
    # Summary panel
    total = stats["total_solved"]
    by_diff = stats["by_difficulty"]
    avg = stats["avg_rating"]
    pending = stats["pending_reviews"]

    recent_7d = stats.get("recent_7d", 0)
    streak = stats.get("streak", 0)

    summary = (
        f"已做题目: [bold cyan]{total}[/bold cyan]  "
        f"([green]Easy {by_diff.get('Easy', 0)}[/green] | "
        f"[yellow]Medium {by_diff.get('Medium', 0)}[/yellow] | "
        f"[red]Hard {by_diff.get('Hard', 0)}[/red])\n"
        f"平均评分: [bold]{avg:.1f}[/bold] / 5\n"
        f"最近 7 天: [bold cyan]{recent_7d}[/bold cyan] 题  "
        f"连续刷题: [bold cyan]{streak}[/bold cyan] 天\n"
        f"待复习: [bold yellow]{pending}[/bold yellow] 题"
    )
    console.print(Panel(summary, title="刷题统计", border_style="blue"))

    if weak_tags:
        table = Table(title="薄弱题型（按评分排序）", border_style="red")
        table.add_column("题型", style="white")
        table.add_column("做题数", style="cyan", justify="right")
        table.add_column("平均评分", style="yellow", justify="right")
        for ts in weak_tags:
            label = CATEGORY_LABELS.get(ts.tag, ts.tag)
            table.add_row(label, str(ts.total_attempts), f"{ts.avg_rating:.1f}")
        console.print(table)


def show_review_list(reviews: list[tuple[Review, Problem]]) -> None:
    if not reviews:
        console.print("[green]没有需要复习的题目！[/green]")
        return

    table = Table(title="待复习题目", border_style="yellow")
    table.add_column("#", style="cyan", width=6)
    table.add_column("题目", style="white")
    table.add_column("难度", width=8)
    table.add_column("间隔", style="dim", justify="right")
    for review, problem in reviews:
        diff_color = DIFFICULTY_COLORS.get(problem.difficulty, "white")
        table.add_row(
            str(problem.id),
            problem.title,
            f"[{diff_color}]{problem.difficulty}[/{diff_color}]",
            f"{review.interval_days}天",
        )
    console.print(table)
    console.print()


def show_similar(problems: list[Problem]) -> None:
    if not problems:
        console.print("[yellow]没有找到相似题目。[/yellow]")
        return

    table = Table(title="相似题目", border_style="cyan")
    table.add_column("#", style="cyan", width=6)
    table.add_column("题目", style="white")
    table.add_column("难度", width=8)
    for p in problems:
        diff_color = DIFFICULTY_COLORS.get(p.difficulty, "white")
        table.add_row(
            str(p.id) if p.id else "?",
            p.title,
            f"[{diff_color}]{p.difficulty}[/{diff_color}]",
        )
    console.print(table)


def show_submit_summary(problem: Problem, rating: int, reviews_scheduled: int, time_spent: str) -> None:
    console.print()
    diff_color = DIFFICULTY_COLORS.get(problem.difficulty, "white")
    review_msg = f"已安排 [yellow]{reviews_scheduled}[/yellow] 次复习" if reviews_scheduled else "[green]无需复习[/green]"
    summary = (
        f"题目: [bold]{problem.id}. {problem.title}[/bold] [{diff_color}]{problem.difficulty}[/{diff_color}]\n"
        f"评分: [bold]{rating}[/bold] / 5\n"
        f"用时: {time_spent}\n"
        f"{review_msg}"
    )
    console.print(Panel(summary, title="提交完成", border_style="green"))


def show_hot_problems(
    problems: list[CodetopProblem],
    attempted_ids: set[int],
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
        status = "[yellow]复习[/yellow]" if cp.leetcode_id in attempted_ids else "[dim]新题[/dim]"
        table.add_row(
            str(cp.leetcode_id),
            cp.title,
            f"[{diff_color}]{cp.difficulty}[/{diff_color}]",
            str(cp.frequency),
            status,
        )
    console.print(table)
    console.print()


def show_plan_problems(problems: list[dict], current_index: int, name: str = "") -> None:
    title = f"刷题计划 — {name}" if name else "刷题计划"
    total = len(problems)
    table = Table(title=f"{title} ({total} 题)", border_style="magenta")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("题号", style="cyan", width=6)
    table.add_column("题目", style="white")
    table.add_column("难度", width=8)
    table.add_column("状态", width=6, justify="center")
    for i, p in enumerate(problems):
        diff_color = DIFFICULTY_COLORS.get(p["difficulty"], "white")
        if i < current_index:
            status = "[green]done[/green]"
        elif i == current_index:
            status = "[bold cyan]→[/bold cyan]"
        else:
            status = "[dim]·[/dim]"
        table.add_row(
            str(i + 1),
            str(p["id"]),
            p["title"],
            f"[{diff_color}]{p['difficulty']}[/{diff_color}]",
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
