"""Regression tests for the 9-item atomicity audit fixes.

Each class covers one specific information-compression / idempotency issue
surfaced by the design-time audit. Comments cite the Tier (T1/T2/T3) and
original symptom so future readers can trace the rationale.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─── T1a: update_user_memory data-protection ───

class TestUpdateUserMemorySafety:
    """Sub-agent must not be able to silently collapse a rich L2 into a stub."""

    def test_refuses_suspicious_shrinkage(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem = tmp_path / "user_memory.md"
        mem.write_text("x" * 1000, encoding="utf-8")
        monkeypatch.setattr(sa, "USER_MEMORY_PATH", mem)
        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "tiny")

        result = json.loads(sa.tool_update_user_memory(
            hint="", client=MagicMock(), messages=[]
        ))
        assert result["status"] == "refused"
        assert result["reason"] == "suspicious_shrinkage"
        assert mem.read_text(encoding="utf-8") == "x" * 1000, \
            "original content must be preserved"

    def test_accepts_reasonable_update(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem = tmp_path / "user_memory.md"
        mem.write_text("# old\nsome preferences here" * 10, encoding="utf-8")
        monkeypatch.setattr(sa, "USER_MEMORY_PATH", mem)
        new_content = "# new\n" + "integrated preferences " * 40
        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: new_content)

        result = json.loads(sa.tool_update_user_memory(
            hint="", client=MagicMock(), messages=[]
        ))
        assert result["status"] == "updated"
        assert result["changed"] is True
        assert "before_bytes" in result and "after_bytes" in result

    def test_empty_subagent_reports_failed(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem = tmp_path / "user_memory.md"
        mem.write_text("existing content", encoding="utf-8")
        monkeypatch.setattr(sa, "USER_MEMORY_PATH", mem)
        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "")

        result = json.loads(sa.tool_update_user_memory(
            hint="", client=MagicMock(), messages=[]
        ))
        assert result["status"] == "failed"
        assert result["reason"] == "subagent_empty"
        assert mem.read_text(encoding="utf-8") == "existing content"


# ─── T1b: analyze_and_memorize data-protection ───

class TestAnalyzeAndMemorizeSafety:
    """L3 summary must not be silently clobbered by a collapsed sub-agent output."""

    def test_refuses_suspicious_shrinkage(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem_file = tmp_path / "1_two_sum.md"
        mem_file.write_text("# 1. Two Sum\n" + ("## section\ncontent here\n" * 50),
                            encoding="utf-8")
        monkeypatch.setattr(sa.db, "get_memory", lambda pid: {
            "problem_id": 1, "title": "Two Sum", "difficulty": "Easy",
            "tags": "array", "memory_file": str(mem_file),
        })
        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "tiny")
        monkeypatch.setattr(sa, "workspace_root", lambda: tmp_path)

        result = json.loads(sa.tool_analyze_and_memorize(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        assert result["l3_written"] is False
        assert result["reason"] == "suspicious_shrinkage"
        # File unchanged
        assert "section" in mem_file.read_text(encoding="utf-8")


# ─── T1c: start_problem state transparency ───

class TestStartProblemState:
    """start_problem must tell the model whether this is a fresh open or a resume."""

    @pytest.fixture
    def isolated_db(self, monkeypatch):
        """Isolate the DB layer: in-memory dict replaces sqlite for this test.

        Otherwise tests hit ~/.leetcode_agent/leetcode.db which carries state
        from real user sessions (e.g. problem_id=1 already present).
        """
        from lc import workspace as ws
        store: dict[int, dict] = {}

        def fake_get_memory(pid):
            return store.get(pid)

        def fake_upsert(pid, title, memory_file, difficulty="", tags=""):
            store[pid] = {
                "problem_id": pid, "title": title, "difficulty": difficulty,
                "tags": tags, "memory_file": memory_file,
            }

        monkeypatch.setattr(ws.db, "get_memory", fake_get_memory)
        monkeypatch.setattr(ws.db, "upsert_memory", fake_upsert)
        return store

    def _fake_problem(self, pid=1):
        from lc.models import Problem
        return Problem(id=pid, title="Two Sum", title_slug="two-sum",
                       difficulty="Easy", description="desc",
                       ac_rate=0.5, tags=["Array"], code_snippet="class Solution: pass",
                       category="two_pointers")

    def _setup_deps(self, monkeypatch):
        from lc import workspace as ws
        monkeypatch.setattr("lc.leetcode_api.fetch_problem",
                            lambda pid: self._fake_problem(pid))
        monkeypatch.setattr(ws, "classify_problem", lambda prob, client: "two_pointers")

    def test_created_state_for_fresh_problem(self, tmp_path, monkeypatch, isolated_db):
        monkeypatch.chdir(tmp_path)
        self._setup_deps(monkeypatch)
        from lc.tool_impl import problems as p

        result = json.loads(p.tool_start_problem(problem_id=1, client=MagicMock()))
        assert result["state"] == "created"
        assert result["solution_preexisted"] is False
        assert result["memory_preexisted"] is False
        assert result["db_entry_preexisted"] is False
        assert result["memory_has_l3_content"] is False

    def test_resumed_state_when_all_preexisted(self, tmp_path, monkeypatch, isolated_db):
        monkeypatch.chdir(tmp_path)
        self._setup_deps(monkeypatch)
        from lc.tool_impl import problems as p

        p.tool_start_problem(problem_id=1, client=MagicMock())
        result = json.loads(p.tool_start_problem(problem_id=1, client=MagicMock()))
        assert result["state"] == "resumed"
        assert result["solution_preexisted"] is True
        assert result["memory_preexisted"] is True
        assert result["db_entry_preexisted"] is True

    def test_partial_state_when_only_some_preexist(self, tmp_path, monkeypatch, isolated_db):
        """User manually deleted solution file; DB + memory file still there."""
        monkeypatch.chdir(tmp_path)
        self._setup_deps(monkeypatch)
        from lc.tool_impl import problems as p

        p.tool_start_problem(problem_id=1, client=MagicMock())
        for sol in (tmp_path / "two_pointers").glob("*.py"):
            sol.unlink()

        result = json.loads(p.tool_start_problem(problem_id=1, client=MagicMock()))
        assert result["state"] == "partial"
        assert result["solution_preexisted"] is False
        assert result["memory_preexisted"] is True
        assert result["db_entry_preexisted"] is True


# ─── T2a: append_solution dup detection ───

class TestAppendSolutionDedup:
    def test_skipped_when_content_already_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_append_solution
        # File must live inside workspace_root()
        f = tmp_path / "design" / "1_x.py"
        f.parent.mkdir()
        f.write_text("# existing\nprint('hello world')\n", encoding="utf-8")

        result = json.loads(tool_append_solution(
            file_path=str(f), content="print('hello world')"
        ))
        assert result["status"] == "skipped_duplicate"
        assert "print('hello world')" in f.read_text(encoding="utf-8")
        # Ensure we didn't double-append
        assert f.read_text(encoding="utf-8").count("print('hello world')") == 1

    def test_appends_when_new_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_append_solution
        f = tmp_path / "design" / "1_x.py"
        f.parent.mkdir()
        f.write_text("# existing\n", encoding="utf-8")

        result = json.loads(tool_append_solution(
            file_path=str(f), content="def new_solution(): pass"
        ))
        assert result["status"] == "appended"
        assert result["bytes_added"] > 0
        assert "def new_solution()" in f.read_text(encoding="utf-8")


# ─── T2b: write_memory dup detection + overwrite signal ───

class TestWriteMemoryStructuredReturn:
    def test_skipped_duplicate_append(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_x.md"
        f.write_text("# header\n\n## 解题思路\n哈希表 O(n)\n", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})

        result = json.loads(m.tool_write_memory(
            problem_id=1, content="哈希表 O(n)", mode="append"
        ))
        assert result["status"] == "skipped_duplicate"

    def test_overwrite_returns_byte_diff(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_x.md"
        f.write_text("old content", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})

        result = json.loads(m.tool_write_memory(
            problem_id=1, content="new content here", mode="overwrite"
        ))
        assert result["status"] == "overwrote"
        assert result["changed"] is True
        assert result["before_bytes"] == len("old content".encode("utf-8"))
        assert result["after_bytes"] == len("new content here".encode("utf-8"))

    def test_append_returns_bytes_added(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_x.md"
        f.write_text("header\n", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})

        result = json.loads(m.tool_write_memory(
            problem_id=1, content="fresh note", mode="append"
        ))
        assert result["status"] == "appended"
        assert result["bytes_added"] > 0


# ─── T3a: search_leetcode annotates already-practiced ───

class TestSearchLeetcodePracticeAnnotation:
    def test_annotates_practiced(self, monkeypatch):
        from lc.tool_impl import problems as p
        from lc.models import Problem

        monkeypatch.setattr(
            "lc.leetcode_api.search_problems",
            lambda kw, limit: [
                Problem(id=1, title="Two Sum", title_slug="two-sum",
                        difficulty="Easy", ac_rate=0.5, tags=["Array"]),
                Problem(id=9999, title="Mystery", title_slug="mystery",
                        difficulty="Hard", ac_rate=0.1, tags=["DP"]),
            ],
        )
        monkeypatch.setattr(p.db, "get_practiced_problem_ids", lambda: {1})

        result = json.loads(p.tool_search_leetcode(keyword="sum"))
        by_id = {x["id"]: x for x in result["problems"]}
        assert by_id[1]["already_practiced"] is True
        assert by_id[9999]["already_practiced"] is False


# ─── T3b: read_memory surfaces has_l3_content ───

class TestReadMemoryHasL3Flag:
    def test_header_only_flagged(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_x.md"
        f.write_text("# 1. Two Sum\n- 难度: Easy\n- 标签: array\n", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})

        result = json.loads(m.tool_read_memory(problem_id=1))
        assert result["status"] == "ok"
        assert result["has_l3_content"] is False

    def test_with_section_flagged_true(self, tmp_path, monkeypatch):
        import lc.tool_impl.memory as m
        f = tmp_path / "1_x.md"
        f.write_text("# 1. Two Sum\n\n## 解题思路\n哈希表\n", encoding="utf-8")
        monkeypatch.setattr(m.db, "get_memory", lambda pid: {"memory_file": str(f)})

        result = json.loads(m.tool_read_memory(problem_id=1))
        assert result["has_l3_content"] is True


# ─── T3c: list_practiced total_in_db + list_hot_problems empty classification ───

class TestListPracticedTotalInDb:
    def test_reports_total_even_when_filter_empties(self, monkeypatch):
        from lc.tool_impl import problems as p
        monkeypatch.setattr(p.db, "get_all_memories", lambda: [
            {"problem_id": 1, "title": "A", "difficulty": "Easy", "tags": "array", "memory_file": "x"},
            {"problem_id": 2, "title": "B", "difficulty": "Easy", "tags": "array", "memory_file": "x"},
        ])
        result = json.loads(p.tool_list_practiced(tag="dp"))
        assert result["total_in_db"] == 2
        assert result["total_matched"] == 0


class TestListHotProblemsEmptyReason:
    def test_all_practiced_reason(self, monkeypatch):
        from lc.tool_impl import problems as p
        # Return ([], stats showing filtered_practiced dominates)
        monkeypatch.setattr(
            "lc.planner._pick_from_codetop",
            lambda **kw: ([], {
                "scanned_count": 10,
                "filtered_practiced": 9,
                "filtered_difficulty": 0,
            }),
        )
        monkeypatch.setattr("lc.cli.get_config", lambda k: None)

        result = json.loads(p.tool_list_hot_problems(tag="dp"))
        assert result["problems"] == []
        assert result["reason"] == "all_practiced"
        assert result["stats"]["filtered_practiced"] == 9

    def test_empty_pool_reason(self, monkeypatch):
        from lc.tool_impl import problems as p
        monkeypatch.setattr(
            "lc.planner._pick_from_codetop",
            lambda **kw: ([], {
                "scanned_count": 0,
                "filtered_practiced": 0,
                "filtered_difficulty": 0,
            }),
        )
        monkeypatch.setattr("lc.cli.get_config", lambda k: None)

        result = json.loads(p.tool_list_hot_problems(tag="obscure"))
        assert result["reason"] == "empty_pool"


# ─── T3d: find_similar_problems hallucination signal + file guard ───

class TestFindSimilarHallucination:
    def test_hallucination_explicitly_flagged(self, monkeypatch):
        from lc.tool_impl import subagents as sa
        # Subagent returns 3 IDs, none exist in DB
        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "9999\n8888\n7777")
        monkeypatch.setattr(sa, "_has_l3_content", lambda _: True)
        monkeypatch.setattr(sa.db, "get_memory", lambda pid: (
            {"problem_id": pid, "title": "Cur", "difficulty": "Easy",
             "tags": "dp", "memory_file": "/tmp/x.md"} if pid == 1 else None
        ))
        monkeypatch.setattr(sa.db, "get_all_memories", lambda: [
            {"problem_id": 100, "title": "Other", "difficulty": "Easy",
             "tags": "dp", "memory_file": "/tmp/100.md"},
        ])

        result = json.loads(sa.tool_find_similar_problems(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        assert result["similar_problems"] == []
        assert result["reason"] == "subagent_hallucinated"
        assert result["hallucination_count"] >= 2

    def test_missing_file_does_not_crash(self, tmp_path, monkeypatch):
        """DB entry exists but memory file deleted from disk — must skip gracefully."""
        from lc.tool_impl import subagents as sa
        ghost_path = tmp_path / "deleted.md"  # never created

        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "200")
        # _has_l3_content returns False for nonexistent file, which skips it
        # cleanly. The risk we're guarding: a future refactor that skips the
        # _has_l3_content check and goes straight to read_text. Patch _has_l3_content
        # to True to exercise the read_text path.
        monkeypatch.setattr(sa, "_has_l3_content", lambda _: True)

        def _get_memory(pid):
            if pid == 1:
                return {"problem_id": 1, "title": "Cur", "difficulty": "Easy",
                        "tags": "dp", "memory_file": str(tmp_path / "1.md")}
            if pid == 200:
                return {"problem_id": 200, "title": "Gone", "difficulty": "Easy",
                        "tags": "dp", "memory_file": str(ghost_path)}
            return None
        monkeypatch.setattr(sa.db, "get_memory", _get_memory)
        monkeypatch.setattr(sa.db, "get_all_memories", lambda: [
            {"problem_id": 200, "title": "Gone", "difficulty": "Easy",
             "tags": "dp", "memory_file": str(ghost_path)},
        ])

        # Must not raise
        result = json.loads(sa.tool_find_similar_problems(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        # 200 was proposed but file missing → skipped, not crashed
        assert result["similar_problems"] == []
        assert result.get("stale_entries", 0) >= 1


# ─── instruction-injection removal regression ───

class TestFindSimilarNoInstructionField:
    """find_similar_problems used to embed prescriptive instruction text in the
    response (P1 anti-pattern). Removal is permanent — guard against re-introduction.
    """

    def test_no_instruction_in_response(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem_file = tmp_path / "100.md"
        mem_file.write_text("# 100\n\n## 解题思路\nBFS\n", encoding="utf-8")

        monkeypatch.setattr(sa, "_sub_agent_call", lambda *a, **kw: "100")
        monkeypatch.setattr(sa, "_has_l3_content", lambda _: True)
        monkeypatch.setattr(sa.db, "get_memory", lambda pid: {
            "problem_id": pid, "title": f"P{pid}", "difficulty": "Easy",
            "tags": "dp",
            "memory_file": str(mem_file if pid == 100 else tmp_path / f"{pid}.md"),
        })
        monkeypatch.setattr(sa.db, "get_all_memories", lambda: [
            {"problem_id": 100, "title": "P100", "difficulty": "Easy",
             "tags": "dp", "memory_file": str(mem_file)},
        ])

        result = json.loads(sa.tool_find_similar_problems(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        assert "instruction" not in result, \
            "instruction field re-introduced — violates P1 'tool return ≠ instruction'"
