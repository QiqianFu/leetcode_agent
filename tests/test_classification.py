"""Tests for workspace classification logic."""
from __future__ import annotations

import pytest

from lc.workspace import pick_category_heuristic
from lc.models import CATEGORIES


class TestPickCategoryHeuristic:
    def test_returns_valid_category(self):
        for tags in [["array"], ["dynamic programming"], ["tree"], ["graph"], ["unknown_xyz"]]:
            result = pick_category_heuristic(tags)
            assert result in CATEGORIES, f"Got invalid category {result!r} for tags {tags}"

    def test_array_maps_to_known_category(self):
        # array should map to something sensible (two_pointers or similar), not an error
        result = pick_category_heuristic(["array"])
        assert result in CATEGORIES

    def test_dp_tag_maps_to_dp(self):
        result = pick_category_heuristic(["dynamic programming"])
        assert result == "dp"

    def test_tree_tag_maps_to_tree(self):
        result = pick_category_heuristic(["binary tree"])
        assert result == "tree"

    def test_graph_tag_maps_to_graph(self):
        result = pick_category_heuristic(["graph"])
        assert result == "graph"

    def test_unknown_tag_falls_back_to_design(self):
        result = pick_category_heuristic(["completely_unknown_tag_xyz"])
        assert result == "design"

    def test_empty_tags_returns_design(self):
        result = pick_category_heuristic([])
        assert result == "design"

    def test_binary_search_tag(self):
        result = pick_category_heuristic(["binary search"])
        assert result == "binary_search"

    def test_stack_tag(self):
        result = pick_category_heuristic(["stack"])
        assert result == "stack_queue"

    def test_string_tag(self):
        result = pick_category_heuristic(["string"])
        assert result == "string"

    def test_first_matching_tag_wins(self):
        """When multiple tags match different categories, a result is still returned."""
        result = pick_category_heuristic(["tree", "dynamic programming"])
        assert result in CATEGORIES


class TestCategories:
    def test_categories_is_nonempty_list(self):
        assert isinstance(CATEGORIES, list)
        assert len(CATEGORIES) == 12

    def test_expected_categories_present(self):
        expected = {"dp", "greedy", "binary_search", "two_pointers", "dfs_bfs",
                    "sorting", "stack_queue", "tree", "graph", "design", "math_bit", "string"}
        assert set(CATEGORIES) == expected
