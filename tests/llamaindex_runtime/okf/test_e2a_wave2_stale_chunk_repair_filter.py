"""RED regression for Wave 2 stale-chunk filtering during tree repair."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    _delete_stale_chunks,
    _repair_stale_tree_nodes,
)

_VERSION_ID = str(UUID(int=1601))
_STALE_NODE_ID = str(UUID(int=1602))
_REPAIR_TARGET_NODE_ID = str(UUID(int=1603))
_RETAINED_CHUNK_ID = str(UUID(int=1604))
_STALE_CHUNK_ID = str(UUID(int=1605))
_DOCUMENT_ID = str(UUID(int=1))
_SPAN_ID = str(UUID(int=100))
_DIGEST = "a" * 64
_RELATIVE_PATH = "raw/guide.pair.json"


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


class _StaleChunkRepairCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.updated_chunk_ids: list[str] = []
        self.deleted_chunk_ids: list[str] = []
        self.chunk_nodes: dict[str, str | None] = {
            _RETAINED_CHUNK_ID: _STALE_NODE_ID,
            _STALE_CHUNK_ID: _STALE_NODE_ID,
        }

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))
        normalized = _normalized(statement)
        if normalized.startswith("update vector_chunks"):
            assert type(parameters) is tuple
            target_node_id, chunk_id, old_node_id = parameters
            assert self.chunk_nodes[chunk_id] == old_node_id
            self.chunk_nodes[chunk_id] = target_node_id
            self.updated_chunk_ids.append(chunk_id)
        elif normalized.startswith("delete from vector_chunks"):
            assert type(parameters) is tuple and len(parameters) == 1
            chunk_ids = parameters[0]
            assert type(chunk_ids) is list
            self.deleted_chunk_ids.extend(chunk_ids)

    def fetchall(self) -> list[Mapping[str, object]]:
        return []


def _desired() -> E2aDesiredState:
    parent = E2aParent(_DOCUMENT_ID, _VERSION_ID, _RELATIVE_PATH, _DIGEST)
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
            E2aSpan(_DOCUMENT_ID, _VERSION_ID, _SPAN_ID, 0, "Admitted text."),
        ),
        vector_chunks=(
            {
                "chunk_id": _RETAINED_CHUNK_ID,
                "version_id": _VERSION_ID,
                "chunk_type": "canonical_span",
                "chunk_order": 0,
                "token_count": 2,
                "text_preview": "Admitted text.",
                "page_no": 1,
                "heading_path": "Guide",
                "node_id": _REPAIR_TARGET_NODE_ID,
                "embedding": [0.0] * 16,
            },
        ),
        vector_chunk_span_links=(
            {"chunk_id": _RETAINED_CHUNK_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
        ),
        tree_nodes=(
            {
                "node_id": _REPAIR_TARGET_NODE_ID,
                "version_id": _VERSION_ID,
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
            {"node_id": _REPAIR_TARGET_NODE_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
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


def test_tree_repair_updates_only_chunks_retained_by_desired_state() -> None:
    cursor = _StaleChunkRepairCursor()
    desired = _desired()
    existing: dict[str, tuple[Mapping[str, object], ...]] = {
        "tree_nodes": (
            {
                "node_id": _STALE_NODE_ID,
                "version_id": _VERSION_ID,
                "parent_node_id": None,
            },
        ),
        "vector_chunks": tuple(
            {
                "chunk_id": chunk_id,
                "version_id": _VERSION_ID,
                "node_id": _STALE_NODE_ID,
            }
            for chunk_id in (_RETAINED_CHUNK_ID, _STALE_CHUNK_ID)
        ),
    }
    recorder = DmlRecorder()

    _repair_stale_tree_nodes(cursor, desired, existing, recorder, {})
    _delete_stale_chunks(cursor, desired, existing, recorder, {})

    stale_delete_index = next(
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if _normalized(statement).startswith("delete from vector_chunks")
    )
    stale_updates_before_delete = [
        parameters[1]
        for index, (statement, parameters) in enumerate(cursor.calls)
        if index < stale_delete_index
        and _normalized(statement).startswith("update vector_chunks")
        and type(parameters) is tuple
        and parameters[1] == _STALE_CHUNK_ID
    ]

    assert cursor.deleted_chunk_ids == [_STALE_CHUNK_ID]
    assert cursor.updated_chunk_ids == [_RETAINED_CHUNK_ID]
    assert stale_updates_before_delete == []
