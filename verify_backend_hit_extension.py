"""Verification script for Task 2.4: BackendHit protocol extension.

Tests verify:
1. Frozen contract preserved (existing fields unchanged)
2. Backward compatibility (new fields optional)
3. Provenance metadata functional (backend_source, retrieval_path)
"""
from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError

from llamaindex_runtime.tree.backend_adapter import BackendHit


def test_frozen_contract_preserved():
    """Test BackendHit frozen=True preserved (immutable)."""
    print("=== Frozen Contract Verification ===\n")

    hit = BackendHit(
        score=0.95,
        text_preview="Test content",
        heading_path="Introduction",
        page_no=1,
        span_ids=[uuid.uuid4()],
        node_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        entity_id=None,
        relation_id=None,
    )

    # Verify frozen=True (immutability)
    try:
        hit.score = 0.99  # Should raise FrozenInstanceError
        print("[FAIL] BackendHit is NOT frozen (contract violation)")
        return False
    except FrozenInstanceError:
        print("[OK] BackendHit frozen=True preserved (immutable contract)")

    return True


def test_backward_compatibility():
    """Test backward compatibility: existing code works without new fields."""
    print("\n=== Backward Compatibility Verification ===\n")

    # Create BackendHit without provenance fields (Phase 1 style)
    hit_old_style = BackendHit(
        score=0.85,
        text_preview="Legacy hit",
        heading_path="Background",
        page_no=5,
        span_ids=[],
        node_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        entity_id=None,
        relation_id=None,
    )

    # Verify defaults
    assert hit_old_style.backend_source is None, "backend_source should default to None"
    assert hit_old_style.retrieval_path is None, "retrieval_path should default to None"

    print("[OK] Backward compatibility: existing code works")
    print(f"  - backend_source (default): {hit_old_style.backend_source}")
    print(f"  - retrieval_path (default): {hit_old_style.retrieval_path}")

    return True


def test_provenance_metadata():
    """Test provenance metadata extension functional."""
    print("\n=== Provenance Metadata Verification ===\n")

    # Create BackendHit with provenance fields (Phase 2 style)
    hit_new_style = BackendHit(
        score=0.90,
        text_preview="Enhanced hit",
        heading_path="Methods",
        page_no=12,
        span_ids=[uuid.uuid4()],
        node_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        entity_id=None,
        relation_id=None,
        backend_source="tree",  # Phase 2 extension
        retrieval_path="reasoning",  # Phase 2 extension
    )

    # Verify provenance fields populated
    assert hit_new_style.backend_source == "tree", "backend_source should be 'tree'"
    assert hit_new_style.retrieval_path == "reasoning", "retrieval_path should be 'reasoning'"

    print("[OK] Provenance metadata functional")
    print(f"  - backend_source: {hit_new_style.backend_source}")
    print(f"  - retrieval_path: {hit_new_style.retrieval_path}")

    return True


def test_all_backend_sources():
    """Test all backend_source values accepted."""
    print("\n=== Backend Source Validation ===\n")

    valid_sources = ["tree", "graph", "vector", "reasoning"]

    for source in valid_sources:
        hit = BackendHit(
            score=None,
            text_preview=f"{source} backend hit",
            heading_path=None,
            page_no=None,
            span_ids=[],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
            backend_source=source,
            retrieval_path=None,
        )
        assert hit.backend_source == source, f"backend_source should accept '{source}'"
        print(f"[OK] backend_source '{source}' accepted")

    return True


if __name__ == "__main__":
    results = []
    results.append(test_frozen_contract_preserved())
    results.append(test_backward_compatibility())
    results.append(test_provenance_metadata())
    results.append(test_all_backend_sources())

    if all(results):
        print("\n=== All GREEN verifications passed ===")
        print("Task 2.4 complete: BackendHit protocol extended (frozen contract preserved)")
    else:
        print("\n=== Some verifications FAILED ===")
        exit(1)