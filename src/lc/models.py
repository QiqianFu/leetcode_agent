from __future__ import annotations

from dataclasses import dataclass, field

# 12 algorithm categories — used for folder naming.
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
