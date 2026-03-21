from __future__ import annotations

from dataclasses import dataclass, field

from lc import db
from lc.config import MAX_NEW_PROBLEMS_PER_DAY, MAX_TOTAL_PROBLEMS_PER_DAY
from lc.models import Problem, Review

# CodeTop uses Chinese tag names, LeetCode uses English.
_TAG_ZH_TO_EN: dict[str, str] = {
    "哈希表": "hash table",
    "数组": "array",
    "排序": "sorting",
    "动态规划": "dynamic programming",
    "数学": "math",
    "字符串": "string",
    "双指针": "two pointers",
    "位运算": "bit manipulation",
    "分治算法": "divide and conquer",
    "堆": "heap",
    "队列": "queue",
    "二分查找": "binary search",
    "深度优先搜索": "depth-first search",
    "广度优先搜索": "breadth-first search",
    "并查集": "union find",
    "栈": "stack",
    "设计": "design",
    "字典树": "trie",
    "记忆化": "memoization",
    "树": "tree",
    "二叉搜索树": "binary search tree",
    "递归": "recursion",
    "链表": "linked list",
    "几何": "geometry",
    "回溯算法": "backtracking",
    "图": "graph",
    "贪心算法": "greedy",
    "线段树": "segment tree",
    "脑筋急转弯": "brainteaser",
    "拓扑排序": "topological sort",
    "极小化极大": "minimax",
    "拒绝采样": "rejection sampling",
    "树状数组": "binary indexed tree",
    "蓄水池抽样": "reservoir sampling",
}


@dataclass
class DailyPlan:
    review_problems: list[tuple[Review, Problem]] = field(default_factory=list)
    new_problems: list[Problem] = field(default_factory=list)


def generate_daily_plan(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    randomize: bool = False,
) -> DailyPlan:
    """Generate today's practice plan.

    Priority:
    1. Review problems always come first
    2. New problems: pick unsolved from CodeTop by frequency (filtered by company/difficulty/tag)
    3. Fallback to local DB weak-tag based selection if no CodeTop filters

    If randomize=True, shuffle the new problems instead of sorting by frequency.
    """
    plan = DailyPlan()

    # 1. Pending reviews always first (deduplicate by problem_id)
    pending = db.get_pending_reviews_by_problem()
    for review in pending:
        problem = db.get_problem(review.problem_id)
        if problem:
            plan.review_problems.append((review, problem))

    # 2. New problems
    remaining = MAX_TOTAL_PROBLEMS_PER_DAY - len(plan.review_problems)
    if remaining <= 0:
        return plan
    new_limit = min(remaining, MAX_NEW_PROBLEMS_PER_DAY)

    # If any filter is set, use CodeTop
    if company or difficulty or tag:
        plan.new_problems = _pick_from_codetop(
            company=company, difficulty=difficulty, tag=tag,
            limit=new_limit, randomize=randomize,
        )
    else:
        if randomize:
            # Random mode without filters: pick from a larger CodeTop pool
            plan.new_problems = _pick_from_codetop(
                limit=new_limit, randomize=True,
            )
        else:
            # Fallback: weak tags from local DB
            weak_tags = db.get_weakest_tags(limit=3)
            if weak_tags:
                tag_names = [t.tag for t in weak_tags]
                plan.new_problems = db.get_unsolved_by_tags(tag_names, limit=new_limit)

    return plan


def _match_tag(tag: str, problem_tags: list[str]) -> bool:
    """Check if tag matches any of the problem's tags (supports Chinese→English)."""
    # Translate Chinese tag to English if possible
    tag_en = _TAG_ZH_TO_EN.get(tag, "").lower()
    tag_lower = tag.lower()
    for t in problem_tags:
        t_lower = t.lower()
        if tag_lower in t_lower or (tag_en and tag_en in t_lower):
            return True
    return False


def _pick_from_codetop(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    limit: int = 5,
    randomize: bool = False,
) -> list[Problem]:
    """Pick unsolved problems from CodeTop.

    Fetches pages incrementally until we have at least `limit` candidates.
    If randomize=True, fetch extra pages and randomly sample.
    """
    import random
    from lc.codetop_api import fetch_hot_problems

    attempted_ids = db.get_attempted_problem_ids()
    candidates = []
    page = 1
    max_pages = 20  # safety cap

    # Random mode: gather a larger pool (at least 5x limit)
    target = limit * 5 if randomize else limit

    while page <= max_pages and len(candidates) < target:
        problems, total = fetch_hot_problems(company=company, page=page, page_size=20)
        if not problems:
            break

        for cp in problems:
            if cp.leetcode_id in attempted_ids:
                continue
            if difficulty and cp.difficulty != difficulty:
                continue
            if tag:
                p = db.get_problem(cp.leetcode_id)
                if not p or not p.tags:
                    try:
                        from lc.leetcode_api import fetch_problem
                        p = fetch_problem(cp.leetcode_id)
                        db.upsert_problem(p)
                    except Exception:
                        continue
                if not _match_tag(tag, p.tags):
                    continue

            candidates.append(Problem(
                id=cp.leetcode_id,
                title=cp.title,
                title_slug=cp.title_slug,
                difficulty=cp.difficulty,
                ac_rate=None,
                tags=[],
            ))

        # Check if we've exhausted all available problems
        if page * 20 >= total:
            break
        page += 1

    if randomize and len(candidates) > limit:
        return random.sample(candidates, limit)
    return candidates[:limit]
