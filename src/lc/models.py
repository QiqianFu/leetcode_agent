from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

# 12 algorithm categories — used for folder naming, stats, and weak-area tracking.
# AI classifies each problem into exactly one category on start.
CATEGORIES = [
    "dp",
    "greedy",
    "binary_search",
    "two_pointers",
    "dfs_bfs",
    "sorting",
    "stack_queue",
    "tree",
    "graph",
    "design",
    "math_bit",
    "string",
]

CATEGORY_LABELS: dict[str, str] = {
    "dp": "动态规划",
    "greedy": "贪心",
    "binary_search": "二分查找",
    "two_pointers": "双指针/滑动窗口",
    "dfs_bfs": "DFS/BFS/回溯",
    "sorting": "排序/堆",
    "stack_queue": "单调栈/队列",
    "tree": "树/BST/字典树",
    "graph": "图/拓扑/并查集",
    "design": "设计",
    "math_bit": "数学/位运算",
    "string": "字符串",
}


@dataclass
class Problem:
    id: int
    title: str
    title_slug: str
    difficulty: str
    description: str | None = None
    ac_rate: float | None = None
    tags: list[str] = field(default_factory=list)
    code_snippet: str = ""
    category: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Problem:
        keys = row.keys()
        return cls(
            id=row["id"],
            title=row["title"],
            title_slug=row["title_slug"],
            difficulty=row["difficulty"],
            description=row["description"],
            ac_rate=row["ac_rate"],
            category=row["category"] if "category" in keys else None,
        )


@dataclass
class Attempt:
    id: int
    problem_id: int
    started_at: str
    finished_at: str | None = None
    self_rating: int | None = None
    hints_used: int = 0
    teach_used: int = 0
    notes: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Attempt:
        return cls(
            id=row["id"],
            problem_id=row["problem_id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            self_rating=row["self_rating"],
            hints_used=row["hints_used"],
            teach_used=row["teach_used"],
            notes=row["notes"],
        )


@dataclass
class Review:
    problem_id: int
    due_date: str
    interval_days: int
    completed: bool = False
    id: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Review:
        return cls(
            id=row["id"],
            problem_id=row["problem_id"],
            due_date=row["due_date"],
            interval_days=row["interval_days"],
            completed=bool(row["completed"]),
        )


@dataclass
class TagStat:
    tag: str
    total_attempts: int
    avg_rating: float
    last_practiced: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TagStat:
        return cls(
            tag=row["tag"],
            total_attempts=row["total_attempts"],
            avg_rating=row["avg_rating"],
            last_practiced=row["last_practiced"],
        )
