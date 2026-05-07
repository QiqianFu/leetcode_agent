"""Regression tests for the 2026-04-25 audit fixes (BUGS.md).

Each class anchors one bug from BUGS.md so future readers can trace which
behavior is being locked down.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── #1: handle_config tag preservation on network failure ───

class TestHandleConfigTagPreservation:
    """User typing a tag while fetch_tags() returned [] must NOT clear the existing tag."""

    def test_network_failure_preserves_existing_tag(self, monkeypatch):
        from lc import cli

        store: dict[str, str] = {"cfg_tag": "graph"}
        monkeypatch.setattr(cli.db, "get_session", lambda k: store.get(k))
        monkeypatch.setattr(cli.db, "set_session",
                            lambda k, v: store.__setitem__(k, v))
        # Stub out other interactions
        monkeypatch.setattr("lc.codetop_api.fetch_companies", lambda: [])
        monkeypatch.setattr("lc.codetop_api.fetch_tags", lambda: [])  # network failed
        monkeypatch.setattr(cli, "show_companies", lambda *a, **kw: None)
        monkeypatch.setattr(cli, "show_tags", lambda *a, **kw: None)

        # Sequence: company="" diff=all mode=default tag="dp"
        prompts = iter(["", "all", "default", "dp"])
        monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **kw: next(prompts))
        cli.handle_config()

        # Tag must be preserved despite network failure on tag list fetch
        assert store["cfg_tag"] == "graph", \
            "Existing tag was wiped despite user providing input — should require valid tag list to change"

    def test_empty_input_clears_existing_tag(self, monkeypatch):
        from lc import cli

        store: dict[str, str] = {"cfg_tag": "graph"}
        monkeypatch.setattr(cli.db, "get_session", lambda k: store.get(k))
        monkeypatch.setattr(cli.db, "set_session",
                            lambda k, v: store.__setitem__(k, v))
        monkeypatch.setattr("lc.codetop_api.fetch_companies", lambda: [])
        monkeypatch.setattr("lc.codetop_api.fetch_tags",
                            lambda: [{"id": 1, "name": "dp"}])
        monkeypatch.setattr(cli, "show_companies", lambda *a, **kw: None)
        monkeypatch.setattr(cli, "show_tags", lambda *a, **kw: None)

        prompts = iter(["", "all", "default", ""])  # empty tag input
        monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **kw: next(prompts))
        cli.handle_config()
        assert store["cfg_tag"] == "", "Empty input should clear existing tag"


# ─── #2: non-retryable exception still rolls back ───

class TestChatRollbackOnNonRetryable:
    """BadRequestError / unexpected exception must still roll back orphaned tool_calls."""

    def test_rollback_on_bad_request(self, monkeypatch):
        from lc.agent import Agent
        from openai import BadRequestError
        import httpx

        call_count = [0]

        def flaky_call(msgs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ("", [{"id": "c1", "name": "check_problem",
                              "arguments": '{"problem_id": 70}'}], {})
            raise BadRequestError(
                message="context length", response=MagicMock(),
                body=None,
            )

        agent = Agent.__new__(Agent)
        agent.client = MagicMock()
        agent.messages = []
        agent._history_warned = False
        agent._call_model = flaky_call

        with patch("lc.agent.flush_stdin", lambda: None), \
             patch("lc.agent.execute_tool", return_value="{}"):
            agent.chat("hi")  # must not raise

        # No orphan tool_calls left
        for i, m in enumerate(agent.messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                expected = {tc["id"] for tc in m["tool_calls"]}
                actual = {n.get("tool_call_id")
                          for n in agent.messages[i + 1:]
                          if n.get("role") == "tool"}
                assert expected.issubset(actual), \
                    f"orphan tool_calls left after non-retryable error at idx {i}"


# ─── #3: _summarize_session_context covers all persistent tools ───

class TestSummarizeSessionContextScope:
    @pytest.mark.parametrize("tool_name", [
        "write_memory",
        "analyze_and_memorize",
        "update_user_memory",
        "append_solution",
        "start_problem",
    ])
    def test_each_persistent_tool_counts(self, tool_name):
        from lc.agent import Agent

        agent = Agent.__new__(Agent)
        agent.messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "tool_calls": [
                {"id": "x", "function": {"name": tool_name, "arguments": "{}"}},
            ]},
        ]
        assert agent._summarize_session_context() is True

    def test_pure_read_tools_dont_count(self):
        from lc.agent import Agent

        agent = Agent.__new__(Agent)
        agent.messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "tool_calls": [
                {"id": "x", "function": {"name": "read_memory", "arguments": "{}"}},
                {"id": "y", "function": {"name": "search_leetcode",
                                         "arguments": "{}"}},
            ]},
        ]
        assert agent._summarize_session_context() is False


# ─── #6: warning_threshold uses >= and re-arms after /clear ───

class TestHistoryWarningThreshold:
    """The threshold check must fire even if msg_count crosses by >1, and re-arm
    after history shrinks (e.g. /clear)."""

    def _agent(self, msgs):
        from lc.agent import Agent
        a = Agent.__new__(Agent)
        a.client = MagicMock()
        a.messages = list(msgs)
        a._history_warned = False
        a._call_model = lambda m: ("ok", [], {})
        return a

    def test_fires_when_at_or_past_threshold(self, monkeypatch):
        from lc.agent import Agent
        # threshold = int(200 * 0.8) = 160 by default. Use 161 (past threshold,
        # not exactly equal) — the >= check should still fire.
        agent = self._agent([{"role": "user", "content": "x"}] * 161)
        with patch("lc.agent.flush_stdin", lambda: None):
            with patch("lc.agent.console.print") as mock_print:
                agent.chat("trigger")
        warned = any("会话已使用" in str(c) for c in mock_print.call_args_list)
        assert warned, "warning should fire when msg_count >= threshold (was strict ==)"
        assert agent._history_warned is True

    def test_does_not_fire_below_threshold(self):
        from lc.agent import Agent
        agent = self._agent([{"role": "user", "content": "x"}] * 50)
        with patch("lc.agent.flush_stdin", lambda: None):
            with patch("lc.agent.console.print") as mock_print:
                agent.chat("trigger")
        warned = any("会话已使用" in str(c) for c in mock_print.call_args_list)
        assert not warned

    def test_rearms_when_shrinks_below_threshold(self):
        from lc.agent import Agent
        agent = self._agent([])
        agent._history_warned = True
        # Simulate /clear: messages cleared
        agent.messages = []
        with patch("lc.agent.flush_stdin", lambda: None):
            with patch.object(Agent, "_call_model", return_value=("ok", [], {})):
                with patch("lc.agent.console.print"):
                    agent.chat("hi")
        assert agent._history_warned is False, "flag should reset under threshold"


# ─── #7: _find_tag_id rejects whitespace / single-char ───

class TestFindTagIdInputGuard:
    def test_rejects_whitespace(self, monkeypatch):
        from lc import codetop_api as ct
        # Even with a tag list that contains spaces, " " must not match
        monkeypatch.setattr(ct, "fetch_tags",
                            lambda: [{"id": 1, "name": "Hash Table"},
                                     {"id": 2, "name": "Array"}])
        assert ct._find_tag_id(" ") is None
        assert ct._find_tag_id("") is None
        assert ct._find_tag_id("a") is None  # 1 char too short

    def test_accepts_min_2_char(self, monkeypatch):
        from lc import codetop_api as ct
        monkeypatch.setattr(ct, "fetch_tags",
                            lambda: [{"id": 1, "name": "DP"}])
        assert ct._find_tag_id("dp") == 1


# ─── #8: shrinkage check writes the same content it measures ───

class TestShrinkageBytesConsistency:
    def test_update_user_memory_writes_stripped(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem = tmp_path / "user_memory.md"
        mem.write_text("# old\nshort", encoding="utf-8")
        monkeypatch.setattr(sa, "USER_MEMORY_PATH", mem)
        # sub-agent returns content with trailing whitespace
        proposed = "# new\n" + ("integrated content " * 30)
        monkeypatch.setattr(sa, "_sub_agent_call",
                            lambda *a, **kw: f"  \n{proposed}\n   ")

        result = json.loads(sa.tool_update_user_memory(
            hint="", client=MagicMock(), messages=[]
        ))
        on_disk = mem.read_text(encoding="utf-8")
        assert len(on_disk.encode("utf-8")) == result["after_bytes"], \
            "after_bytes must equal what's actually on disk"
        assert on_disk == proposed.strip(), "file content must equal stripped proposed"

    def test_analyze_and_memorize_writes_stripped(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa
        mem_file = tmp_path / "1.md"
        mem_file.write_text("short header", encoding="utf-8")
        monkeypatch.setattr(sa.db, "get_memory", lambda pid: {
            "problem_id": 1, "title": "X", "difficulty": "Easy",
            "tags": "dp", "memory_file": str(mem_file),
        })
        proposed = "## summary\n" + ("body line " * 30)
        monkeypatch.setattr(sa, "_sub_agent_call",
                            lambda *a, **kw: f"\n  {proposed}  \n")
        monkeypatch.setattr(sa, "workspace_root", lambda: tmp_path)

        result = json.loads(sa.tool_analyze_and_memorize(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        on_disk = mem_file.read_text(encoding="utf-8")
        assert len(on_disk.encode("utf-8")) == result["after_bytes"]
        assert on_disk == proposed.strip()


# ─── #10: read_solution returns JSON ───

class TestReadSolutionJsonReturn:
    def test_success_is_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_read_solution
        f = tmp_path / "dp" / "1_x.py"
        f.parent.mkdir()
        f.write_text("print('hi')\n", encoding="utf-8")

        out = json.loads(tool_read_solution(file_path=str(f)))
        assert out["status"] == "ok"
        assert "print('hi')" in out["content"]
        assert out["bytes"] == len("print('hi')\n".encode("utf-8"))

    def test_error_is_json(self):
        from lc.tool_impl.workspace import tool_read_solution
        out = json.loads(tool_read_solution())
        assert out["status"] == "error"


# ─── #11: web_search empty query returns JSON ───

class TestWebSearchJsonReturn:
    def test_empty_query_json(self):
        from lc.tool_impl.subagents import tool_web_search
        out = json.loads(tool_web_search(query=""))
        assert out["error"] is True


# ─── #12: check_problem flags missing memory file ───

class TestCheckProblemFileExists:
    def test_returns_memory_file_exists(self, tmp_path, monkeypatch):
        from lc.tool_impl import workspace as ws

        ghost = tmp_path / "ghost.md"  # not created
        monkeypatch.setattr(ws.db, "get_memory", lambda pid: {
            "title": "X", "difficulty": "Easy", "tags": "dp",
            "memory_file": str(ghost),
        })
        out = json.loads(ws.tool_check_problem(problem_id=1))
        assert out["has_memory"] is True
        assert out["memory_file_exists"] is False

    def test_present_file_flagged_true(self, tmp_path, monkeypatch):
        from lc.tool_impl import workspace as ws

        f = tmp_path / "1.md"
        f.write_text("# header", encoding="utf-8")
        monkeypatch.setattr(ws.db, "get_memory", lambda pid: {
            "title": "X", "difficulty": "Easy", "tags": "dp",
            "memory_file": str(f),
        })
        out = json.loads(ws.tool_check_problem(problem_id=1))
        assert out["memory_file_exists"] is True


# ─── #13: let_user_pick rejects entries without title ───

class TestLetUserPickTitleRequired:
    def test_skips_titleless_entries(self, monkeypatch):
        from lc.tool_impl import problems as p
        # If all entries lack title → format error
        out = json.loads(p.tool_let_user_pick(
            choices=[{"id": 1}, {"id": 2}]
        ))
        assert out.get("error") is True

    def test_keeps_only_titled_entries(self, monkeypatch):
        from lc.tool_impl import problems as p

        captured = {}

        def fake_arrow_select(formatted):
            captured["count"] = len(formatted)
            return formatted[0][1]
        monkeypatch.setattr(p, "arrow_select", fake_arrow_select)

        json.loads(p.tool_let_user_pick(choices=[
            {"id": 1, "title": "OK"},
            {"id": 2},  # dropped
            {"id": 3, "title": "  "},  # whitespace title dropped
            {"id": 4, "title": "Also OK"},
        ]))
        assert captured["count"] == 2


# ─── #15: classify_problem normalizes spaces / hyphens ───

class TestClassifyProblemNormalization:
    @pytest.mark.parametrize("ai_reply,expected", [
        ("two pointers", "two_pointers"),
        ("Two-Pointers", "two_pointers"),
        ("binary search algorithm", "binary_search"),
        ("dfs bfs", "dfs_bfs"),
        ("stack-queue", "stack_queue"),
        ("math bit manipulation", "math_bit"),
    ])
    def test_normalizes_to_underscore_form(self, ai_reply, expected):
        from lc.workspace import classify_problem
        from lc.models import Problem

        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=ai_reply))]
        )
        prob = Problem(id=1, title="x", title_slug="x",
                       difficulty="Easy", tags=["array"])
        assert classify_problem(prob, client) == expected


# ─── #16: cross_workspace_db_overwrite flag ───

class TestCrossWorkspaceFlag:
    def test_flag_set_when_memory_path_differs(self, tmp_path, monkeypatch):
        from lc import workspace as ws
        from lc.models import Problem

        store: dict = {1: {"problem_id": 1, "title": "X", "difficulty": "Easy",
                           "tags": "dp",
                           "memory_file": "/some/other/workspace/.memories/1_x.md"}}
        monkeypatch.setattr(ws.db, "get_memory", lambda pid: store.get(pid))
        monkeypatch.setattr(ws.db, "upsert_memory",
                            lambda pid, t, mf, **kw: store.__setitem__(pid, {
                                "memory_file": mf, "title": t,
                                "difficulty": kw.get("difficulty", ""),
                                "tags": kw.get("tags", "")}))
        monkeypatch.setattr("lc.leetcode_api.fetch_problem",
                            lambda pid: Problem(id=1, title="X",
                                                title_slug="x", difficulty="Easy",
                                                tags=["dp"], code_snippet=""))
        monkeypatch.setattr(ws, "classify_problem", lambda p, c: "dp")
        monkeypatch.chdir(tmp_path)

        result = ws.start_problem(1, MagicMock())
        assert isinstance(result, tuple)
        _, _, _, flags = result
        assert flags["cross_workspace_db_overwrite"] is True

    def test_flag_clear_for_same_workspace(self, tmp_path, monkeypatch):
        from lc import workspace as ws
        from lc.models import Problem

        store: dict = {}
        monkeypatch.setattr(ws.db, "get_memory", lambda pid: store.get(pid))
        monkeypatch.setattr(ws.db, "upsert_memory",
                            lambda pid, t, mf, **kw: store.__setitem__(pid, {
                                "memory_file": mf, "title": t,
                                "difficulty": kw.get("difficulty", ""),
                                "tags": kw.get("tags", "")}))
        monkeypatch.setattr("lc.leetcode_api.fetch_problem",
                            lambda pid: Problem(id=1, title="X",
                                                title_slug="x", difficulty="Easy",
                                                tags=["dp"], code_snippet=""))
        monkeypatch.setattr(ws, "classify_problem", lambda p, c: "dp")
        monkeypatch.chdir(tmp_path)

        # First call creates entry
        ws.start_problem(1, MagicMock())
        # Second call same workspace — no cross-workspace overwrite
        result = ws.start_problem(1, MagicMock())
        _, _, _, flags = result
        assert flags["cross_workspace_db_overwrite"] is False


# ─── #17: tag_resolved propagates through stats ───

class TestTagResolvedPropagation:
    def test_unresolved_tag_surfaced(self, monkeypatch):
        from lc import planner as pl
        # Force tag resolution to fail
        monkeypatch.setattr("lc.codetop_api._find_tag_id", lambda t: None)
        monkeypatch.setattr("lc.codetop_api.fetch_hot_problems",
                            lambda **kw: ([], 0))
        monkeypatch.setattr(pl.db, "get_practiced_problem_ids", lambda: set())

        candidates, stats = pl._pick_from_codetop(tag="obscure_tag", limit=5)
        assert stats["tag_requested"] == "obscure_tag"
        assert stats["tag_resolved"] is False

    def test_used_filters_includes_tag_resolved(self, monkeypatch):
        from lc.tool_impl import problems as p
        monkeypatch.setattr(
            "lc.planner._pick_from_codetop",
            lambda **kw: ([], {
                "scanned_count": 0, "filtered_practiced": 0,
                "filtered_difficulty": 0,
                "tag_requested": kw.get("tag"),
                "tag_resolved": False,
                "target_unmet": False,
            }),
        )
        monkeypatch.setattr("lc.cli.get_config", lambda k: None)
        out = json.loads(p.tool_list_hot_problems(tag="weird"))
        assert out["used_filters"]["tag_resolved"] is False


# ─── #18: single hallucination still surfaces dropped_hallucinations ───

class TestFindSimilarSingleHallucination:
    def test_single_hallucination_exposed(self, tmp_path, monkeypatch):
        from lc.tool_impl import subagents as sa

        valid = tmp_path / "200.md"
        valid.write_text("# 200\n\n## solution\nbfs\n", encoding="utf-8")

        # subagent returns 1 valid + 1 hallucinated id
        monkeypatch.setattr(sa, "_sub_agent_call",
                            lambda *a, **kw: "200\n9999")
        monkeypatch.setattr(sa, "_has_l3_content", lambda _: True)

        def get_memory(pid):
            if pid == 1:
                return {"problem_id": 1, "title": "Cur", "difficulty": "Easy",
                        "tags": "dp", "memory_file": str(tmp_path / "1.md")}
            if pid == 200:
                return {"problem_id": 200, "title": "Other",
                        "difficulty": "Easy", "tags": "dp",
                        "memory_file": str(valid)}
            return None
        monkeypatch.setattr(sa.db, "get_memory", get_memory)
        monkeypatch.setattr(sa.db, "get_all_memories", lambda: [
            {"problem_id": 200, "title": "Other", "difficulty": "Easy",
             "tags": "dp", "memory_file": str(valid)},
        ])

        result = json.loads(sa.tool_find_similar_problems(
            problem_id=1, client=MagicMock(), messages=[]
        ))
        # One hallucination → results kept but dropped_hallucinations exposed
        assert result.get("dropped_hallucinations") == 1
        assert len(result["similar_problems"]) == 1
        assert result["similar_problems"][0]["problem_id"] == 200


# ─── #19: fetch_problem retries with wider window ───

class TestFetchProblemRetries:
    def test_falls_back_to_wider_limit(self, monkeypatch):
        from lc import leetcode_api as la

        list_call_limits: list[int] = []

        def fake_graphql(query, variables, retries=2):
            # Detail query doesn't carry `limit` — distinguish by titleSlug
            if "titleSlug" in variables and "categorySlug" not in variables:
                return {"question": {
                    "questionId": "1", "questionFrontendId": "1",
                    "title": "Target", "titleSlug": "target", "content": "",
                    "difficulty": "Easy", "topicTags": [],
                    "hints": [], "similarQuestions": "[]",
                    "codeSnippets": [],
                }}
            # List query
            list_call_limits.append(variables["limit"])
            if variables["limit"] == 5:
                return {"problemsetQuestionList": {
                    "questions": [{"frontendQuestionId": "999",
                                   "title": "z", "titleSlug": "z",
                                   "difficulty": "Easy", "acRate": 0.5,
                                   "topicTags": []}],
                }}
            return {"problemsetQuestionList": {"questions": [
                {"frontendQuestionId": "999", "title": "z", "titleSlug": "z",
                 "difficulty": "Easy", "acRate": 0.5, "topicTags": []},
                {"frontendQuestionId": "1", "title": "Target",
                 "titleSlug": "target", "difficulty": "Easy",
                 "acRate": 0.5, "topicTags": []},
            ]}}
        monkeypatch.setattr(la, "_graphql", fake_graphql)

        prob = la.fetch_problem(1)
        assert prob.id == 1
        assert 5 in list_call_limits and 25 in list_call_limits


# ─── #20: codetop cache TTL ───

class TestCodetopCacheTTL:
    def test_cache_expires(self, monkeypatch):
        from lc import codetop_api as ct

        # Reset and set short TTL
        ct._companies_cache = None
        ct._companies_cache_time = 0.0
        monkeypatch.setattr(ct, "_CACHE_TTL_SECONDS", 0.01)

        call_count = [0]

        def fake_get(*a, **kw):
            call_count[0] += 1
            return [{"id": call_count[0], "name": f"Company{call_count[0]}"}]
        monkeypatch.setattr(ct, "_get", fake_get)

        ct.fetch_companies()
        first = call_count[0]
        import time
        time.sleep(0.02)  # exceed TTL
        ct.fetch_companies()
        assert call_count[0] > first, "cache should expire after TTL"


# ─── #21: _sanitize_messages cleans tool_calls.arguments ───

class TestSanitizeToolCallArgs:
    def test_surrogate_in_tool_args_cleaned(self):
        from lc.agent import Agent
        bad = "\udc80"  # lone surrogate
        msgs = [{"role": "assistant", "tool_calls": [{
            "id": "1", "type": "function",
            "function": {"name": "search_leetcode",
                         "arguments": '{"keyword": "ok ' + bad + '"}'},
        }]}]
        cleaned = Agent._sanitize_messages(msgs)
        # Re-encoding must not raise
        cleaned[0]["tool_calls"][0]["function"]["arguments"].encode("utf-8")


# ─── #22: target_unmet flag surfaces randomize shortfall ───

class TestTargetUnmetFlag:
    def test_target_unmet_when_randomize_short(self, monkeypatch):
        from lc import planner as pl
        from lc.codetop_api import CodetopProblem

        # Only 2 candidates available, but randomize wants 5*5=25
        monkeypatch.setattr("lc.codetop_api.fetch_hot_problems", lambda **kw: (
            [CodetopProblem(leetcode_id=1, title="A", title_slug="a",
                            difficulty="Easy", frequency=1)], 1,
        ))
        monkeypatch.setattr("lc.codetop_api._find_tag_id", lambda t: None)
        monkeypatch.setattr(pl.db, "get_practiced_problem_ids", lambda: set())

        _, stats = pl._pick_from_codetop(limit=5, randomize=True)
        assert stats["target_unmet"] is True

    def test_target_unmet_false_when_filled(self, monkeypatch):
        from lc import planner as pl
        from lc.codetop_api import CodetopProblem

        problems = [CodetopProblem(leetcode_id=i, title=f"P{i}",
                                   title_slug=f"p{i}",
                                   difficulty="Easy", frequency=1)
                    for i in range(50)]
        monkeypatch.setattr("lc.codetop_api.fetch_hot_problems", lambda **kw: (
            problems, 50,
        ))
        monkeypatch.setattr("lc.codetop_api._find_tag_id", lambda t: None)
        monkeypatch.setattr(pl.db, "get_practiced_problem_ids", lambda: set())

        _, stats = pl._pick_from_codetop(limit=5, randomize=True)
        assert stats["target_unmet"] is False


# ─── #23: find_problem_file surfaces all_files when multiple ───

class TestFindProblemFileMultiMatch:
    def test_multi_match_all_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_find_problem_file

        (tmp_path / "dp").mkdir()
        (tmp_path / "two_pointers").mkdir()
        (tmp_path / "dp" / "1_x.py").write_text("# a")
        (tmp_path / "two_pointers" / "1_x.py").write_text("# b")

        out = json.loads(tool_find_problem_file(problem_id=1))
        assert out["found"] is True
        assert out["total_matches"] == 2
        assert "all_files" in out
        assert len(out["all_files"]) == 2

    def test_single_match_no_all_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_find_problem_file

        (tmp_path / "dp").mkdir()
        (tmp_path / "dp" / "1_x.py").write_text("# a")

        out = json.loads(tool_find_problem_file(problem_id=1))
        assert out["total_matches"] == 1
        assert "all_files" not in out


# ─── #24: legacy mode="tag" migrated on app startup ───

class TestLegacyModeMigration:
    def test_migrate_persists(self, monkeypatch):
        from lc import cli
        store: dict[str, str] = {"cfg_mode": "tag"}
        monkeypatch.setattr(cli.db, "get_session", lambda k: store.get(k))
        monkeypatch.setattr(cli.db, "set_session",
                            lambda k, v: store.__setitem__(k, v))

        cli._migrate_legacy_config()
        assert store["cfg_mode"] == "default"

    def test_no_op_when_clean(self, monkeypatch):
        from lc import cli
        store: dict[str, str] = {"cfg_mode": "random"}
        monkeypatch.setattr(cli.db, "get_session", lambda k: store.get(k))
        monkeypatch.setattr(cli.db, "set_session",
                            lambda k, v: store.__setitem__(k, v))

        cli._migrate_legacy_config()
        assert store["cfg_mode"] == "random"


# ─── #27: append_solution rejects non-.py files ───

class TestAppendSolutionPySuffix:
    def test_rejects_md_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_append_solution

        f = tmp_path / "README.md"
        f.write_text("# readme\n", encoding="utf-8")

        out = json.loads(tool_append_solution(file_path=str(f), content="x"))
        assert out["status"] == "error"
        assert ".py" in out["message"]

    def test_accepts_py_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from lc.tool_impl.workspace import tool_append_solution

        f = tmp_path / "dp" / "1_x.py"
        f.parent.mkdir()
        f.write_text("# x\n", encoding="utf-8")

        out = json.loads(tool_append_solution(file_path=str(f),
                                              content="def y(): pass"))
        assert out["status"] == "appended"
