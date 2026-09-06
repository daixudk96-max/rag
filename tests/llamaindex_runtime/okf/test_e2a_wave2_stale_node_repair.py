"""Regression coverage for Wave 2 stale-node compare-and-set repair."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    _cache_rows_for_stale_nodes,
    _delete_stale_tree_nodes,
    _repair_stale_tree_nodes,
)

_PARENT_VERSION_ID = str(UUID(int=2))
_STALE_NODE_ID = str(UUID(int=62))
_RETAINED_STALE_CHUNK_ID = str(UUID(int=71))
_RETAINED_MOVED_CHUNK_ID = str(UUID(int=72))
_DESIRED_NODE_ID = str(UUID(int=73))
_DOCUMENT_ID = str(UUID(int=1))
_SPAN_ID_1 = str(UUID(int=100))
_SPAN_ID_2 = str(UUID(int=101))
_DIGEST = "a" * 64
_RELATIVE_PATH = "raw/guide.pair.json"


def _normalized(statement: str) -> str:
    return " ".join(statement.split()).lower()


def _parameter_identifiers(parameters: object | None) -> tuple[str, ...]:
    identifiers: list[str] = []

    def collect(value: object | None) -> None:
        if isinstance(value, (tuple, list)):
            for item in value:
                collect(item)
        elif type(value) is str:
            identifiers.append(value)

    collect(parameters)
    return tuple(identifiers)


class _StaleNodeRepairCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.chunk_nodes: dict[str, str | None] = {
            _RETAINED_STALE_CHUNK_ID: _STALE_NODE_ID,
            _RETAINED_MOVED_CHUNK_ID: _DESIRED_NODE_ID,
        }
        self.updated_chunk_ids: list[str] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))
        normalized = _normalized(statement)
        if normalized.startswith("update vector_chunks"):
            self._apply_repair(statement, parameters)
        elif normalized.startswith("delete from tree_nodes"):
            self._delete_tree_nodes(parameters)

    def fetchall(self) -> list[Mapping[str, object]]:
        return []

    def _apply_repair(self, statement: str, parameters: object | None) -> None:
        assert type(parameters) is tuple
        target, chunk_id, old_node = parameters
        current_node = self.chunk_nodes[chunk_id]
        normalized = _normalized(statement)
        if "node_id is not distinct from %s" in normalized:
            matches_old_node = current_node == old_node
        elif "node_id is distinct from %s" in normalized:
            matches_old_node = current_node != old_node
        else:
            raise AssertionError("repair must compare against its stale snapshot")
        if matches_old_node:
            self.chunk_nodes[chunk_id] = target
            self.updated_chunk_ids.append(chunk_id)

    def _delete_tree_nodes(self, parameters: object | None) -> None:
        for node_id in _parameter_identifiers(parameters):
            for chunk_id, current_node in self.chunk_nodes.items():
                if current_node == node_id:
                    self.chunk_nodes[chunk_id] = None


def _desired() -> E2aDesiredState:
    parent = E2aParent(_DOCUMENT_ID, _PARENT_VERSION_ID, _RELATIVE_PATH, _DIGEST)
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=(
            E2aSpan(
                _DOCUMENT_ID, _PARENT_VERSION_ID, _SPAN_ID_1, 0, "Admitted text one."
            ),
            E2aSpan(
                _DOCUMENT_ID, _PARENT_VERSION_ID, _SPAN_ID_2, 1, "Admitted text two."
            ),
        ),
        vector_chunks=(
            {
                "chunk_id": _RETAINED_STALE_CHUNK_ID,
                "version_id": _PARENT_VERSION_ID,
                "chunk_type": "canonical_span",
                "chunk_order": 0,
                "token_count": 2,
                "text_preview": "Admitted text one.",
                "page_no": 1,
                "heading_path": "Guide",
                "node_id": _DESIRED_NODE_ID,
                "embedding": [0.0] * 16,
            },
            {
                "chunk_id": _RETAINED_MOVED_CHUNK_ID,
                "version_id": _PARENT_VERSION_ID,
                "chunk_type": "canonical_span",
                "chunk_order": 1,
                "token_count": 2,
                "text_preview": "Admitted text two.",
                "page_no": 1,
                "heading_path": "Guide",
                "node_id": _DESIRED_NODE_ID,
                "embedding": [0.0] * 16,
            },
        ),
        vector_chunk_span_links=(
            {
                "chunk_id": _RETAINED_STALE_CHUNK_ID,
                "span_id": _SPAN_ID_1,
                "ordinal_no": 0,
            },
            {
                "chunk_id": _RETAINED_MOVED_CHUNK_ID,
                "span_id": _SPAN_ID_2,
                "ordinal_no": 0,
            },
        ),
        tree_nodes=(
            {
                "node_id": _DESIRED_NODE_ID,
                "version_id": _PARENT_VERSION_ID,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Guide",
                "heading_path": "Guide",
                "page_start": None,
                "page_end": None,
                "summary_text": None,
            },
        ),
        tree_node_span_links=(
            {"node_id": _DESIRED_NODE_ID, "span_id": _SPAN_ID_1, "ordinal_no": 0},
            {"node_id": _DESIRED_NODE_ID, "span_id": _SPAN_ID_2, "ordinal_no": 1},
        ),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def test_stale_node_repair_compare_and_set_preserves_retained_chunk_nodes() -> None:
    cursor = _StaleNodeRepairCursor()
    desired = _desired()
    existing: dict[str, tuple[Mapping[str, object], ...]] = {
        "tree_nodes": (
            {
                "node_id": _STALE_NODE_ID,
                "version_id": _PARENT_VERSION_ID,
                "parent_node_id": None,
            },
        ),
        "vector_chunks": tuple(
            {
                "chunk_id": chunk_id,
                "version_id": _PARENT_VERSION_ID,
                "node_id": _STALE_NODE_ID,
            }
            for chunk_id in (_RETAINED_STALE_CHUNK_ID, _RETAINED_MOVED_CHUNK_ID)
        ),
    }
    recorder = DmlRecorder()
    cache_counts: dict[str, int] = {}
    stale_counts: dict[str, int] = {}

    stale_node_ids = _repair_stale_tree_nodes(
        cursor,
        desired,
        existing,
        recorder,
        cache_counts,
    )
    _delete_stale_tree_nodes(cursor, stale_node_ids, recorder, stale_counts)

    assert stale_node_ids == (_STALE_NODE_ID,)
    assert cursor.chunk_nodes == {
        _RETAINED_STALE_CHUNK_ID: _DESIRED_NODE_ID,
        _RETAINED_MOVED_CHUNK_ID: _DESIRED_NODE_ID,
    }
    assert cursor.updated_chunk_ids == [_RETAINED_STALE_CHUNK_ID]
    repair_statement = next(
        statement
        for statement, _ in cursor.calls
        if _normalized(statement).startswith("update vector_chunks")
    )
    assert "and node_id is not distinct from %s" in _normalized(repair_statement)


def test_cache_measurement_rejects_raw_table_text_before_cursor_activity() -> None:
    cursor = _StaleNodeRepairCursor()

    with pytest.raises(ValueError, match="cache measurement"):
        _cache_rows_for_stale_nodes(
            cursor,
            "summaries WHERE true; DELETE FROM relations",  # type: ignore[arg-type]
            (_STALE_NODE_ID,),
        )

    assert cursor.calls == []
