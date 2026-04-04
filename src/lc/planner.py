from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
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
    seen_ids: set[int] = set()
    candidates = []
    page = 1
    max_pages = 20
    batch_size = 3  # fetch multiple pages in parallel

    target = limit * 5 if randomize else limit

    # Only pass tag to CodeTop if it can resolve it server-side
    server_tag = tag if (tag and _find_tag_id(tag) is not None) else None

    while page <= max_pages and len(candidates) < target:
        # Fetch a batch of pages in parallel
        pages_to_fetch = list(range(page, min(page + batch_size, max_pages + 1)))

        if len(pages_to_fetch) == 1:
            page_results = {page: fetch_hot_problems(
                company=company, tag=server_tag, page=page, page_size=20,
            )}
        else:
            with ThreadPoolExecutor(max_workers=len(pages_to_fetch)) as pool:
                futures = {
                    pool.submit(
                        fetch_hot_problems,
                        company=company, tag=server_tag, page=p, page_size=20,
                    ): p
                    for p in pages_to_fetch
                }
                page_results = {futures[f]: f.result() for f in futures}

        done = False
        for p in sorted(page_results):
            problems, total = page_results[p]
            if not problems:
                done = True
                break

            for cp in problems:
                if cp.leetcode_id in practiced_ids:
                    continue
                if cp.leetcode_id in seen_ids:
                    continue
                if difficulty and cp.difficulty != difficulty:
                    continue
                seen_ids.add(cp.leetcode_id)
                candidates.append(Problem(
                    id=cp.leetcode_id,
                    title=cp.title,
                    title_slug=cp.title_slug,
                    difficulty=cp.difficulty,
                    ac_rate=None,
                    tags=[],
                ))

            if p * 20 >= total:
                done = True
                break

        if done:
            break
        page += batch_size

    if randomize and len(candidates) > limit:
        candidates = random.sample(candidates, limit)

    return candidates[:limit]
