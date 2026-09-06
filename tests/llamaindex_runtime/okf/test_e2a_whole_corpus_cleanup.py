"""Regression coverage for empty whole-corpus E2a reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=501))
_VERSION_ID = str(UUID(int=502))
_SPAN_ID = str(UUID(int=503))
_CHUNK_ID = str(UUID(int=504))
_NODE_ID = str(UUID(int=505))
_ENTITY_ID = str(UUID(int=506))
_EVIDENCE_ID = str(UUID(int=507))
_OWNERSHIP_ID = str(UUID(int=508))


def _empty_desired() -> E2aDesiredState:
    manifest = {"schema": "e2a-corpus-v1", "artifacts": []}
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(),
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
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


class _HistoricalWholeCorpusCursor:
    """Expose one retired E2a scope and no parentless legacy material."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = _normalized(self._last_statement)
        if "for update" in statement:
            return self._locked_rows(statement)
        if "select exists" in statement:
            return [{"present": False}]
        if "select evidence_link_id" in statement:
            return []
        if statement.startswith(
            "select version_id, materialization_owner from okf_sync_state"
        ):
            return [{"version_id": _VERSION_ID, "materialization_owner": "e2a"}]
        if "from canonical_spans where version_id = any(%s)" in statement:
            return [{"span_id": _SPAN_ID}]
        if "from vector_chunks where version_id = any(%s)" in statement:
            return [
                {
                    "chunk_id": _CHUNK_ID,
                    "version_id": _VERSION_ID,
                    "node_id": _NODE_ID,
                }
            ]
        if "from tree_nodes where version_id = any(%s)" in statement:
            return [
                {
                    "node_id": _NODE_ID,
                    "version_id": _VERSION_ID,
                    "parent_node_id": None,
                }
            ]
        if "from evidence inner join okf_manual_evidence_targets" in statement:
            return [{"evidence_id": _EVIDENCE_ID}]
        if (
            "from okf_manual_fact_ownership" in statement
            and "where version_id = any(%s)" in statement
        ):
            return [
                {
                    "ownership_id": _OWNERSHIP_ID,
                    "fact_kind": "entity",
                    "fact_id": _ENTITY_ID,
                }
            ]
        if (
            "from okf_manual_fact_ownership" in statement
            and "version_id is null" in statement
        ):
            return []
        if "from okf_sync_state where version_id = any(%s)" in statement:
            return [
                {
                    "okf_file_path": "raw/retired.pair.json",
                    "doc_id": _DOCUMENT_ID,
                    "version_id": _VERSION_ID,
                    "source_checksum": _DIGEST,
                    "canonical_hash": _DIGEST,
                    "status": "materialized",
                    "materialization_owner": "e2a",
                }
            ]
        return []

    @staticmethod
    def _locked_rows(statement: str) -> list[Mapping[str, object]]:
        fields = (
            ("canonical_spans", "span_id", _SPAN_ID),
            ("vector_chunks", "chunk_id", _CHUNK_ID),
            ("tree_nodes", "node_id", _NODE_ID),
            ("evidence", "evidence_id", _EVIDENCE_ID),
            ("entities", "entity_id", _ENTITY_ID),
        )
        for table, field, identifier in fields:
            if f"from {table}" in statement:
                return [{field: identifier}]
        raise AssertionError(f"unexpected locked relation: {statement}")


def test_empty_whole_corpus_discovers_and_purges_retired_e2a_scope() -> None:
    cursor = _HistoricalWholeCorpusCursor()

    result = E2aMaterializationRepository().reconcile(
        cursor, _empty_desired(), recorder=DmlRecorder()
    )

    assert result.outcome == "changed"
    assert result.stale_deletion_counts == {
        "canonical_spans": 1,
        "evidence": 1,
        "okf_manual_fact_ownership": 1,
        "okf_sync_state": 1,
        "tree_nodes": 1,
        "vector_chunks": 1,
    }
    executed = [statement for statement, _ in cursor.calls]
    assert any(
        statement.startswith("DELETE FROM canonical_spans") for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM vector_chunks") for statement in executed
    )
    assert any(statement.startswith("DELETE FROM tree_nodes") for statement in executed)
    assert any(statement.startswith("DELETE FROM evidence") for statement in executed)
    assert any(
        statement.startswith("DELETE FROM okf_manual_fact_ownership")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM okf_sync_state") for statement in executed
    )
    assert any("version_id is null" in statement.lower() for statement in executed)
