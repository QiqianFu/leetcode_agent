"""Tests for the tool dispatcher (tools.execute_tool)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lc.tools import TOOLS, execute_tool


def _mock_client() -> MagicMock:
    return MagicMock()


class TestExecuteToolDispatch:
    def test_unknown_tool_returns_error(self):
        result = json.loads(execute_tool("nonexistent_tool", "{}", _mock_client()))
        assert result["error"] is True
        assert "nonexistent_tool" in result["message"]

    def test_malformed_json_returns_error(self):
        result = json.loads(execute_tool("check_problem", "{bad json", _mock_client()))
        assert result["error"] is True
        assert "JSON" in result["message"]

    def test_empty_arguments_string(self):
        """Empty string for arguments should not crash the dispatcher."""
        with patch("lc.tool_impl.workspace.db") as mock_db:
            mock_db.get_memory.return_value = None
            result = execute_tool("check_problem", "", _mock_client())
        # Should return an error about missing problem_id, not crash
        assert "problem_id" in result or "error" in result

    def test_all_tool_names_registered(self):
        """Every tool in TOOLS must have a registry entry."""
        from lc.tools import _TOOL_REGISTRY
        schema_names = {t["function"]["name"] for t in TOOLS}
        registry_names = set(_TOOL_REGISTRY.keys())
        assert schema_names == registry_names, (
            f"Mismatch: schema_only={schema_names - registry_names}, "
            f"registry_only={registry_names - schema_names}"
        )

    def test_needs_client_tools_receive_client(self):
        """Tools with needs_client=True should receive the client kwarg."""
        from lc.tools import _TOOL_REGISTRY
        client_tools = [name for name, (_, needs_client, _) in _TOOL_REGISTRY.items() if needs_client]
        assert "start_problem" in client_tools
        assert "update_user_memory" in client_tools
        assert "find_similar_problems" in client_tools
        assert "analyze_and_memorize" in client_tools

    def test_needs_messages_implies_needs_client(self):
        """Sub-agent tools that need messages must also need client."""
        from lc.tools import _TOOL_REGISTRY
        for name, (_, needs_client, needs_messages) in _TOOL_REGISTRY.items():
            if needs_messages:
                assert needs_client, f"{name}: needs_messages=True but needs_client=False"

    def test_tool_exception_returns_structured_error(self):
        """If a tool handler raises, execute_tool returns a JSON error, not a crash."""
        with patch("lc.tool_impl.workspace.db") as mock_db:
            mock_db.get_memory.side_effect = RuntimeError("db exploded")
            result = json.loads(execute_tool("check_problem", '{"problem_id": 1}', _mock_client()))
        assert result["error"] is True
        assert result["error_type"] == "RuntimeError"
        assert "db exploded" in result["message"]


class TestToolDefs:
    def test_tools_list_is_nonempty(self):
        assert len(TOOLS) > 0

    def test_each_tool_has_required_fields(self):
        for tool in TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"

    def test_no_duplicate_tool_names(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names found"
