"""Tests for memory read/write tools and the _has_l3_content helper."""
from __future__ import annotations

import pytest

from lc.tool_impl.memory import tool_read_memory, tool_write_memory
from lc.tool_impl.subagents import _has_l3_content


class TestHasL3Content:
    def test_empty_file_returns_false(self, tmp_path):
        f = tmp_path / "mem.md"
        f.write_text("", encoding="utf-8")
        assert _has_l3_content(str(f)) is False

    def test_header_only_returns_false(self, tmp_path):
        f = tmp_path / "mem.md"
        f.write_text("# 1. Two Sum\n- Difficulty: Easy\n- Tags: array\n", encoding="utf-8")
        assert _has_l3_content(str(f)) is False

    def test_with_section_returns_true(self, tmp_path):
        f = tmp_path / "mem.md"
        f.write_text("# 1. Two Sum\n\n## 解题思路\n哈希表。\n", encoding="utf-8")
        assert _has_l3_content(str(f)) is True

    def test_nonexistent_file_returns_false(self, tmp_path):
        assert _has_l3_content(str(tmp_path / "ghost.md")) is False


class TestToolReadMemory:
    def test_missing_problem_id(self):
        result = tool_read_memory()
        assert "problem_id" in result

    def test_no_memory_in_db(self, monkeypatch):
        import lc.tool_impl.memory as m
        monkeypatch.setattr(m.db, "get_memory", lambda pid: None)
        result = tool_read_memory(problem_id=999)
        assert "没有记忆文件" in result

    def test_memory_file_missing_on_disk(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {
            "memory_file": str(tmp_path / "missing.md")
        })
        result = tool_read_memory(problem_id=1)
        assert "不存在" in result

    def test_reads_content(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_two_sum.md"
        f.write_text("# 1. Two Sum\nsome notes", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})
        result = tool_read_memory(problem_id=1)
        assert "Two Sum" in result


class TestToolWriteMemory:
    def test_missing_problem_id(self):
        result = tool_write_memory(content="hello")
        assert "problem_id" in result

    def test_missing_content(self):
        result = tool_write_memory(problem_id=1)
        assert "content" in result

    def test_no_memory_in_db(self, monkeypatch):
        import lc.tool_impl.memory as m
        monkeypatch.setattr(m.db, "get_memory", lambda pid: None)
        result = tool_write_memory(problem_id=999, content="notes")
        assert "没有记忆文件" in result

    def test_append_mode(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_two_sum.md"
        f.write_text("# header\n", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})
        tool_write_memory(problem_id=1, content="new note", mode="append")
        assert "new note" in f.read_text(encoding="utf-8")
        assert "# header" in f.read_text(encoding="utf-8")

    def test_overwrite_mode(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_two_sum.md"
        f.write_text("old content", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})
        tool_write_memory(problem_id=1, content="new content", mode="overwrite")
        assert f.read_text(encoding="utf-8") == "new content"
