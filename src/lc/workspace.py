from __future__ import annotations

import re
from pathlib import Path

from openai import OpenAI

from lc import db
from lc.config import DEEPSEEK_MODEL
from lc.display import console
from lc.models import CATEGORIES, Problem


# ─── Text / path helpers ───

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text


def detect_imports(snippet: str) -> str:
    """Detect typing and data structure imports needed by the code snippet."""
    typing_types = ["List", "Optional", "Dict", "Set", "Tuple", "Deque"]
    needed_typing = [t for t in typing_types if re.search(rf'\b{t}\b', snippet)]

    lines = []
    if needed_typing:
        lines.append(f"from typing import {', '.join(needed_typing)}")
    if "collections." in snippet or re.search(r'\b(deque|defaultdict|Counter|OrderedDict)\b', snippet):
        lines.append("import collections")
    if re.search(r'\bheapq\b', snippet):
        lines.append("import heapq")

    return "\n".join(lines)


# ─── Workspace file utilities ───

def workspace_root() -> Path:
    """Readonly workspace root for local lookup tools."""
    return Path.cwd().resolve()


def problem_files_in_workspace() -> list[Path]:
    root = workspace_root()
    results: list[Path] = []
    for cat in CATEGORIES:
        cat_dir = root / cat
        if cat_dir.is_dir():
            results.extend(p for p in cat_dir.rglob("*.py") if p.is_file())
    results.sort(key=lambda p: str(p.relative_to(root)))
    return results


def relative_workspace_path(path: Path) -> str:
    return str(path.resolve().relative_to(workspace_root()))


def extract_problem_id(path: Path) -> int | None:
    m = re.match(r"^(\d+)_", path.stem)
    return int(m.group(1)) if m else None


def workspace_file_payload(path: Path) -> dict:
    payload = {"file_path": relative_workspace_path(path)}
    problem_id = extract_problem_id(path)
    if problem_id is not None:
        payload["problem_id"] = problem_id
    return payload


# ─── Classification ───

_TAG_TO_CATEGORY = {
    # dp
    "dynamic programming": "dp", "memoization": "dp",
    # greedy
    "greedy": "greedy",
    # binary_search
    "binary search": "binary_search",
    # two_pointers
    "two pointers": "two_pointers", "sliding window": "two_pointers",
    # dfs_bfs
    "depth-first search": "dfs_bfs", "breadth-first search": "dfs_bfs",
    "backtracking": "dfs_bfs", "recursion": "dfs_bfs",
    # sorting
    "sorting": "sorting", "heap (priority queue)": "sorting",
    "merge sort": "sorting", "quickselect": "sorting", "counting sort": "sorting",
    "bucket sort": "sorting", "radix sort": "sorting",
    # stack_queue
    "stack": "stack_queue", "queue": "stack_queue",
    "monotonic stack": "stack_queue", "monotonic queue": "stack_queue",
    # tree
    "tree": "tree", "binary tree": "tree", "binary search tree": "tree",
    "trie": "tree", "segment tree": "tree", "binary indexed tree": "tree",
    "linked list": "tree",
    # graph
    "graph": "graph", "topological sort": "graph", "union find": "graph",
    "shortest path": "graph", "minimum spanning tree": "graph",
    # design
    "design": "design",
    # math_bit
    "math": "math_bit", "bit manipulation": "math_bit",
    "number theory": "math_bit", "combinatorics": "math_bit", "geometry": "math_bit",
    # string
    "string": "string", "string matching": "string",
    # --- 常见 tag 补充映射 ---
    "array": "two_pointers", "matrix": "dfs_bfs",
    "hash table": "two_pointers", "prefix sum": "two_pointers",
    "divide and conquer": "sorting",
    "simulation": "design",
    "enumeration": "math_bit", "brainteaser": "math_bit",
    "ordered set": "tree", "iterator": "design",
    "database": "design", "shell": "design",
    "concurrency": "design",
}


def pick_category_heuristic(tags: list[str]) -> str:
    """Fallback: map LeetCode tags to one of the 12 categories."""
    for tag in tags:
        cat = _TAG_TO_CATEGORY.get(tag.lower())
        if cat:
            return cat
    return "design"


def classify_problem(problem: Problem, client: OpenAI) -> str:
    """Use AI to classify a problem into one of the predefined categories."""
    categories_str = ", ".join(CATEGORIES)
    prompt = (
        f"将这道 LeetCode 题分类到以下类别之一（只回复类别名，不要其他内容）：\n"
        f"{categories_str}\n\n"
        f"题目: {problem.id}. {problem.title}\n"
        f"难度: {problem.difficulty}\n"
        f"LeetCode 标签: {', '.join(problem.tags)}\n"
    )
    if problem.description:
        prompt += f"描述: {problem.description[:200]}\n"

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        answer = resp.choices[0].message.content.strip().lower()
        # Normalize spaces / hyphens to underscores so AI replies like "two
        # pointers" or "stack-queue" match our underscore-form CATEGORIES.
        answer_norm = re.sub(r"[\s\-]+", "_", answer)
        for cat in CATEGORIES:
            if cat in answer_norm:
                return cat
    except Exception:
        pass
    return pick_category_heuristic(problem.tags)


