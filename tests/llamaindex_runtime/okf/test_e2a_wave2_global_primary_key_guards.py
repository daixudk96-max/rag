"""Fake-only source-gate regressions for global E2a primary-key ownership."""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
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
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=101))
_VERSION_ID = str(UUID(int=102))
_OTHER_VERSION_ID = str(UUID(int=103))
_SPAN_ID = str(UUID(int=104))
_CHUNK_ID = str(UUID(int=105))
_NODE_ID = str(UUID(int=106))

_GLOBAL_ROWS = (
    ("canonical_spans", "span_id", _SPAN_ID),
    ("vector_chunks", "chunk_id", _CHUNK_ID),
    ("tree_nodes", "node_id", _NODE_ID),
    ("evidence", "evidence_id", "evidence_id"),
    ("evidence_links", "evidence_link_id", "evidence_link_id"),
)


def _desired() -> E2aDesiredState:
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


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


def _references_exact_table(statement: str, *, keyword: str, table: str) -> bool:
    """Check if normalized SQL references the exact table after keyword (not a substring).

    Uses word-boundary matching to distinguish 'FROM evidence' from 'FROM evidence_links'.
    """
    normalized = _normalized(statement)
    # Use word-boundary regex: \b matches at word boundary, _ is a word character
    # So 'evidence\b' matches 'evidence ' but not 'evidence_links'
    pattern = rf"\b{re.escape(keyword)}\s+{re.escape(table)}\b"
    return re.search(pattern, normalized) is not None


class _AdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _Cursor:
    def __init__(
        self,
        *,
        collision_table: str | None = None,
        collision_identifier: str | None = None,
        collision_version_id: str = _OTHER_VERSION_ID,
        collision_source_kind: str = "manual_okf",
        compatible_identifiers: Mapping[str, str] | None = None,
        raced_table: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.adapters = _AdapterRegistry()
        self.connection = object()
        self._last_statement = ""
        self._collision_table = collision_table
        self._collision_identifier = collision_identifier
        self._collision_version_id = collision_version_id
        self._collision_source_kind = collision_source_kind
        self._compatible_identifiers = dict(compatible_identifiers or {})
        self._raced_table = raced_table

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        normalized = _normalized(self._last_statement)
        if _references_exact_table(
            self._last_statement, keyword="from", table="document_versions"
        ):
            return [{"doc_id": _DOCUMENT_ID, "version_id": _VERSION_ID}]
        if self._collision_table is None:
            return []
        for table, identifier, value in _GLOBAL_ROWS:
            if (
                table in self._compatible_identifiers
                and _references_exact_table(
                    self._last_statement, keyword="from", table=table
                )
                and f"{identifier} = any(%s)" in normalized
            ):
                compatible: dict[str, object] = {
                    identifier: self._compatible_identifiers[table],
                    "version_id": _VERSION_ID,
                }
                if table == "evidence_links":
                    compatible["source_kind"] = "manual_okf"
                return [compatible]
            if (
                table == self._collision_table
                and _references_exact_table(
                    self._last_statement, keyword="from", table=table
                )
                and f"{identifier} = any(%s)" in normalized
            ):
                row: dict[str, object] = {
                    identifier: self._collision_identifier or self._identifier(value),
                    "version_id": self._collision_version_id,
                }
                if table == "evidence_links":
                    row["source_kind"] = self._collision_source_kind
                return [row]
        return []

    def fetchone(self) -> Mapping[str, object] | None:
        normalized = _normalized(self._last_statement)
        if "returning" not in normalized:
            return None
        if self._raced_table is not None and _references_exact_table(
            self._last_statement, keyword="into", table=self._raced_table
        ):
            return None
        return {"acknowledged": True}

    def close(self) -> None:
        return None

    @staticmethod
    def _identifier(value: str) -> str:
        return value


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.autocommit = False
        self.cursor_value = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, *, row_factory: object | None = None) -> _Cursor:
        del row_factory
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class _NoOpRepository:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def reconcile(
        self,
        cursor: object,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        self.calls.append((cursor, desired, recorder))
        return E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256=desired.corpus_manifest_sha256,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
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


def _global_preflight_calls(cursor: _Cursor) -> list[tuple[str, object | None]]:
    return [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if statement.lstrip().upper().startswith("SELECT")
        and any(
            _references_exact_table(statement, keyword="from", table=table)
            for table, _, _ in _GLOBAL_ROWS
        )
        and "= any(%s)" in _normalized(statement)
    ]


def _assert_global_preflight(cursor: _Cursor, desired: E2aDesiredState) -> None:
    calls = _global_preflight_calls(cursor)
    assert len(calls) == len(_GLOBAL_ROWS)
    for table, field, _ in _GLOBAL_ROWS:
        matches = [
            (statement, parameters)
            for statement, parameters in calls
            if _references_exact_table(statement, keyword="from", table=table)
        ]
        assert len(matches) == 1
        statement, parameters = matches[0]
        assert f"{field} = any(%s)" in _normalized(statement)
        assert type(parameters) is tuple
        assert parameters == ([_identifier_for(desired, table)],)
        if table == "evidence_links":
            assert "source_kind" in _normalized(statement).partition(" from ")[0]
    assert not any(
        statement.lstrip().upper().startswith("LOCK TABLE")
        and any(
            _references_exact_table(statement, keyword="lock table", table=table)
            for table, _, _ in _GLOBAL_ROWS
        )
        for statement, _ in cursor.calls
    )


@pytest.mark.parametrize("table", tuple(row[0] for row in _GLOBAL_ROWS))
def test_global_primary_key_preflight_rejects_cross_scope_takeover_before_repository_dml(
    table: str,
) -> None:
    desired = _desired()
    cursor = _Cursor(
        collision_table=table,
        collision_identifier=_identifier_for(desired, table),
    )
    connection = _Connection(cursor)
    repository = _NoOpRepository()

    with pytest.raises(ValueError, match="scope|global|version"):
        E2aReconciler(repository=repository).reconcile(connection, desired)

    _assert_global_preflight(cursor, desired)
    assert repository.calls == []
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_global_evidence_link_preflight_rejects_non_manual_source_kind() -> None:
    desired = _desired()
    cursor = _Cursor(
        collision_table="evidence_links",
        collision_identifier=desired.evidence_links[0].evidence_link_id,
        collision_version_id=_VERSION_ID,
        collision_source_kind="legacy",
    )
    connection = _Connection(cursor)
    repository = _NoOpRepository()

    with pytest.raises(ValueError, match="source|manual_okf|global"):
        E2aReconciler(repository=repository).reconcile(connection, desired)

    _assert_global_preflight(cursor, desired)
    assert repository.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_same_scope_global_rows_remain_eligible_for_sequential_no_op_reconciliation() -> (
    None
):
    desired = _desired()
    cursor = _Cursor(
        compatible_identifiers={
            table: _identifier_for(desired, table) for table, _, _ in _GLOBAL_ROWS
        }
    )
    connection = _Connection(cursor)
    repository = _NoOpRepository()

    result = E2aReconciler(repository=repository).reconcile(connection, desired)

    _assert_global_preflight(cursor, desired)
    assert result.outcome == "no_op"
    assert repository.calls
    assert connection.commits == connection.closed == 1
    assert connection.rollbacks == 0


@pytest.mark.parametrize("table", tuple(row[0] for row in _GLOBAL_ROWS))
def test_guarded_global_upsert_race_rolls_back_when_conflict_returns_no_row(
    table: str,
) -> None:
    desired = _desired()
    cursor = _Cursor(raced_table=table)
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="global|scope|conflict"):
        E2aReconciler().reconcile(connection, desired)

    guarded = [
        statement
        for statement, _ in cursor.calls
        if _is_dml(statement)
        and _references_exact_table(statement, keyword="into", table=table)
    ]
    assert len(guarded) == 1
    statement = _normalized(guarded[0])
    assert "on conflict" in statement
    assert "returning" in statement
    assert (
        "version_id" in statement.partition("on conflict")[2].partition("returning")[0]
    )
    if table == "evidence_links":
        assert "source_kind" in statement.partition("on conflict")[2]
    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1
    assert any(_is_dml(statement) for statement, _ in cursor.calls)


