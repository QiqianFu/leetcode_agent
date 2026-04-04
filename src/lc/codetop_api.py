from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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
    with httpx.Client(timeout=15) as client:
        for attempt in range(retries + 1):
            try:
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


_companies_cache: list[dict] | None = None


def fetch_companies() -> list[dict]:
    """Return list of {'id': int, 'name': str} (cached)."""
    global _companies_cache
    if _companies_cache is not None:
        return _companies_cache
    data = _get("/companies/", {})
    if isinstance(data, list):
        _companies_cache = [{"id": c["id"], "name": c["name"]} for c in data]
        return _companies_cache
    return []


_tags_cache: list[dict] | None = None


def fetch_tags() -> list[dict]:
    """Return list of {'id': int, 'name': str} from CodeTop tags API (cached)."""
    global _tags_cache
    if _tags_cache is not None:
        return _tags_cache
    data = _get("/tags/", {})
    if isinstance(data, list):
        _tags_cache = [{"id": t["id"], "name": t["name"]} for t in data]
        return _tags_cache
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


# English -> Chinese tag mapping for CodeTop (whose tags are in Chinese)
_TAG_EN_TO_ZH = {
    "dynamic programming": "动态规划", "dp": "动态规划",
    "greedy": "贪心",
    "binary search": "二分查找",
    "two pointers": "双指针", "sliding window": "滑动窗口",
    "dfs": "深度优先搜索", "depth-first search": "深度优先搜索",
    "bfs": "广度优先搜索", "breadth-first search": "广度优先搜索",
    "backtracking": "回溯",
    "sorting": "排序", "sort": "排序",
    "stack": "栈", "queue": "队列",
    "tree": "树", "binary tree": "二叉树",
    "graph": "图", "union find": "并查集", "topological sort": "拓扑排序",
    "design": "设计",
    "math": "数学", "bit manipulation": "位运算",
    "string": "字符串", "string matching": "字符串匹配",
    "hash table": "哈希表", "array": "数组", "linked list": "链表",
    "heap": "堆", "trie": "字典树", "segment tree": "线段树",
    "recursion": "递归", "divide and conquer": "分治",
}


def _find_tag_id(tag_name: str) -> int | None:
    """Find CodeTop tag ID by name (exact then fuzzy, supports English input)."""
    tags = fetch_tags()
    tag_lower = tag_name.lower()

    # Try exact match first
    for t in tags:
        if t["name"].lower() == tag_lower:
            return t["id"]

    # If user typed English, translate to Chinese and match
    zh_name = _TAG_EN_TO_ZH.get(tag_lower, "")
    if zh_name:
        for t in tags:
            if t["name"] == zh_name:
                return t["id"]

    # Fuzzy match
    for t in tags:
        t_lower = t["name"].lower()
        if tag_lower in t_lower or t_lower in tag_lower:
            return t["id"]
        if zh_name and zh_name in t["name"]:
            return t["id"]

    return None


def fetch_hot_problems(
    company: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CodetopProblem], int]:
    """Fetch problems sorted by frequency. Returns (problems, total_count)."""
    params: dict = {
        "page": page,
        "page_size": page_size,
        "search": "",
        "ordering": "-frequency",
    }

    # Resolve company_id and tag_id in parallel when both are needed
    if company and tag:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cid_future = pool.submit(_find_company_id, company)
            tid_future = pool.submit(_find_tag_id, tag)
            cid = cid_future.result()
            tid = tid_future.result()
        if cid is None:
            return [], 0
        params["company"] = cid
        if tid is not None:
            params["tag"] = tid
    elif company:
        cid = _find_company_id(company)
        if cid is None:
            return [], 0
        params["company"] = cid
    elif tag:
        tid = _find_tag_id(tag)
        if tid is not None:
            params["tag"] = tid

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