# ─── File creation ───

def memory_dir() -> Path:
    """Directory for problem memory markdown files."""
    d = Path.cwd() / ".memories"
    d.mkdir(exist_ok=True)
    return d


def get_memory_path(problem: Problem) -> Path:
    """Get the memory file path for a problem."""
    return memory_dir() / f"{problem.id}_{slugify(problem.title)}.md"


def create_memory_file(problem: Problem) -> tuple[Path, bool]:
    """Create an initial memory file for a problem.

    Returns (path, created) — created is False if the file already existed.
    """
    memory_path = get_memory_path(problem)
    if memory_path.exists():
        return memory_path, False

    lines = [
        f"# {problem.id}. {problem.title}",
        f"- 难度: {problem.difficulty}",
        f"- 标签: {', '.join(problem.tags)}",
        f"- 链接: https://leetcode.com/problems/{problem.title_slug}/",
        "",
    ]
    memory_path.write_text("\n".join(lines), encoding="utf-8")
    return memory_path, True


def create_solution_file(problem: Problem) -> tuple[Path, bool]:
    """Create a solution file for a problem.

    Returns (path, created) — created is False if the file already existed.
    """
    category = slugify(problem.category or pick_category_heuristic(problem.tags))
    dir_path = Path.cwd() / category
    dir_path.mkdir(exist_ok=True)

    filename = f"{problem.id}_{slugify(problem.title)}.py"
    file_path = dir_path / filename

    if file_path.exists():
        return file_path, False

    lines = [
        f"# {problem.id}. {problem.title}",
        f"# https://leetcode.com/problems/{problem.title_slug}/",
        "",
    ]

    if problem.description:
        lines.append('"""')
        for desc_line in problem.description.strip().splitlines():
            lines.append(desc_line)
        lines.append('"""')
        lines.append("")

    snippet = problem.code_snippet or ""
    imports = detect_imports(snippet)
    if imports:
        lines.append(imports)
    lines.append("")

    if snippet:
        lines.append(snippet)
    else:
        lines.append("class Solution:")
        lines.append("    pass")

    lines.append("")
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path, True


# ─── Shared action ───

def start_problem(
    problem_id: int, client: OpenAI
) -> tuple[Problem, Path, Path, dict] | str:
    """Start a problem.

    Returns (problem, solution_path, memory_path, flags) on success; error str on failure.
    `flags` carries observables so callers can tell fresh-start from resume:
        - solution_preexisted, memory_preexisted, db_entry_preexisted: bool
        - memory_has_l3_content: bool (substantial L3 beyond header template)
        - cross_workspace_db_overwrite: bool (existing DB entry pointed at a
          different memory_file path → likely a different workspace; overwriting
          the index orphans the prior workspace's L3 lookup)
    """
    try:
        from lc.leetcode_api import fetch_problem
        with console.status("[bold cyan]正在获取题目...[/bold cyan]"):
            problem = fetch_problem(problem_id)
    except Exception as e:
        return f"获取题目失败: {e}"

    with console.status("[bold cyan]分类中...[/bold cyan]"):
        problem.category = classify_problem(problem, client)

    existing = db.get_memory(problem.id)
    db_entry_preexisted = existing is not None
    file_path, solution_created = create_solution_file(problem)
    memory_path, memory_created = create_memory_file(problem)

    # Detect substantial L3 content (vs. just the initial header template).
    # Kept inline to avoid importing from lc.tool_impl.subagents (circular).
    memory_has_l3_content = False
    try:
        memory_has_l3_content = "\n## " in memory_path.read_text(encoding="utf-8")
    except Exception:
        pass

    rel_memory = str(memory_path.relative_to(Path.cwd()))

    # Cross-workspace clash: DB index points at a memory_file that differs from
    # this workspace's path (or its abs-resolved version exists elsewhere).
    cross_workspace_db_overwrite = False
    if existing:
        existing_file = existing.get("memory_file") or ""
        if existing_file and existing_file != rel_memory:
            cross_workspace_db_overwrite = True

    db.upsert_memory(problem.id, problem.title, rel_memory,
                     difficulty=problem.difficulty,
                     tags=", ".join(problem.tags))

    rel_path = file_path.relative_to(Path.cwd())
    flags = {
        "solution_preexisted": not solution_created,
        "memory_preexisted": not memory_created,
        "db_entry_preexisted": db_entry_preexisted,
        "memory_has_l3_content": memory_has_l3_content,
        "cross_workspace_db_overwrite": cross_workspace_db_overwrite,
    }
    return problem, rel_path, memory_path, flags
