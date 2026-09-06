from __future__ import annotations

import math
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    TreeBranchDecisionPolicy,
    TreeSemanticDistributionAdapter,
)


class TestTreeSemanticDistributionAdapter:
    def test_adapter_emits_per_node_semantic_stats(self) -> None:
        version_id = uuid.uuid4()
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        span_a1 = uuid.uuid4()
        span_a2 = uuid.uuid4()
        span_b1 = uuid.uuid4()
        chunk_a1 = uuid.uuid4()
        chunk_a2 = uuid.uuid4()
        chunk_b1 = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_a, "heading_path": "Chapter 1", "level_no": 0},
            {"node_id": node_b, "heading_path": "Chapter 2", "level_no": 0},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a, "span_id": span_a1, "ordinal_no": 0},
            {"node_id": node_a, "span_id": span_a2, "ordinal_no": 1},
            {"node_id": node_b, "span_id": span_b1, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a1, "node_id": node_a, "embedding": [1.0, 2.0]},
            {"chunk_id": chunk_a2, "node_id": node_a, "embedding": [3.0, 4.0]},
            {"chunk_id": chunk_b1, "node_id": node_b, "embedding": [10.0, 0.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a1, "span_id": span_a1, "ordinal_no": 0},
            {"chunk_id": chunk_a2, "span_id": span_a2, "ordinal_no": 0},
            {"chunk_id": chunk_b1, "span_id": span_b1, "ordinal_no": 0},
        ]

        result = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )

        assert result["tree_signals"]["node_count"] == 2
        assert result["tree_signals"]["analyzed_node_count"] == 2

        node_stats = result["node_stats"]
        assert len(node_stats) == 2

        first = node_stats[0]
        assert first["node_id"] == node_a
        assert first["span_ids"] == [span_a1, span_a2]
        assert first["chunk_ids"] == [chunk_a1, chunk_a2]
        assert first["centroid"] == pytest.approx([2.0, 3.0])
        assert first["dispersion"] == pytest.approx(math.sqrt(2.0))
        assert first["entropy"] == pytest.approx(1.0)
        assert first["support_count"] == 2

        second = node_stats[1]
        assert second["node_id"] == node_b
        assert second["span_ids"] == [span_b1]
        assert second["chunk_ids"] == [chunk_b1]
        assert second["centroid"] == pytest.approx([10.0, 0.0])
        assert second["dispersion"] == pytest.approx(0.0)
        assert second["entropy"] == pytest.approx(0.0)
        assert second["support_count"] == 1

    def test_adapter_maps_chunk_via_span_when_node_id_missing(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "heading_path": "Chapter 1", "level_no": 0},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": None, "embedding": [2.0, 2.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        result = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )

        assert len(result["node_stats"]) == 1
        assert result["node_stats"][0]["node_id"] == node_id
        assert result["node_stats"][0]["chunk_ids"] == [chunk_id]
        assert result["node_stats"][0]["support_count"] == 1

    def test_adapter_limit_truncates_output(self) -> None:
        version_id = uuid.uuid4()
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_a, "heading_path": "Chapter 1", "level_no": 0},
            {"node_id": node_b, "heading_path": "Chapter 2", "level_no": 0},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": node_a, "embedding": [1.0, 1.0]},
            {"chunk_id": chunk_b, "node_id": node_b, "embedding": [2.0, 2.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]

        result = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
            limit=1,
        )

        assert [item["node_id"] for item in result["node_stats"]] == [node_a]
        assert result["tree_signals"]["analyzed_node_count"] == 1

    def test_empty_string_embedding_is_skipped(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "heading_path": "Chapter 1", "level_no": 0},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": node_id, "embedding": "[]"},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        result = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )

        assert result["node_stats"] == []
        assert result["tree_signals"]["analyzed_node_count"] == 0
        assert result["tree_signals"]["skipped_chunk_count"] == 1

    def test_dimension_mismatch_raises_value_error(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "heading_path": "Chapter 1", "level_no": 0},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_id, "span_id": span_b, "ordinal_no": 1},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": node_id, "embedding": [1.0, 2.0]},
            {"chunk_id": chunk_b, "node_id": node_id, "embedding": [3.0, 4.0, 5.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]

        with pytest.raises(ValueError, match="same dimension"):
            PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
                version_id=version_id,
                registry=registry,
            )


class TestTreeSemanticDistributionSeams:
    def test_adapter_implements_distribution_protocol(self) -> None:
        adapter = PersistedTreeSemanticDistributionAdapter()
        assert isinstance(adapter, TreeSemanticDistributionAdapter)

    def test_branch_decision_policy_protocol_supports_duck_typing(self) -> None:
        class DummyPolicy:
            def decide_branch_action(
                self,
                *,
                node_stats: dict[str, Any],
                tree_signals: dict[str, Any],
            ) -> str:
                return "keep_parent"

        assert isinstance(DummyPolicy(), TreeBranchDecisionPolicy)


class TestBaselineTreeBranchDecisionPolicy:
    def test_high_dispersion_and_high_entropy_drills_down(self) -> None:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        node_stats = {
            "node_id": uuid.uuid4(),
            "dispersion": 1.5,
            "entropy": 0.7,
            "support_count": 10,
        }
        tree_signals = {
            "node_count": 20,
            "analyzed_node_count": 15,
        }

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        assert decision == "drill_down"

    def test_low_dispersion_and_low_entropy_keeps_parent(self) -> None:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        node_stats = {
            "node_id": uuid.uuid4(),
            "dispersion": 0.5,
            "entropy": 0.3,
            "support_count": 10,
        }
        tree_signals = {
            "node_count": 20,
            "analyzed_node_count": 15,
        }

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        assert decision == "keep_parent"

    def test_high_dispersion_but_low_entropy_prunes(self) -> None:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        node_stats = {
            "node_id": uuid.uuid4(),
            "dispersion": 1.5,
            "entropy": 0.3,
            "support_count": 10,
        }
        tree_signals = {
            "node_count": 20,
            "analyzed_node_count": 15,
        }

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        assert decision == "prune"

    def test_low_support_count_prunes_even_if_concentrated(self) -> None:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
            min_support_threshold=5,
        )
        node_stats = {
            "node_id": uuid.uuid4(),
            "dispersion": 0.5,
            "entropy": 0.3,
            "support_count": 3,
        }
        tree_signals = {
            "node_count": 20,
            "analyzed_node_count": 15,
        }

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        assert decision == "prune"

    def test_policy_implements_branch_decision_protocol(self) -> None:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        assert isinstance(policy, TreeBranchDecisionPolicy)
