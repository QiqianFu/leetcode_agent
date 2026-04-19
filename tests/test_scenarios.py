"""Integration scenarios covering end-to-end ReAct flows with scripted LLM responses.

Each scenario simulates a user request + a predetermined sequence of model outputs,
then verifies the correct tools are called in the correct order with correct args.
These tests exercise the post-2026-04-18 atomic-tool architecture.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class _ScriptedLLM:
    """Returns a predetermined sequence of (content, tool_calls) pairs."""

    def __init__(self, script):
        self.script = list(script)

    def __call__(self, messages):
        if not self.script:
            return ("done", [], {})
        content, tool_calls = self.script.pop(0)
        out = []
        for i, (name, args) in enumerate(tool_calls):
            out.append({
                "id": f"call_{i}",
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            })
        return (content, out, {})


@pytest.fixture
def run_agent():
    """Fixture: returns a function that runs Agent.chat with a scripted LLM.

    Returns (log, agent) — `log` is a list of (tool_name, parsed_args) tuples.
    """
    from lc.agent import Agent
    from lc import tools as tools_mod

    def _run(script, user_input, tool_mocks=None):
        tool_mocks = tool_mocks or {}
        log = []
        llm = _ScriptedLLM(script)

        agent = Agent.__new__(Agent)
        agent.client = MagicMock()
        agent.messages = []
        agent._call_model = llm

        real_execute = tools_mod.execute_tool

        def logging_execute(name, args, client, messages=None):
            parsed = json.loads(args) if args else {}
            log.append((name, parsed))
            if name in tool_mocks:
                result = tool_mocks[name](parsed)
                return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            return real_execute(name, args, client, messages)

        with patch("lc.agent.flush_stdin", lambda: None), \
             patch("lc.agent.execute_tool", logging_execute):
            agent.chat(user_input)

        return log, agent

    return _run


# ─── Scenarios ───

class TestDPRecommendation:
    """User says '给我来道 DP 题', model should query → CoT → recommend."""

    def test_list_then_start(self, run_agent):
        script = [
            ("查候选", [("list_hot_problems", {"tag": "dp", "difficulty": "Medium", "limit": 8})]),
            ("选 416", [("start_problem", {"problem_id": 416})]),
            ("已开始 #416", []),
        ]
        mocks = {
            "list_hot_problems": lambda a: {
                "problems": [
                    {"id": 300, "title": "LIS", "difficulty": "Medium"},
                    {"id": 416, "title": "Partition Equal Subset Sum", "difficulty": "Medium"},
                    {"id": 494, "title": "Target Sum", "difficulty": "Medium"},
                ],
                "used_filters": {"tag": "dp", "difficulty": "Medium"},
            },
            "start_problem": lambda a: {"status": "started", "problem_id": a["problem_id"]},
        }
        log, _ = run_agent(script, "给我来道 DP 题", mocks)
        assert [n for n, _ in log] == ["list_hot_problems", "start_problem"]
        assert log[0][1]["tag"] == "dp"
        assert log[1][1]["problem_id"] == 416


class TestPracticeHistory:
    """User asks '我做过几道 DP 题？', model should list_practiced + inspect samples."""

    def test_list_and_sample_memories(self, run_agent):
        script = [
            ("查已做", [("list_practiced", {"tag": "dp", "limit": 50})]),
            ("抽样读两个 memory", [
                ("read_memory", {"problem_id": 70}),
                ("read_memory", {"problem_id": 322}),
            ]),
            ("做过 5 道 DP 题，简单已掌握，中等还在巩固。", []),
        ]
        mocks = {
            "list_practiced": lambda a: {
                "total_matched": 5, "returned": 5,
                "problems": [
                    {"problem_id": 70, "title": "Climbing Stairs", "difficulty": "Easy", "tags": "dp"},
                    {"problem_id": 322, "title": "Coin Change", "difficulty": "Medium", "tags": "dp"},
                ],
            },
            "read_memory": lambda a: f"# {a['problem_id']}\n## 解题思路\n经典 DP",
        }
        log, _ = run_agent(script, "我做过几道 DP 题？", mocks)
        assert log[0][0] == "list_practiced"
        assert log[1][0] == "read_memory" and log[2][0] == "read_memory"


class TestPreviewWithoutStart:
    """User says '416 是啥？先别开始' — check local, display only, no commit."""

    def test_check_then_display(self, run_agent):
        script = [
            ("先查本地", [("check_problem", {"problem_id": 416})]),
            ("用 display_problem 展示", [("display_problem", {"problem_id": 416})]),
            ("已在终端展示", []),
        ]
        mocks = {
            "check_problem": lambda a: {"problem_id": 416, "has_memory": False},
            "display_problem": lambda a: {"status": "displayed", "problem_id": 416},
        }
        log, _ = run_agent(script, "416 是啥？先别开始", mocks)
        assert [n for n, _ in log] == ["check_problem", "display_problem"]
        assert "start_problem" not in [n for n, _ in log]


class TestCustomSimilarity:
    """find_similar_problems with custom criteria must inject into sub-agent task."""

    def test_criteria_propagates(self, run_agent, monkeypatch):
        captured = {}

        def fake_sub_agent_call(client, messages, task, max_tokens=2048):
            captured["task"] = task
            return "673\n1143"

        monkeypatch.setattr("lc.tool_impl.subagents._sub_agent_call", fake_sub_agent_call)
        monkeypatch.setattr("lc.tool_impl.subagents._has_l3_content", lambda _: True)

        def fake_get_memory(pid):
            return {"problem_id": pid, "title": "LIS", "difficulty": "Medium",
                    "tags": "dp", "memory_file": "/tmp/x.md"}
        monkeypatch.setattr("lc.tool_impl.subagents.db.get_memory", fake_get_memory)
        monkeypatch.setattr("lc.tool_impl.subagents.db.get_all_memories", lambda: [
            {"problem_id": 673, "title": "Number of LIS", "difficulty": "Medium",
             "tags": "dp", "memory_file": "/tmp/673.md"},
        ])

        class _FakePath:
            def __init__(self, _): pass
            def read_text(self, encoding="utf-8"): return "memo"
            def exists(self): return True
        monkeypatch.setattr("lc.tool_impl.subagents.Path", _FakePath)

        script = [
            ("用自定义 criteria", [("find_similar_problems", {
                "problem_id": 300, "max_results": 5,
                "criteria": "相同一维 DP 状态设计，但使用不同数据结构",
            })]),
            ("找到了", []),
        ]
        log, _ = run_agent(script, "找类似 300 但数据结构不同的", {})
        assert log[0][0] == "find_similar_problems"
        assert log[0][1]["max_results"] == 5
        assert "相同一维 DP 状态设计" in captured["task"]


class TestUserMemoryHint:
    """update_user_memory with hint must propagate into sub-agent task."""

    def test_hint_propagates(self, run_agent, monkeypatch, tmp_path):
        mem_path = tmp_path / "user_memory.md"
        captured = {}

        def fake_sub_agent_call(client, messages, task, max_tokens=2048):
            captured["task"] = task
            return "# 用户偏好\n- 直接给思路"

        monkeypatch.setattr("lc.tool_impl.subagents._sub_agent_call", fake_sub_agent_call)
        monkeypatch.setattr("lc.tool_impl.subagents.USER_MEMORY_PATH", mem_path)

        hint_text = "用户偏好从提示变成直接思路"
        script = [
            ("记录偏好", [("update_user_memory", {"hint": hint_text})]),
            ("已更新", []),
        ]
        log, _ = run_agent(script, "我不要提示了", {})
        assert log[0][0] == "update_user_memory"
        assert hint_text in captured["task"]
        assert mem_path.read_text(encoding="utf-8").startswith("# 用户偏好")


class TestParallelWriteMemory:
    """write_memory is no longer in _SERIAL_TOOLS; two calls in same turn work."""

    def test_two_write_memory_same_turn(self, run_agent):
        script = [
            ("同时写两个", [
                ("write_memory", {"problem_id": 70, "content": "note 1"}),
                ("write_memory", {"problem_id": 322, "content": "note 2"}),
            ]),
            ("done", []),
        ]
        mocks = {"write_memory": lambda a: f"已写入 #{a['problem_id']}"}
        log, _ = run_agent(script, "给 70 和 322 各加笔记", mocks)
        assert len(log) == 2
        assert {a["problem_id"] for _, a in log} == {70, 322}

    def test_write_memory_not_in_serial_set(self):
        import inspect
        from lc.agent import Agent
        src = inspect.getsource(Agent.chat)
        serial_block = src.split("_SERIAL_TOOLS = {")[1].split("}")[0]
        assert "write_memory" not in serial_block


class TestListPracticedDifficultyCase:
    """Difficulty filter must be case-insensitive (model may pass 'easy' vs 'Easy')."""

    def test_lowercase_difficulty(self, monkeypatch):
        from lc.tool_impl import problems as problems_mod
        monkeypatch.setattr(problems_mod.db, "get_all_memories", lambda: [
            {"problem_id": 70, "title": "Climbing", "difficulty": "Easy",
             "tags": "dp", "memory_file": "x"},
            {"problem_id": 1,  "title": "Two Sum", "difficulty": "Medium",
             "tags": "hash", "memory_file": "x"},
        ])
        for variant in ("easy", "EASY", "Easy", "easY"):
            r = json.loads(problems_mod.tool_list_practiced(difficulty=variant))
            assert r["total_matched"] == 1, f"case variant {variant!r} failed"
            assert r["problems"][0]["problem_id"] == 70


class TestPickFromCodetopDifficultyCase:
    """_pick_from_codetop must accept mixed-case difficulty values."""

    def test_lowercase_difficulty(self, monkeypatch):
        from lc import planner as planner_mod
        from lc.codetop_api import CodetopProblem
        monkeypatch.setattr(planner_mod.db, "get_practiced_problem_ids", lambda: set())
        monkeypatch.setattr("lc.codetop_api.fetch_hot_problems", lambda **_: (
            [CodetopProblem(leetcode_id=70, title="X", title_slug="x",
                            difficulty="Easy", frequency=100)], 1,
        ))
        monkeypatch.setattr("lc.codetop_api._find_tag_id", lambda _: None)
        for variant in ("easy", "EASY", "Easy"):
            r = planner_mod._pick_from_codetop(difficulty=variant, limit=5)
            assert len(r) == 1, f"case variant {variant!r} failed"


class TestReactLoopRollback:
    """Mid-loop API failure must roll back messages to avoid orphaned tool_calls."""

    def test_rollback_on_api_failure_after_tool_call(self, monkeypatch):
        from lc.agent import Agent
        from openai import APIConnectionError
        import httpx

        call_count = [0]
        def flaky_call(msgs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ("", [{"id": "c1", "name": "check_problem",
                              "arguments": '{"problem_id": 70}'}], {})
            raise APIConnectionError(request=httpx.Request("POST", "http://x"))

        agent = Agent.__new__(Agent)
        agent.client = MagicMock()
        agent.messages = [{"role": "user", "content": "previous"},
                          {"role": "assistant", "content": "previous reply"}]
        pre = list(agent.messages)
        agent._call_model = flaky_call

        with patch("lc.agent.flush_stdin", lambda: None), \
             patch("lc.agent.execute_tool", return_value="{}"):
            agent.chat("hi")

        assert agent.messages == pre, \
            f"expected rollback to pre-turn state, got {agent.messages}"

    def test_no_orphan_tool_calls_after_failure(self, monkeypatch):
        """Stronger: explicit check that no assistant.tool_calls is left without tool responses."""
        from lc.agent import Agent
        from openai import APIConnectionError
        import httpx

        call_count = [0]
        def flaky_call(msgs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ("", [{"id": "c1", "name": "check_problem",
                              "arguments": '{"problem_id": 70}'}], {})
            raise APIConnectionError(request=httpx.Request("POST", "http://x"))

        agent = Agent.__new__(Agent)
        agent.client = MagicMock()
        agent.messages = []
        agent._call_model = flaky_call

        with patch("lc.agent.flush_stdin", lambda: None), \
             patch("lc.agent.execute_tool", return_value="{}"):
            agent.chat("hi")

        for i, m in enumerate(agent.messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                expected_ids = {tc["id"] for tc in m["tool_calls"]}
                actual_ids = {
                    n.get("tool_call_id")
                    for n in agent.messages[i + 1:i + 1 + len(expected_ids)]
                    if n.get("role") == "tool"
                }
                assert expected_ids == actual_ids, \
                    f"orphaned tool_calls at [{i}]: expected {expected_ids}, got {actual_ids}"


class TestListPracticedTagAliases:
    """list_practiced must resolve short-form tag aliases (dp → dynamic programming)."""

    def test_dp_alias_matches_official_tag(self, monkeypatch):
        from lc.tool_impl import problems as problems_mod

        monkeypatch.setattr(problems_mod.db, "get_all_memories", lambda: [
            {"problem_id": 70, "title": "Climbing Stairs", "difficulty": "Easy",
             "tags": "Math, Dynamic Programming, Memoization", "memory_file": "x"},
            {"problem_id": 1,  "title": "Two Sum", "difficulty": "Easy",
             "tags": "Array, Hash Table", "memory_file": "x"},
            {"problem_id": 322, "title": "Coin Change", "difficulty": "Medium",
             "tags": "Array, Dynamic Programming, Breadth-First Search", "memory_file": "x"},
        ])

        result = json.loads(problems_mod.tool_list_practiced(tag="dp"))
        ids = {p["problem_id"] for p in result["problems"]}
        assert ids == {70, 322}, f"expected DP problems via 'dp' alias, got {ids}"

    def test_bfs_alias_matches_breadth_first_search(self, monkeypatch):
        from lc.tool_impl import problems as problems_mod

        monkeypatch.setattr(problems_mod.db, "get_all_memories", lambda: [
            {"problem_id": 102, "title": "Level Order", "difficulty": "Medium",
             "tags": "Tree, Breadth-First Search", "memory_file": "x"},
            {"problem_id": 1, "title": "Two Sum", "difficulty": "Easy",
             "tags": "Array, Hash Table", "memory_file": "x"},
        ])
        result = json.loads(problems_mod.tool_list_practiced(tag="bfs"))
        ids = {p["problem_id"] for p in result["problems"]}
        assert ids == {102}

    def test_unknown_tag_falls_back_to_literal_substring(self, monkeypatch):
        from lc.tool_impl import problems as problems_mod

        monkeypatch.setattr(problems_mod.db, "get_all_memories", lambda: [
            {"problem_id": 1, "title": "Two Sum", "difficulty": "Easy",
             "tags": "Array, Hash Table", "memory_file": "x"},
        ])
        # "hash table" IS in _TAG_EN_TO_ZH → expands (still matches "Hash Table" substring)
        result = json.loads(problems_mod.tool_list_practiced(tag="hash table"))
        assert len(result["problems"]) == 1

    def test_chinese_tag_reverse_lookup(self, monkeypatch):
        from lc.tool_impl import problems as problems_mod
        monkeypatch.setattr(problems_mod.db, "get_all_memories", lambda: [
            {"problem_id": 70, "title": "X", "difficulty": "Easy",
             "tags": "Dynamic Programming", "memory_file": "x"},
        ])
        # User / model passes Chinese — should reverse-lookup to English synonyms
        result = json.loads(problems_mod.tool_list_practiced(tag="动态规划"))
        assert result["total_matched"] == 1

    def test_empty_tag_input_safe(self):
        """expand_tag_synonyms('') must return [] so callers don't accidentally match all."""
        from lc.codetop_api import expand_tag_synonyms
        assert expand_tag_synonyms("") == []
        assert expand_tag_synonyms("   ") == []
        assert expand_tag_synonyms(None) == []  # defensive

    def test_case_insensitive_english_input(self):
        from lc.codetop_api import expand_tag_synonyms
        for v in ("dp", "DP", "Dp", "dP"):
            assert set(expand_tag_synonyms(v)) == {"dp", "dynamic programming"}


