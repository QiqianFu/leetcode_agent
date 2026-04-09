"""Memory read/write tools (L3 per-problem memory)."""
from __future__ import annotations

from pathlib import Path

from lc import db


def tool_read_memory(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"
    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。"
    memory_path = Path(memory["memory_file"])
    if not memory_path.exists():
        return f"记忆文件不存在: {memory['memory_file']}"
    return memory_path.read_text(encoding="utf-8")


def tool_write_memory(problem_id: int | None = None, content: str = "",
                      mode: str = "append", **_) -> str:
    if not problem_id:
        return "请传入 problem_id。"
    if not content:
        return "请传入要写入的 content。"
    memory = db.get_memory(problem_id)
    if not memory:
        return f"第 {problem_id} 题没有记忆文件。请先用 start_problem 开始做题。"
    memory_path = Path(memory["memory_file"])

    if mode == "overwrite":
        memory_path.write_text(content, encoding="utf-8")
    else:
        with memory_path.open("a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
    return "已写入记忆文件。"
