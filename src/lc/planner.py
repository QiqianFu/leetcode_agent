from __future__ import annotations

import random
from dataclasses import dataclass, field

from lc import db
from lc.config import MAX_NEW_PROBLEMS_PER_DAY, MAX_TOTAL_PROBLEMS_PER_DAY
from lc.models import Problem


@dataclass
class DailyPlan:
    new_problems: list[Problem] = field(default_factory=list)


def generate_daily_plan(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    randomize: bool = False,
) -> DailyPlan:
    """Generate today's practice plan from CodeTop."""
    plan = DailyPlan()
    new_limit = min(MAX_TOTAL_PROBLEMS_PER_DAY, MAX_NEW_PROBLEMS_PER_DAY)
    plan.new_problems = _pick_from_codetop(
        company=company, difficulty=difficulty, tag=tag,
        limit=new_limit, randomize=randomize,
    )
    return plan


def _pick_from_codetop(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    limit: int = 5,
    randomize: bool = False,
) -> list[Problem]:
    """Pick unsolved problems from CodeTop.

    Uses CodeTop server-side filtering for tag. If the tag can't be resolved
    server-side, it is ignored (no slow per-problem LeetCode API calls).
    """
    from lc.codetop_api import fetch_hot_problems, _find_tag_id

    practiced_ids = db.get_practiced_problem_ids()
    candidates = []
    page = 1
    max_pages = 20

    target = limit * 5 if randomize else limit

    # Only pass tag to CodeTop if it can resolve it server-side
    server_tag = tag if (tag and _find_tag_id(tag) is not None) else None

    while page <= max_pages and len(candidates) < target:
        problems, total = fetch_hot_problems(
            company=company, tag=server_tag, page=page, page_size=20,
        )
        if not problems:
            break

        for cp in problems:
            if cp.leetcode_id in practiced_ids:
                continue
            if difficulty and cp.difficulty != difficulty:
                continue
            candidates.append(Problem(
                id=cp.leetcode_id,
                title=cp.title,
                title_slug=cp.title_slug,
                difficulty=cp.difficulty,
                ac_rate=None,
                tags=[],
            ))

        if page * 20 >= total:
            break
        page += 1

    if randomize and len(candidates) > limit:
        candidates = random.sample(candidates, limit)

    return candidates[:limit]