class TestComplexChain:
    """'找和 322 类似但更难的题' — 5-tool chain across 4 turns."""

    def test_full_chain(self, run_agent):
        script = [
            ("读旧记忆 + 查已做", [
                ("read_memory", {"problem_id": 322}),
                ("list_practiced", {"tag": "dp", "difficulty": "Hard"}),
            ]),
            ("搜相关题", [("search_leetcode", {"keyword": "unbounded knapsack", "limit": 5})]),
            ("让用户挑", [("let_user_pick", {
                "choices": [
                    {"id": 879, "title": "Profitable Schemes", "difficulty": "Hard"},
                    {"id": 1449, "title": "Largest Number", "difficulty": "Hard"},
                ],
                "prompt": "选一道：",
            })]),
            ("开题", [("start_problem", {"problem_id": 879})]),
            ("已开始", []),
        ]
        mocks = {
            "read_memory": lambda a: "# 322\n完全背包",
            "list_practiced": lambda a: {"total_matched": 0, "problems": []},
            "search_leetcode": lambda a: {"problems": [
                {"id": 879, "title": "Profitable Schemes", "difficulty": "Hard"},
            ]},
            "let_user_pick": lambda a: {"status": "selected", "selected_id": 879},
            "start_problem": lambda a: {"status": "started", "problem_id": 879},
        }
        log, _ = run_agent(script, "找类似 322 但更难的", mocks)
        expected = ["read_memory", "list_practiced", "search_leetcode", "let_user_pick", "start_problem"]
        assert [n for n, _ in log] == expected
