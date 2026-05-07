from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

from lc import db
from lc.models import Problem


def _pick_from_codetop(
    company: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    limit: int = 5,
    randomize: bool = False,
) -> tuple[list[Problem], dict]:
    """Pick unsolved problems from CodeTop.

    Uses CodeTop server-side filtering for tag. If the tag can't be resolved
    server-side, it is ignored (no slow per-problem LeetCode API calls).

    Returns (candidates, stats). `stats` lets the caller distinguish "filter too
    strict" from "user has done all the hot ones":
        - scanned_count: total CodeTop problems inspected
        - filtered_practiced: dropped because user already practiced
        - filtered_difficulty: dropped because difficulty mismatch
        - tag_requested / tag_resolved: surface that user-requested tag was
          dropped server-side because CodeTop doesn't have a matching tag id
        - target_unmet: True iff randomize wanted more candidates than we found
    """
    from lc.codetop_api import fetch_hot_problems, _find_tag_id

    practiced_ids = db.get_practiced_problem_ids()
    seen_ids: set[int] = set()
    candidates = []
    scanned_count = 0
    filtered_practiced = 0
    filtered_difficulty = 0
    page = 1
    max_pages = 20
    batch_size = 3  # fetch multiple pages in parallel

    target = limit * 5 if randomize else limit

    # Normalize difficulty: "easy" / "EASY" / "Easy" → "Easy" (matches CodeTop's form)
    difficulty_norm = (difficulty or "").strip().title() or None

    # Only pass tag to CodeTop if it can resolve it server-side
    tag_resolved = bool(tag and _find_tag_id(tag) is not None)
    server_tag = tag if tag_resolved else None

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
                scanned_count += 1
                if cp.leetcode_id in seen_ids:
                    continue
                if cp.leetcode_id in practiced_ids:
                    filtered_practiced += 1
                    continue
                if difficulty_norm and (cp.difficulty or "").title() != difficulty_norm:
                    filtered_difficulty += 1
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

    target_unmet = randomize and len(candidates) < target

    if randomize and len(candidates) > limit:
        candidates = random.sample(candidates, limit)

    stats = {
        "scanned_count": scanned_count,
        "filtered_practiced": filtered_practiced,
        "filtered_difficulty": filtered_difficulty,
        "tag_requested": tag,
        "tag_resolved": tag_resolved,
        "target_unmet": target_unmet,
    }
    return candidates[:limit], stats