@pytest.mark.parametrize("table", tuple(row[0] for row in _GLOBAL_ROWS))
def test_global_upsert_conflict_where_clause_is_scope_only_before_returning(
    table: str,
) -> None:
    desired = _desired()
    cursor = _Cursor(raced_table=table)
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="global|scope|conflict"):
        E2aReconciler().reconcile(connection, desired)

    guarded = [
        statement
        for statement, _ in cursor.calls
        if _is_dml(statement)
        and _references_exact_table(statement, keyword="into", table=table)
    ]
    assert len(guarded) == 1
    statement = _normalized(guarded[0])
    assert "on conflict" in statement
    assert "returning" in statement

    # The scope predicate must govern the ENTIRE conflict update. PostgreSQL
    # AND precedence means an unparenthesized OR chain followed by
    # ``AND same_scope`` attaches the guard only to the final OR term, so the
    # frozen architecture requires a scope-only WHERE clause before RETURNING.
    after_on_conflict = statement.partition("on conflict")[2]
    before_returning = after_on_conflict.partition("returning")[0]
    conflict_where = before_returning.partition("where")[2]

    assert f"{table}.version_id = excluded.version_id" in conflict_where
    if table == "evidence_links":
        assert "source_kind = 'manual_okf'" in conflict_where

    # Python precomparison avoids ordinary unchanged DML, so the conflict WHERE
    # must not require mutable-field IS DISTINCT FROM predicates and must not
    # chain them with OR.
    assert " or " not in conflict_where
    assert "is distinct from" not in conflict_where
