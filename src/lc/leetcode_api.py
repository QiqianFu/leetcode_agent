from __future__ import annotations

import json
import re
import time

import httpx

from lc.config import LEETCODE_GRAPHQL_URL
from lc.models import Problem

_HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

PROBLEM_LIST_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      frontendQuestionId: questionFrontendId
      title
      titleSlug
      difficulty
      acRate
      topicTags { name slug }
    }
  }
}
"""

PROBLEM_DETAIL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    content
    difficulty
    topicTags { name slug }
    hints
    similarQuestions
    codeSnippets { lang langSlug code }
  }
}
"""


def _graphql(query: str, variables: dict, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    LEETCODE_GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    headers=_HEADERS,
                )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()["data"]
        except (httpx.HTTPError, KeyError):
            if attempt < retries:
                time.sleep(1)
                continue
            raise
    return {}


def _html_to_text(html: str) -> str:
    """Simple HTML to markdown-ish text conversion."""
    text = html
    text = re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)
    text = re.sub(r"<li>", "- ", text)
    text = re.sub(r"<p>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&#\d+;", lambda m: chr(int(m.group(0)[2:-1])), text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_problem(problem_id: int) -> Problem:
    """Fetch a problem by its frontend ID. Two API calls: list search + detail."""
    # Step 1: find titleSlug via search
    data = _graphql(PROBLEM_LIST_QUERY, {
        "categorySlug": "",
        "limit": 5,
        "skip": 0,
        "filters": {"searchKeywords": str(problem_id)},
    })
    questions = data.get("problemsetQuestionList", {}).get("questions", [])
    match = None
    for q in questions:
        if str(q["frontendQuestionId"]) == str(problem_id):
            match = q
            break
    if match is None:
        raise ValueError(f"Problem #{problem_id} not found on LeetCode")

    title_slug = match["titleSlug"]

    # Step 2: fetch full detail
    detail_data = _graphql(PROBLEM_DETAIL_QUERY, {"titleSlug": title_slug})
    q = detail_data["question"]

    description = _html_to_text(q.get("content") or "")
    tags = [t["name"] for t in q.get("topicTags", [])]

    # Extract Python3 code snippet
    code_snippet = ""
    for snippet in q.get("codeSnippets") or []:
        if snippet.get("langSlug") == "python3":
            code_snippet = snippet.get("code", "")
            break

    return Problem(
        id=int(q["questionFrontendId"]),
        title=q["title"],
        title_slug=q["titleSlug"],
        difficulty=q["difficulty"],
        description=description,
        ac_rate=match.get("acRate"),
        tags=tags,
        code_snippet=code_snippet,
    )


def fetch_problems_by_tag(tag_slug: str, limit: int = 50) -> list[Problem]:
    """Fetch problem list filtered by tag."""
    data = _graphql(PROBLEM_LIST_QUERY, {
        "categorySlug": "",
        "limit": limit,
        "skip": 0,
        "filters": {"tags": [tag_slug]},
    })
    questions = data.get("problemsetQuestionList", {}).get("questions", [])
    results = []
    for q in questions:
        results.append(Problem(
            id=int(q["frontendQuestionId"]),
            title=q["title"],
            title_slug=q["titleSlug"],
            difficulty=q["difficulty"],
            ac_rate=q.get("acRate"),
            tags=[t["name"] for t in q.get("topicTags", [])],
        ))
    return results


def fetch_similar_problems(title_slug: str) -> list[dict]:
    """Fetch similar problems from the similarQuestions field."""
    data = _graphql(PROBLEM_DETAIL_QUERY, {"titleSlug": title_slug})
    q = data.get("question", {})
    similar_raw = q.get("similarQuestions", "[]")
    try:
        return json.loads(similar_raw)
    except (json.JSONDecodeError, TypeError):
        return []
