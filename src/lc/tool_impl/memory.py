"""Memory read/write tools (L3 per-problem memory)."""
from __future__ import annotations

import json
from pathlib import Path

from lc import db


def tool_read_memory(problem_id: int | None = None, **_) -> str:
    if not problem_id:
        return json.dumps(
            {"status": "error", "message": "请传入 problem_id。"},
            ensure_ascii=False,
        )
    memory = db.get_memory(problem_id)
    if not memory:
        return json.dumps({
            "status": "error",
            "problem_id": problem_id,
            "message": f"第 {problem_id} 题没有记忆文件。",
        }, ensure_ascii=False)
    memory_path = Path(memory["memory_file"])
    if not memory_path.exists():
        return json.dumps({
            "status": "error",
            "problem_id": problem_id,
            "message": f"记忆文件不存在: {memory['memory_file']}",
        }, ensure_ascii=False)

    content = memory_path.read_text(encoding="utf-8")
    # `\n## ` marks a real section (analyze_and_memorize / write_memory output);
    # its absence means the file is still the initial header template.
    has_l3_content = "\n## " in content
    return json.dumps({
        "status": "ok",
        "problem_id": problem_id,
        "has_l3_content": has_l3_content,
        "bytes": len(content.encode("utf-8")),
        "content": content,
    }, ensure_ascii=False)


def tool_write_memory(problem_id: int | None = None, content: str = "",
                      mode: str = "append", **_) -> str:
    if not problem_id:
        return json.dumps(
            {"status": "error", "message": "请传入 problem_id。"},
            ensure_ascii=False,
        )
    if not content:
        return json.dumps(
            {"status": "error", "message": "请传入要写入的 content。"},
            ensure_ascii=False,
        )
    memory = db.get_memory(problem_id)
    if not memory:
        return json.dumps({
            "status": "error",
            "problem_id": problem_id,
            "message": f"第 {problem_id} 题没有记忆文件。请先用 start_problem 开始做题。",
        }, ensure_ascii=False)
    memory_path = Path(memory["memory_file"])
    existing = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    before_bytes = len(existing.encode("utf-8"))

    if mode == "overwrite":
        memory_path.write_text(content, encoding="utf-8")
        after_bytes = len(content.encode("utf-8"))
        return json.dumps({
            "status": "overwrote",
            "problem_id": problem_id,
            "changed": content.strip() != existing.strip(),
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
        }, ensure_ascii=False)

    stripped = content.strip()
    if stripped and stripped in existing:
        return json.dumps({
            "status": "skipped_duplicate",
            "problem_id": problem_id,
            "message": "内容已存在于记忆文件中，未重复追加。",
        }, ensure_ascii=False)

    payload = "\n" + content + "\n"
    with memory_path.open("a", encoding="utf-8") as f:
        f.write(payload)
    return json.dumps({
        "status": "appended",
        "problem_id": problem_id,
        "bytes_added": len(payload.encode("utf-8")),
    }, ensure_ascii=False)
