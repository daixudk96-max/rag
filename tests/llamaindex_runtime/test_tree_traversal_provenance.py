from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SemanticDistributionRegistry,
)


class TestTraversalProvenanceIntegrity:
    def test_traversal_uses_chunk_specific_span_ids(self) -> None:
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        node_id = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_id, "span_id": span_b, "ordinal_no": 1},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": node_id, "embedding": [1.0, 1.0]},
            {"chunk_id": chunk_b, "node_id": node_id, "embedding": [1.0, 1.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id

        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert len(hits) == 2
        hits_by_chunk = {hit.chunk_id: hit for hit in hits}
        assert hits_by_chunk[chunk_a].span_id == span_a
        assert hits_by_chunk[chunk_b].span_id == span_b

    def test_traversal_uses_real_doc_id_from_registry(self) -> None:
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        node_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        span_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": node_id, "embedding": [1.0, 1.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_doc_id_by_version.return_value = doc_id

        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert len(hits) == 1
        assert hits[0].doc_id == doc_id
        assert hits[0].version_id == version_id
        assert hits[0].span_id == span_id
        assert hits[0].chunk_id == chunk_id
        assert hits[0].node_id == node_id

    def test_traversal_skips_chunks_without_span_provenance(self) -> None:
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        node_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": node_id, "embedding": [1.0, 1.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []
        registry.query_doc_id_by_version.return_value = doc_id

        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert hits == []
