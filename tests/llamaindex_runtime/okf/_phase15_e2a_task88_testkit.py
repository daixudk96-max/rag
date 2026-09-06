"""Shared narrow recording doubles and desired-state builders for Task #88.

Shared exclusively by the Task #88 non-live unit modules:

- ``test_phase15_e2a_task88_cells_contracts`` (cells helper contracts),
- ``test_phase15_e2a_task88_reconciler_transactions`` (reconciler
  transaction boundaries),
- ``test_phase15_e2a_task88_preflight_guards`` (preflight and DmlRecorder
  pins).

The doubles are narrowly typed recording stand-ins for psycopg cursors
and connections, the repository boundary, and the desired-state builder;
they are used ONLY in non-live unit contracts and never produce
acceptance evidence. No database, no Docker, and no live selector is
exercised here, and no prohibited historical module is imported.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType, ModuleType
from uuid import UUID

from llamaindex_runtime.okf.e2a_contracts import (
    _E2A_DENYLIST_TABLES,
    _E2A_PRIMARY_TABLES,
    E2aDesiredState,
    E2aEvidenceObject,
    E2aEvidenceReference,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aReconciliationResult,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aMaterializationInput

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=201))
_VERSION_ID = str(UUID(int=202))
_OTHER_VERSION_ID = str(UUID(int=203))
_SPAN_ID = str(UUID(int=204))
_CHUNK_ID = str(UUID(int=205))
_NODE_ID = str(UUID(int=206))
_OTHER_ENTITY_ID = str(UUID(int=207))


def _identifier(number: int) -> str:
    return str(UUID(int=number))


def _desired_empty() -> E2aDesiredState:
    parent = E2aParent(
        document_id=_identifier(1),
        version_id=_identifier(101),
        relative_path="raw/one.pair.json",
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


def _desired_full() -> E2aDesiredState:
    """Valid desired state covering every global primary-key table."""
    parent = E2aParent(
        _DOCUMENT_ID,
        _VERSION_ID,
        "raw/global-guard.pair.json",
        _DIGEST,
    )
    span = E2aSpan(_DOCUMENT_ID, _VERSION_ID, _SPAN_ID, 0, "Global key guard.")
    natural_key = canonical_json({"entity_type": "concept", "title": "Guarded"})
    entity = E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        "entities/guarded.md",
        _DIGEST,
        natural_key=natural_key,
    )
    owner = E2aOwnershipFact.create(
        relative_path=entity.relative_path,
        fact_kind="entity",
        fact_id=entity.fact_id,
        source_digest=entity.source_digest,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
    )
    evidence = E2aEvidenceObject.create(
        version_id=_VERSION_ID,
        entity_id=entity.fact_id,
        relation_id=None,
    )
    evidence_link = E2aEvidenceReference(
        _DOCUMENT_ID,
        _VERSION_ID,
        _SPAN_ID,
        entity.fact_id,
        None,
        evidence.evidence_id,
        owner.ownership_id,
        owner.scope_version_id,
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{_DOCUMENT_ID}:{_VERSION_ID}",
                "canonical_hash": _DIGEST,
            },
            {
                "kind": "entity",
                "path": entity.relative_path,
                "identity": entity.fact_id,
                "source_digest": _DIGEST,
            },
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=(span,),
        vector_chunks=(
            {
                "chunk_id": _CHUNK_ID,
                "version_id": _VERSION_ID,
                "chunk_type": "canonical_span",
                "chunk_order": 0,
                "token_count": 3,
                "text_preview": span.text,
                "page_no": 1,
                "heading_path": "Guard",
                "node_id": _NODE_ID,
                "embedding": tuple(float(index) for index in range(16)),
            },
        ),
        vector_chunk_span_links=(
            {"chunk_id": _CHUNK_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
        ),
        tree_nodes=(
            {
                "node_id": _NODE_ID,
                "version_id": _VERSION_ID,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Guard",
                "heading_path": "Guard",
                "page_start": 1,
                "page_end": 1,
                "summary_text": "Guarded node.",
            },
        ),
        tree_node_span_links=(
            {"node_id": _NODE_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
        ),
        manual_entities=(entity,),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(evidence,),
        evidence_links=(evidence_link,),
        ownership_facts=(owner,),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _no_op_result(state: E2aDesiredState) -> E2aReconciliationResult:
    """Production-shaped no-op result: full canonical key sets on count maps."""
    return E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={table: 0 for table in sorted(_E2A_PRIMARY_TABLES)},
        denylist_dml_counts={table: 0 for table in sorted(_E2A_DENYLIST_TABLES)},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )


def _matching_parent_rows(state: E2aDesiredState) -> list[Mapping[str, object]]:
    parent = state.parents[0]
    return [{"doc_id": parent.document_id, "version_id": parent.version_id}]


def _materialization_input(state: E2aDesiredState) -> E2aMaterializationInput:
    return E2aMaterializationInput(
        admitted=state,
        span_records=(),
        parent_source_checksums={state.parents[0].version_id: _DIGEST},
    )


def _is_dml(statement: str) -> bool:
    return (
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "MERGE"))
    )


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _references_exact_table(statement: str, *, keyword: str, table: str) -> bool:
    normalized = _normalized(statement)
    pattern = rf"\b{re.escape(keyword)}\s+{re.escape(table)}\b"
    return re.search(pattern, normalized) is not None


_GLOBAL_ROWS = (
    ("canonical_spans", "span_id"),
    ("vector_chunks", "chunk_id"),
    ("tree_nodes", "node_id"),
    ("evidence", "evidence_id"),
    ("evidence_links", "evidence_link_id"),
)


def _identifier_for(desired: E2aDesiredState, table: str) -> str:
    if table == "canonical_spans":
        return desired.canonical_spans[0].span_id
    if table == "vector_chunks":
        return str(desired.vector_chunks[0]["chunk_id"])
    if table == "tree_nodes":
        return str(desired.tree_nodes[0]["node_id"])
    if table == "evidence":
        return desired.evidence_objects[0].evidence_id
    if table == "evidence_links":
        return desired.evidence_links[0].evidence_link_id
    raise AssertionError(f"unsupported global table: {table}")


class _AdapterRegistry:
    def __init__(self) -> None:
        self.loaders: list[tuple[str, object]] = []

    def register_loader(self, name: str, loader: object) -> None:
        self.loaders.append((name, loader))


class _Cursor:
    """Narrow recording cursor routing fetchall by statement table."""

    def __init__(
        self,
        *,
        parent_rows: list[Mapping[str, object]] | None = None,
        collision_table: str | None = None,
        collision_identifier: str | None = None,
        collision_version_id: str = _OTHER_VERSION_ID,
        collision_source_kind: str = "manual_okf",
        compatible_identifiers: Mapping[str, str] | None = None,
        sync_owner_rows: object = None,
        entity_rows: object = None,
        ownership_rows: object = None,
        fetchone_none: bool = False,
        close_error: Exception | None = None,
        fail_scope_lock: bool = False,
        has_adaptation_context: bool = True,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.closed = 0
        self._last_statement = ""
        self._parent_rows = parent_rows or []
        self._collision_table = collision_table
        self._collision_identifier = collision_identifier
        self._collision_version_id = collision_version_id
        self._collision_source_kind = collision_source_kind
        self._compatible_identifiers = dict(compatible_identifiers or {})
        self._sync_owner_rows = sync_owner_rows
        self._entity_rows = entity_rows
        self._ownership_rows = ownership_rows
        self._fetchone_none = fetchone_none
        self._close_error = close_error
        self._fail_scope_lock = fail_scope_lock
        self.connection = object()
        if has_adaptation_context:
            self.adapters = _AdapterRegistry()

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))
        if self._fail_scope_lock and "pg_advisory_xact_lock" in statement:
            raise RuntimeError("scope lock failed")

    def fetchall(self) -> object:
        normalized = _normalized(self._last_statement)
        if "document_versions" in normalized:
            return list(self._parent_rows)
        if self._sync_owner_rows is not None and "from okf_sync_state" in normalized:
            return self._sync_owner_rows
        if self._entity_rows is not None and "from entities" in normalized:
            return self._entity_rows
        if (
            self._ownership_rows is not None
            and "from okf_manual_fact_ownership" in normalized
        ):
            return self._ownership_rows
        if "= any(%s)" not in normalized:
            return []
        for table, identifier in _GLOBAL_ROWS:
            if not _references_exact_table(
                self._last_statement, keyword="from", table=table
            ):
                continue
            if table in self._compatible_identifiers:
                row: dict[str, object] = {
                    identifier: self._compatible_identifiers[table],
                    "version_id": _VERSION_ID,
                }
                if table == "evidence_links":
                    row["source_kind"] = "manual_okf"
                return [row]
            if table == self._collision_table:
                row = {
                    identifier: self._collision_identifier,
                    "version_id": self._collision_version_id,
                }
                if table == "evidence_links":
                    row["source_kind"] = self._collision_source_kind
                return [row]
        return []

    def fetchone(self) -> Mapping[str, object] | None:
        if self._fetchone_none:
            return None
        if "returning" in _normalized(self._last_statement):
            return {"okf_file_path": "okf/manual/sync.json"}
        return None

    def close(self) -> None:
        self.closed += 1
        if self._close_error is not None:
            raise self._close_error


class _Connection:
    """Narrow recording connection tracking autocommit writes and lifecycle."""

    autocommit_writes: list[object]

    def __init__(
        self,
        cursor: _Cursor,
        *,
        autocommit: object = False,
        has_autocommit: bool = True,
        rollback_error: Exception | None = None,
        close_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        object.__setattr__(self, "_track_autocommit_writes", False)
        object.__setattr__(self, "autocommit_writes", [])
        if has_autocommit:
            object.__setattr__(self, "autocommit", autocommit)
        object.__setattr__(self, "_track_autocommit_writes", True)
        self.cursor_value = cursor
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.commit_error = commit_error
        self.cursor_row_factories: list[object | None] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def __setattr__(self, name: str, value: object) -> None:
        if name == "autocommit" and self.__dict__.get(
            "_track_autocommit_writes", False
        ):
            self.autocommit_writes.append(value)
        object.__setattr__(self, name, value)

    def cursor(self, *, row_factory: object | None = None) -> _Cursor:
        self.cursor_row_factories.append(row_factory)
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class _Repository:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[object, E2aDesiredState, object]] = []
        self._failure = failure

    def reconcile(
        self,
        cursor: object,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        self.calls.append((cursor, desired, recorder))
        if self._failure is not None:
            raise self._failure
        return _no_op_result(desired)


class _Builder:
    def __init__(self, state: E2aDesiredState) -> None:
        self.calls: list[object] = []
        self._state = state

    def build(self, source: object) -> E2aDesiredState:
        self.calls.append(source)
        return self._state


class _SyncDesired:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.sync_state_rows = rows


def _sync_row() -> Mapping[str, object]:
    return {
        "okf_file_path": "okf/manual/sync.json",
        "doc_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "source_checksum": _DIGEST,
        "canonical_hash": _DIGEST,
        "status": "active",
        "materialization_owner": "e2a",
    }


def _entity_row(fact: E2aManualFact) -> Mapping[str, object]:
    return {
        "entity_id": fact.fact_id,
        "entity_key": fact.natural_key,
        "entity_type": "concept",
        "canonical_name": "Guarded",
        "description": None,
        "community_id": None,
    }


def _ownership_row(owner: E2aOwnershipFact) -> Mapping[str, object]:
    return {
        "ownership_id": owner.ownership_id,
        "okf_relative_path": owner.relative_path,
        "fact_kind": "entity",
        "fact_id": owner.fact_id,
        "entity_id": owner.fact_id,
        "relation_id": None,
        "source_digest": _DIGEST,
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "scope_version_id": _VERSION_ID,
    }


def _cells_module() -> ModuleType:
    from . import _phase15_e2a_task88_cells as cells

    return cells
