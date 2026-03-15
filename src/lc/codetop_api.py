from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

CODETOP_API_BASE = "https://codetop.cc/api"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://codetop.cc/home",
}

LEVEL_MAP = {1: "Easy", 2: "Medium", 3: "Hard"}


@dataclass
class CodetopProblem:
    leetcode_id: int
    title: str
    title_slug: str
    difficulty: str
    frequency: int  # 面试出现次数
    content: str | None = None


def _get(path: str, params: dict, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{CODETOP_API_BASE}{path}",
                    params=params,
                    headers=_HEADERS,
                )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, KeyError):
            if attempt < retries:
                time.sleep(1)
                continue
            raise
    return {}


def fetch_companies() -> list[dict]:
    """Return list of {'id': int, 'name': str}."""
    data = _get("/companies/", {})
    if isinstance(data, list):
        return [{"id": c["id"], "name": c["name"]} for c in data]
    return []


def _find_company_id(company_name: str) -> int | None:
    companies = fetch_companies()
    for c in companies:
        if c["name"] == company_name:
            return c["id"]
    # Fuzzy match
    for c in companies:
        if company_name.lower() in c["name"].lower():
            return c["id"]
    return None


def fetch_hot_problems(
    company: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CodetopProblem], int]:
    """Fetch problems sorted by frequency. Returns (problems, total_count)."""
    params: dict = {
        "page": page,
        "search": "",
        "ordering": "-frequency",
    }
    if company:
        cid = _find_company_id(company)
        if cid is None:
            return [], 0
        params["company"] = cid

    data = _get("/questions/", params)
    total = data.get("count", 0)
    problems = []
    for item in data.get("list", []):
        lc = item.get("leetcode", {})
        fqid = lc.get("frontend_question_id")
        if not fqid:
            continue
        try:
            lid = int(fqid)
        except (ValueError, TypeError):
            continue  # skip non-numeric IDs like '补充题4'
        problems.append(CodetopProblem(
            leetcode_id=lid,
            title=lc.get("title", ""),
            title_slug=lc.get("slug_title", ""),
            difficulty=LEVEL_MAP.get(lc.get("level", 0), "Unknown"),
            frequency=item.get("value", 0),
            content=lc.get("content"),
        ))
    return problems, total


def fetch_all_hot(
    company: str | None = None,
    max_pages: int = 10,
) -> list[CodetopProblem]:
    """Fetch multiple pages of hot problems, already sorted by frequency desc."""
    all_problems = []
    for page in range(1, max_pages + 1):
        problems, total = fetch_hot_problems(company=company, page=page, page_size=20)
        all_problems.extend(problems)
        if len(all_problems) >= total or not problems:
            break
    return all_problems
