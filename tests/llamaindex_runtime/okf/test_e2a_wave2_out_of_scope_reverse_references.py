"""RED contracts for Wave 2 out-of-scope reverse-reference closure guards.

These tests use cursor fakes only. They neither open a database connection nor permit
DML to reach a cursor unless the required fail-closed dependency probe has run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aParent,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=1601))
_VERSION_ID = str(UUID(int=1602))
_STALE_SPAN_ID = str(UUID(int=1603))
_STALE_NODE_ID = str(UUID(int=1605))


@dataclass(frozen=True)
class _ReverseReferenceCase:
    identifier: str
    inventory_table: str
    stale_id: str
    permitted_owner_ids: tuple[str, ...]
    probe_marker: str
    probe_statement: str
    error_message: str

    @property
    def probe_parameters(self) -> tuple[list[str], list[str]]:
        return ([self.stale_id], list(self.permitted_owner_ids))


_CASES = (
    _ReverseReferenceCase(
        identifier="stale span vector chunk span owner outside closure",
        inventory_table="canonical_spans",
        stale_id=_STALE_SPAN_ID,
        permitted_owner_ids=(),
        probe_marker="from vector_chunk_spans where span_id = any",
        probe_statement=(
            "SELECT EXISTS (SELECT 1 FROM vector_chunk_spans WHERE span_id = ANY(%s) "
            "AND chunk_id <> ALL(%s)) AS present"
        ),
        error_message="stale span has out-of-scope vector chunk span dependencies",
    ),
    _ReverseReferenceCase(
        identifier="stale span tree node span owner outside closure",
        inventory_table="canonical_spans",
        stale_id=_STALE_SPAN_ID,
        permitted_owner_ids=(),
        probe_marker="from tree_node_spans where span_id = any",
        probe_statement=(
            "SELECT EXISTS (SELECT 1 FROM tree_node_spans WHERE span_id = ANY(%s) "
            "AND node_id <> ALL(%s)) AS present"
        ),
        error_message="stale span has out-of-scope tree node span dependencies",
    ),
    _ReverseReferenceCase(
        identifier="stale node vector chunk owner outside closure",
        inventory_table="tree_nodes",
        stale_id=_STALE_NODE_ID,
        permitted_owner_ids=(),
        probe_marker="from vector_chunks where node_id = any",
        probe_statement=(
            "SELECT EXISTS (SELECT 1 FROM vector_chunks WHERE node_id = ANY(%s) "
            "AND chunk_id <> ALL(%s)) AS present"
        ),
        error_message="stale tree has out-of-scope vector chunk dependencies",
    ),
    _ReverseReferenceCase(
        identifier="stale node child tree node outside closure",
        inventory_table="tree_nodes",
        stale_id=_STALE_NODE_ID,
        permitted_owner_ids=(_STALE_NODE_ID,),
        probe_marker="from tree_nodes where parent_node_id = any",
        probe_statement=(
            "SELECT EXISTS (SELECT 1 FROM tree_nodes WHERE parent_node_id = ANY(%s) "
            "AND node_id <> ALL(%s)) AS present"
        ),
        error_message="stale tree has out-of-scope child tree node dependencies",
    ),
)


def _desired() -> E2aDesiredState:
    parent = E2aParent(
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        relative_path="raw/out-of-scope.pair.json",
        canonical_hash=_DIGEST,
    )
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


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


class _OutOfScopeReverseReferenceCursor:
    """Returns an external reverse reference only for the required exact probe."""

    def __init__(self, case: _ReverseReferenceCase) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.probe_calls: list[tuple[str, object | None]] = []
        self.probe_results: list[Mapping[str, object]] = []
        self._case = case
        self._last_statement = ""
        self._last_was_required_probe = False

    def execute(self, statement: str, parameters: object | None = None) -> None:
        normalized = _normalized(statement)
        if _is_dml(statement):
            assert self.probe_calls, (
                "required out-of-scope reverse-reference probe must reject before "
                f"any DML; attempted: {statement}"
            )
        self._last_was_required_probe = False
        if self._case.probe_marker in normalized:
            assert normalized == _normalized(self._case.probe_statement)
            assert parameters == self._case.probe_parameters
            self.probe_calls.append((statement, parameters))
            self._last_was_required_probe = True
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = _normalized(self._last_statement)
        if self._last_was_required_probe:
            result: Mapping[str, object] = {"present": True}
            self.probe_results.append(result)
            return [result]
        if "for update" in statement:
            return [self._lock_row()]
        if self._is_stale_inventory(statement):
            return [self._inventory_row()]
        if "select exists" in statement:
            return [{"present": False}]
        return []

    def _is_stale_inventory(self, statement: str) -> bool:
        return (
            f"from {self._case.inventory_table}" in statement
            and "where version_id = any(%s)" in statement
        )

    def _inventory_row(self) -> Mapping[str, object]:
        if self._case.inventory_table == "canonical_spans":
            return {"span_id": self._case.stale_id}
        if self._case.inventory_table == "vector_chunks":
            return {
                "chunk_id": self._case.stale_id,
                "version_id": _VERSION_ID,
                "node_id": None,
            }
        if self._case.inventory_table == "tree_nodes":
            return {
                "node_id": self._case.stale_id,
                "version_id": _VERSION_ID,
                "parent_node_id": None,
            }
        raise AssertionError(
            f"unexpected inventory table: {self._case.inventory_table}"
        )

    def _lock_row(self) -> Mapping[str, object]:
        if self._case.inventory_table == "canonical_spans":
            return {"span_id": self._case.stale_id}
        if self._case.inventory_table == "vector_chunks":
            return {"chunk_id": self._case.stale_id}
        if self._case.inventory_table == "tree_nodes":
            return {"node_id": self._case.stale_id}
        raise AssertionError(f"unexpected lock table: {self._case.inventory_table}")


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.identifier)
def test_reconcile_rejects_out_of_scope_reverse_references_before_any_dml(
    case: _ReverseReferenceCase,
) -> None:
    cursor = _OutOfScopeReverseReferenceCursor(case)
    recorder = DmlRecorder()

    with pytest.raises(ValueError, match=case.error_message):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(),
            recorder=recorder,
        )

    assert [
        (_normalized(statement), parameters)
        for statement, parameters in cursor.probe_calls
    ] == [(_normalized(case.probe_statement), case.probe_parameters)]
    assert cursor.probe_results == [{"present": True}]
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert recorder.primary_dml_by_table == {}
