"""RED regression for Wave 2 sync-path ownership PostgreSQL array binding."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from llamaindex_runtime.okf._e2a_sync_state_operations import (
    ensure_sync_path_ownership,
)
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    canonical_json_sha256,
)

_DOCUMENT_ID = str(UUID(int=1))
_ALPHA_VERSION_ID = str(UUID(int=2))
_ZETA_VERSION_ID = str(UUID(int=3))
_DIGEST = "a" * 64
_ALPHA_PATH = "raw/alpha.pair.json"
_ZETA_PATH = "raw/zeta.pair.json"


class _OwnershipCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def fetchone(self) -> Mapping[str, object] | None:
        raise AssertionError("ensure_sync_path_ownership must not call fetchone")


def _desired() -> E2aDesiredState:
    alpha_parent = E2aParent(_DOCUMENT_ID, _ALPHA_VERSION_ID, _ALPHA_PATH, _DIGEST)
    zeta_parent = E2aParent(_DOCUMENT_ID, _ZETA_VERSION_ID, _ZETA_PATH, _DIGEST)
    parents = (alpha_parent, zeta_parent)
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
            for parent in parents
        ],
    }
    sync_state_rows = (
        {
            "okf_file_path": _ALPHA_PATH,
            "doc_id": _DOCUMENT_ID,
            "version_id": _ALPHA_VERSION_ID,
            "source_checksum": "b" * 64,
            "canonical_hash": _DIGEST,
            "status": "materialized",
            "materialization_owner": "e2a",
        },
        {
            "okf_file_path": _ZETA_PATH,
            "doc_id": _DOCUMENT_ID,
            "version_id": _ZETA_VERSION_ID,
            "source_checksum": "b" * 64,
            "canonical_hash": _DIGEST,
            "status": "materialized",
            "materialization_owner": "e2a",
        },
    )
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=parents,
        canonical_spans=(),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=sync_state_rows,
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def test_ensure_sync_path_ownership_binds_every_sql_array_as_a_list() -> None:
    cursor = _OwnershipCursor()
    desired = _desired()

    ensure_sync_path_ownership(cursor, desired)

    array_bindings = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if "any(%s)" in statement.lower()
    ]

    assert array_bindings
    assert all(
        type(parameters) is tuple
        and len(parameters) == 1
        and type(parameters[0]) is list
        for _, parameters in array_bindings
    )
    assert array_bindings == [
        (
            "SELECT okf_file_path, materialization_owner FROM okf_sync_state "
            "WHERE okf_file_path = ANY(%s)",
            (["raw/alpha.pair.json", "raw/zeta.pair.json"],),
        )
    ]
