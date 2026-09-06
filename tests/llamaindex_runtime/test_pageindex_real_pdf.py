"""Test PageIndexTreeAdapter.index_tree() forbidden-authoring boundary.

Phase 15: Verify PageIndexTreeAdapter.index_tree() raises the static
FORBIDDEN RuntimeError unconditionally — before reading source_path and
before any registry interaction. The test deliberately does NOT require a
real PDF fixture, because index_tree() never reads its input. Path-based
skipif gates are therefore both unnecessary and cwd-dependent, so they
have been removed in favor of a deterministic, non-skipped test.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest


class TestPageIndexIndexTreeForbiddenBoundary:
    """Verify index_tree() enforces the static FORBIDDEN boundary.

    The boundary is unconditional: index_tree() raises before reading
    source_path and before invoking any registry method. Tests use a
    plain path string (no fixture, no tmp_path write) because the path
    is never read.
    """

    def test_index_tree_raises_forbidden_for_any_path(
        self,
    ) -> None:
        """index_tree() must raise FORBIDDEN RuntimeError for any source_path.

        Verifies that the static consumer-only boundary fires before
        any path I/O or registry interaction, regardless of the path
        value. No real PDF is required, and no path is read.
        """
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()
        registry = MagicMock()
        version_id = uuid.uuid4()

        # Plain path string — value is irrelevant; index_tree() never reads it.
        source_path = "any/path/that/is/never/read.pdf"

        # MUST raise FORBIDDEN RuntimeError immediately
        with pytest.raises(RuntimeError) as exc_info:
            adapter.index_tree(
                source_path=source_path,
                version_id=version_id,
                registry=registry,
            )

        # Verify error message contains FORBIDDEN
        error_msg = str(exc_info.value)
        assert "FORBIDDEN" in error_msg
        assert "cannot author canonical" in error_msg.lower()

        # Verify registry.write_tree was NEVER called
        registry.write_tree.assert_not_called()

    def test_index_tree_zero_registry_interactions(
        self,
    ) -> None:
        """index_tree() must result in zero relevant registry writer calls.

        Ensures the forbidden boundary fires before any tree parsing or
        registry side effect, preventing any write/query interaction
        with the registry.
        """
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()
        registry = MagicMock()
        version_id = uuid.uuid4()

        source_path = "any/path/that/is/never/read.pdf"

        # Attempt index_tree (must fail with FORBIDDEN)
        with pytest.raises(RuntimeError):
            adapter.index_tree(
                source_path=source_path,
                version_id=version_id,
                registry=registry,
            )

        # Verify NO relevant registry methods were called (complete isolation)
        registry.write_tree.assert_not_called()
        registry.query_tree_nodes_by_version.assert_not_called()
        registry.query_tree_node_spans_by_version.assert_not_called()
        registry.query_vector_chunk_spans_by_version.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
