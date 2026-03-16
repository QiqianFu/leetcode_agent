from __future__ import annotations

from dataclasses import dataclass, field

from lc import db
from lc.config import MAX_NEW_PROBLEMS_PER_DAY, MAX_TOTAL_PROBLEMS_PER_DAY
from lc.models import Problem, Review


@dataclass
class DailyPlan:
    review_problems: list[tuple[Review, Problem]] = field(default_factory=list)
    new_problems: list[Problem] = field(default_factory=list)


def generate_daily_plan(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
) -> DailyPlan:
    """Generate today's practice plan.

    Priority:
    1. Review problems always come first
    2. New problems: pick unsolved from CodeTop by frequency (filtered by company/difficulty/tag)
    3. Fallback to local DB weak-tag based selection if no CodeTop filters
    """
    plan = DailyPlan()

    # 1. Pending reviews always first
    pending = db.get_pending_reviews()
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
            company=company, difficulty=difficulty, tag=tag, limit=new_limit
        )
    else:
        # Fallback: weak tags from local DB
        weak_tags = db.get_weakest_tags(limit=3)
        if weak_tags:
            tag_names = [t.tag for t in weak_tags]
            plan.new_problems = db.get_unsolved_by_tags(tag_names, limit=new_limit)

    return plan


def _pick_from_codetop(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    limit: int = 5,
) -> list[Problem]:
    """Pick unsolved problems from CodeTop, ordered by frequency."""
    from lc.codetop_api import fetch_all_hot

    solved_ids = db.get_solved_problem_ids()
    hot = fetch_all_hot(company=company, max_pages=1)

    results = []
    for cp in hot:
        if cp.leetcode_id in solved_ids:
            continue
        if difficulty and cp.difficulty != difficulty:
            continue
        # Tag filter
        if tag:
            p = db.get_problem(cp.leetcode_id)
            if not p or not p.tags:
                # Not in DB — fetch from LeetCode and cache
                try:
                    from lc.leetcode_api import fetch_problem
                    p = fetch_problem(cp.leetcode_id)
                    db.upsert_problem(p)
                except Exception:
                    continue  # Can't verify tag, skip
            if not any(tag.lower() in t.lower() for t in p.tags):
                continue

        results.append(Problem(
            id=cp.leetcode_id,
            title=cp.title,
            title_slug=cp.title_slug,
            difficulty=cp.difficulty,
            ac_rate=None,
            tags=[],
        ))
        if len(results) >= limit:
            break

    return results
