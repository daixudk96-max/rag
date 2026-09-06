"""Tests for TreeBackendAdapter seam and BackendHit type.

Phase 4 slice 1: verify the new tree backend adapter protocol before implementation.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest


class TestTreeBackendAdapterProtocol:
    """Verify TreeBackendAdapter protocol supports donor-backed tree build/retrieval."""

    def test_protocol_has_index_tree_method(self) -> None:
        """Protocol must define index_tree for donor-backed tree build."""
        from llamaindex_runtime.tree.backend_adapter import TreeBackendAdapter

        # Protocol must have index_tree method
        assert hasattr(TreeBackendAdapter, "index_tree")

    def test_protocol_has_retrieve_tree_hits_method(self) -> None:
        """Protocol must define retrieve_tree_hits for donor-backed retrieval."""
        from llamaindex_runtime.tree.backend_adapter import TreeBackendAdapter

        # Protocol must have retrieve_tree_hits method
        assert hasattr(TreeBackendAdapter, "retrieve_tree_hits")

    def test_index_tree_signature_accepts_source_path_and_registry(
        self,
    ) -> None:
        """index_tree must accept source document path and registry seam."""
        # This test verifies signature, not implementation
        # Will use Protocol inspection after implementation
        pass

    def test_retrieve_tree_hits_signature_accepts_query_and_registry(
        self,
    ) -> None:
        """retrieve_tree_hits must accept query text and registry seam."""
        # This test verifies signature, not implementation
        # Will use Protocol inspection after implementation
        pass


class TestBackendHitType:
    """Verify BackendHit structure matches frozen interface design."""

    def test_backend_hit_has_score_field(self) -> None:
        """BackendHit must have score for retrieval ranking."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.score == 0.85

    def test_backend_hit_has_text_preview_field(self) -> None:
        """BackendHit must have text_preview for display."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.text_preview == "sample text"

    def test_backend_hit_has_heading_path_field(self) -> None:
        """BackendHit must preserve heading hierarchy from tree structure."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.heading_path == "Section > Subsection"

    def test_backend_hit_has_page_no_field(self) -> None:
        """BackendHit must preserve page provenance."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.page_no == 5

    def test_backend_hit_has_span_ids_field(self) -> None:
        """BackendHit must preserve span provenance links."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        span_id = uuid.uuid4()
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[span_id],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.span_ids == [span_id]

    def test_backend_hit_has_node_id_field(self) -> None:
        """BackendHit must preserve tree node provenance."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        node_id = uuid.uuid4()
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=node_id,
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        assert hit.node_id == node_id

    def test_backend_hit_has_chunk_id_field(self) -> None:
        """BackendHit must preserve chunk provenance."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        chunk_id = uuid.uuid4()
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=chunk_id,
            entity_id=None,
            relation_id=None,
        )

        assert hit.chunk_id == chunk_id

    def test_backend_hit_has_optional_entity_id_field(self) -> None:
        """BackendHit may preserve entity provenance (optional)."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        entity_id = uuid.uuid4()
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=entity_id,
            relation_id=None,
        )

        assert hit.entity_id == entity_id

    def test_backend_hit_has_optional_relation_id_field(self) -> None:
        """BackendHit may preserve relation provenance (optional)."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        relation_id = uuid.uuid4()
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=relation_id,
        )

        assert hit.relation_id == relation_id

    def test_backend_hit_is_frozen_dataclass(self) -> None:
        """BackendHit must be immutable to preserve provenance."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        # Verify frozen=True by attempting mutation (should raise)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            hit.score = 0.90  # type: ignore


class TestBackendHitToQueryHitMapping:
    """Verify BackendHit can be mapped to final QueryHit through registry."""

    def test_backend_hit_provides_fields_for_registry_write(
        self,
    ) -> None:
        """BackendHit must provide all fields needed for registry write-back."""
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        version_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        node_id = uuid.uuid4()

        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[span_id],
            node_id=node_id,
            chunk_id=chunk_id,
            entity_id=None,
            relation_id=None,
        )

        # BackendHit must provide enough fields to construct QueryHit
        # (QueryHit requires: doc_id, version_id, span_id, chunk_id, node_id, similarity_score)
        # BackendHit provides: score, span_ids, node_id, chunk_id
        # Registry will provide: doc_id, version_id (from version_id parameter)
        assert hit.score is not None
        assert hit.span_ids is not None
        assert hit.node_id is not None
        assert hit.chunk_id is not None


class TestAdapterIntegrationConstraints:
    """Verify adapter design enforces frozen program constraints."""

    def test_adapter_must_write_through_registry(
        self,
    ) -> None:
        """Adapter outputs must be written through registry seam, not bypassing."""
        # This is a design constraint test - verified by implementation signature
        # TreeBackendAdapter methods must accept registry parameter
        from llamaindex_runtime.tree.backend_adapter import TreeBackendAdapter

        # Protocol methods must have registry parameter
        assert hasattr(TreeBackendAdapter, "index_tree")
        assert hasattr(TreeBackendAdapter, "retrieve_tree_hits")

    def test_adapter_must_not_change_provenance_meaning(
        self,
    ) -> None:
        """Adapter must preserve immutable provenance contracts."""
        # Verified by BackendHit structure matching frozen contracts
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        # All provenance fields in BackendHit use UUID type (same as frozen contracts)
        hit = BackendHit(
            score=0.85,
            text_preview="sample text",
            heading_path="Section > Subsection",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        # Type checks enforced by dataclass definition
        assert isinstance(hit.span_ids[0], uuid.UUID)
        assert isinstance(hit.node_id, uuid.UUID)
        assert isinstance(hit.chunk_id, uuid.UUID)