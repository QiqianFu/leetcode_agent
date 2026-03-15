from __future__ import annotations

from datetime import date, timedelta

from lc.models import Review


def schedule_review(
    problem_id: int, self_rating: int, hints_used: int, teach_used: int
) -> list[Review] | None:
    """Decide review schedule based on how the user performed.

    Returns None if no review is needed (solved easily with no help).
    """
    if self_rating <= 2 and hints_used == 0 and teach_used == 0:
        return None

    struggle_score = self_rating + (hints_used * 0.5) + (teach_used * 1.0)

    if struggle_score >= 5:
        intervals = [1, 3, 7, 14, 30]
    elif struggle_score >= 3:
        intervals = [1, 7, 30]
    else:
        intervals = [3, 14]

    today = date.today()
    return [
        Review(
            problem_id=problem_id,
            due_date=(today + timedelta(days=days)).isoformat(),
            interval_days=days,
        )
        for days in intervals
    ]


def handle_review_submit(
    review: Review, self_rating: int
) -> tuple[list[Review], bool]:
    """Handle review completion. Returns (new_reviews, should_cancel_future).

    should_cancel_future: if True, caller should cancel all remaining reviews.
    """
    if self_rating <= 2:
        # Mastered — cancel all future reviews
        return [], True
    elif self_rating >= 4:
        # Still struggling — add a short-interval review
        new_review = Review(
            problem_id=review.problem_id,
            due_date=(date.today() + timedelta(days=1)).isoformat(),
            interval_days=1,
        )
        return [new_review], False
    else:
        # Medium — keep existing schedule
        return [], False
