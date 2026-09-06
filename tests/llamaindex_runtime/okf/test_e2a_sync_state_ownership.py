"""RED cursor-only specifications for exclusive E2a sync-state ownership."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf._e2a_materialization_inventory import load_existing_scope
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
_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SYNC_PATH = "raw/guide.pair.json"
_SYNC_FIELDS = (
    "okf_file_path",
    "doc_id",
    "version_id",
    "source_checksum",
    "canonical_hash",
    "status",
    "materialization_owner",
)


def _contains(parameters: object | None, expected: str) -> bool:
    if isinstance(parameters, (tuple, list)):
        return any(_contains(value, expected) for value in parameters)
    return parameters == expected


def _select_clause(statement: str) -> str:
    return statement.lower().partition("from")[0]


def _sync_projection(statement: str) -> tuple[str, ...]:
    selected = _select_clause(statement)
    return tuple(
        field
        for field in _SYNC_FIELDS
        if re.search(rf"\b(?:[a-z_]+\.)?{field}\b", selected) is not None
    )


def _is_sync_read(statement: str) -> bool:
    return bool(
        re.search(r"\bfrom\s+okf_sync_state\b", statement.lower())
        and statement.lstrip().upper().startswith("SELECT")
    )


def _is_sync_dml(statement: str) -> bool:
    return bool(
        re.search(r"\b(?:into|from)\s+okf_sync_state\b", statement.lower())
        and statement.lstrip().upper().startswith(("INSERT", "DELETE", "UPDATE"))
    )


def _has_e2a_owner_filter(statement: str, parameters: object | None) -> bool:
    normalized = " ".join(statement.lower().split())
    return "materialization_owner" in normalized and (
        "'e2a'" in normalized or _contains(parameters, "e2a")
    )


@dataclass(frozen=True)
class _SyncStateRow:
    okf_file_path: str
    doc_id: str
    version_id: str
    source_checksum: str
    canonical_hash: str
    status: str
    materialization_owner: str

    def project(self, fields: tuple[str, ...]) -> dict[str, object]:
        values: Mapping[str, object] = {
            "okf_file_path": self.okf_file_path,
            "doc_id": self.doc_id,
            "version_id": self.version_id,
            "source_checksum": self.source_checksum,
            "canonical_hash": self.canonical_hash,
            "status": self.status,
            "materialization_owner": self.materialization_owner,
        }
        return {field: values[field] for field in fields}


def _sync_row(
    *,
    owner: str = "e2a",
    path: str = _SYNC_PATH,
    version_id: str = _VERSION_ID,
) -> _SyncStateRow:
    return _SyncStateRow(
        okf_file_path=path,
        doc_id=_DOCUMENT_ID,
        version_id=version_id,
        source_checksum="b" * 64,
        canonical_hash=_DIGEST,
        status="materialized",
        materialization_owner=owner,
    )


def _desired(*, sync_state_rows: tuple[Mapping[str, object], ...]) -> E2aDesiredState:
    parent = E2aParent(_DOCUMENT_ID, _VERSION_ID, _SYNC_PATH, _DIGEST)
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
        sync_state_rows=sync_state_rows,
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


class _OwnerAwareCursor:
    def __init__(
        self,
        rows: tuple[_SyncStateRow, ...] = (),
        *,
        collision_row: _SyncStateRow | None = None,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""
        self._rows = rows
        self._collision_row = collision_row

    @property
    def connection(self) -> object:
        raise AssertionError("E2a reconciliation must remain cursor-only")

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        if not _is_sync_read(self._last_statement):
            return []
        fields = _sync_projection(self._last_statement)
        if "materialization_owner" not in fields:
            return []
        rows = self._owned_rows(self._last_statement, self.calls[-1][1])
        return [row.project(fields) for row in rows]

    def fetchone(self) -> None:
        return None

    def _owned_rows(
        self, statement: str, parameters: object | None
    ) -> tuple[_SyncStateRow, ...]:
        if _has_e2a_owner_filter(statement, parameters):
            return self._matching_rows(
                tuple(row for row in self._rows if row.materialization_owner == "e2a"),
                parameters,
            )
        if self._collision_row is not None and _contains(
            parameters, self._collision_row.okf_file_path
        ):
            return (self._collision_row,)
        return ()

    @staticmethod
    def _matching_rows(
        rows: tuple[_SyncStateRow, ...], parameters: object | None
    ) -> tuple[_SyncStateRow, ...]:
        paths = tuple(row for row in rows if _contains(parameters, row.okf_file_path))
        if paths:
            return paths
        versions = tuple(row for row in rows if _contains(parameters, row.version_id))
        return versions or rows


def _sync_dml(cursor: _OwnerAwareCursor) -> list[tuple[str, object | None]]:
    return [call for call in cursor.calls if _is_sync_dml(call[0])]


def test_full_sync_inventory_filters_to_e2a_and_projects_owner() -> None:
    e2a = _sync_row()
    legacy = _sync_row(owner="legacy_pre_e2a", path="raw/legacy.pair.json")
    cursor = _OwnerAwareCursor((e2a, legacy))

    existing = load_existing_scope(
        cursor, _desired(sync_state_rows=(e2a.project(_SYNC_FIELDS),))
    )

    assert existing["okf_sync_state"] == (e2a.project(_SYNC_FIELDS),)
    sync_reads = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if _is_sync_read(statement)
    ]
    assert sync_reads
    assert all(
        "materialization_owner" in _sync_projection(statement)
        and _has_e2a_owner_filter(statement, parameters)
        for statement, parameters in sync_reads
    )


def test_same_path_legacy_sync_row_fails_before_any_sync_dml() -> None:
    desired_row = _sync_row().project(_SYNC_FIELDS)
    cursor = _OwnerAwareCursor(
        collision_row=_sync_row(owner="legacy_pre_e2a"),
    )

    with pytest.raises(ValueError, match="owner|collision|sync"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(sync_state_rows=(desired_row,)),
            recorder=DmlRecorder(),
        )

    assert _sync_dml(cursor) == []
    collision_reads = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if _is_sync_read(statement)
        and "materialization_owner" in _sync_projection(statement)
        and _contains(parameters, _SYNC_PATH)
    ]
    assert collision_reads


def test_sync_upsert_detects_atomic_legacy_conflict_returning_no_row() -> None:
    desired_row = _sync_row().project(_SYNC_FIELDS)
    cursor = _OwnerAwareCursor()

    with pytest.raises(ValueError, match="owner|conflict|sync"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(sync_state_rows=(desired_row,)),
            recorder=DmlRecorder(),
        )

    dml = _sync_dml(cursor)
    assert len(dml) == 1
    statement, _ = dml[0]
    conflict = statement.lower().partition("on conflict")[2]
    update_predicate = conflict.partition("returning")[0].partition("where")[2]
    assert "(okf_file_path)" in conflict
    assert "do update" in conflict
    assert "materialization_owner" in update_predicate
    assert "excluded.materialization_owner" not in update_predicate
    assert "returning" in conflict


def test_stale_sync_deletion_is_qualified_to_e2a_owner() -> None:
    stale = _sync_row(path="raw/stale.pair.json")
    cursor = _OwnerAwareCursor((stale,))

    result = E2aMaterializationRepository().reconcile(
        cursor,
        _desired(sync_state_rows=()),
        recorder=DmlRecorder(),
    )

    deletes = [
        (statement, parameters)
        for statement, parameters in _sync_dml(cursor)
        if statement.lstrip().upper().startswith("DELETE")
    ]
    assert len(deletes) == 1
    statement, parameters = deletes[0]
    assert "materialization_owner" in statement.lower()
    assert _has_e2a_owner_filter(statement, parameters)
    assert result.stale_deletion_counts["okf_sync_state"] == 1


def test_equivalent_e2a_sync_row_issues_zero_dml() -> None:
    existing_row = _sync_row()
    cursor = _OwnerAwareCursor((existing_row,))

    result = E2aMaterializationRepository().reconcile(
        cursor,
        _desired(sync_state_rows=(existing_row.project(_SYNC_FIELDS),)),
        recorder=DmlRecorder(),
    )

    assert result.outcome == "no_op"
    assert _sync_dml(cursor) == []
    assert result.primary_dml_by_table["okf_sync_state"] == 0


_MIGRATION_019 = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)


def test_migration_019_adds_atomic_legacy_defaulted_sync_owner_without_promotion() -> (
    None
):
    normalized = " ".join(_MIGRATION_019.read_text(encoding="utf-8").lower().split())

    assert normalized.count("do $e2a019$") == 1
    assert re.search(
        r"\badd column(?: if not exists)? materialization_owner\b", normalized
    )
    assert "materialization_owner text not null default 'legacy_pre_e2a'" in normalized
    assert "materialization_owner in ('legacy_pre_e2a', 'e2a')" in normalized
    assert "primary key (okf_file_path, materialization_owner)" not in normalized
    assert "primary key (materialization_owner, okf_file_path)" not in normalized
    assert not re.search(r"\bset\s+materialization_owner\s*=\s*'e2a'\b", normalized)


def test_desired_state_accepts_an_e2a_sync_projection_closed_over_parent() -> None:
    row = _sync_row().project(_SYNC_FIELDS)

    desired = _desired(sync_state_rows=(row,))

    assert dict(desired.sync_state_rows[0]) == row


@pytest.mark.parametrize(
    "owner",
    ("legacy_pre_e2a", "foreign_owner"),
    ids=("legacy", "unknown"),
)
def test_desired_state_rejects_sync_projection_not_owned_by_e2a(owner: str) -> None:
    invalid = {
        **_sync_row().project(_SYNC_FIELDS),
        "materialization_owner": owner,
    }

    with pytest.raises(ValueError, match="owner|sync|projection"):
        _desired(sync_state_rows=(invalid,))


def test_desired_state_rejects_sync_projection_missing_owner() -> None:
    invalid = dict(_sync_row().project(_SYNC_FIELDS))
    del invalid["materialization_owner"]

    with pytest.raises(ValueError, match="owner|sync|missing|required"):
        _desired(sync_state_rows=(invalid,))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("doc_id", str(UUID(int=10))),
        ("version_id", str(UUID(int=11))),
        ("okf_file_path", "raw/other.pair.json"),
        ("canonical_hash", "c" * 64),
        ("status", "retired"),
    ),
    ids=("document", "version", "path", "hash", "status"),
)
def test_desired_state_rejects_sync_projection_outside_exact_parent_closure(
    field: str, value: str
) -> None:
    invalid = {**_sync_row().project(_SYNC_FIELDS), field: value}

    with pytest.raises(ValueError, match="sync|parent|path|hash|status|projection"):
        _desired(sync_state_rows=(invalid,))


class _HistoricalSyncScopeCursor:
    def __init__(self, rows: tuple[_SyncStateRow, ...]) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""
        self._rows = rows

    @property
    def connection(self) -> object:
        raise AssertionError("E2a history discovery must remain cursor-only")

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        if not _is_sync_read(self._last_statement):
            return []
        fields = _sync_projection(self._last_statement)
        rows = self._matching_rows(self._last_statement, self.calls[-1][1])
        return [row.project(fields) for row in rows]

    def fetchone(self) -> None:
        return None

    def _matching_rows(
        self, statement: str, parameters: object | None
    ) -> tuple[_SyncStateRow, ...]:
        rows = (
            tuple(row for row in self._rows if row.materialization_owner == "e2a")
            if _has_e2a_owner_filter(statement, parameters)
            else self._rows
        )
        normalized = " ".join(statement.lower().split())
        if "where version_id = any" in normalized:
            return tuple(row for row in rows if _contains(parameters, row.version_id))
        if "okf_file_path = any" in normalized:
            return tuple(
                row for row in rows if _contains(parameters, row.okf_file_path)
            )
        return rows


def test_sync_history_and_inventory_isolate_retired_e2a_from_legacy_rows() -> None:
    retired_e2a = _sync_row(
        path="raw/retired-e2a.pair.json",
        version_id=str(UUID(int=20)),
    )
    legacy_same_version = _sync_row(
        owner="legacy_pre_e2a",
        path="raw/legacy-same-version.pair.json",
        version_id=retired_e2a.version_id,
    )
    cursor = _HistoricalSyncScopeCursor((retired_e2a, legacy_same_version))

    existing = load_existing_scope(cursor, _desired(sync_state_rows=()))

    scoped_paths = {str(row["okf_file_path"]) for row in existing["okf_sync_state"]}
    assert retired_e2a.okf_file_path in scoped_paths
    assert legacy_same_version.okf_file_path not in scoped_paths

    history_reads = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if _is_sync_read(statement)
        and "version_id" in _sync_projection(statement)
        and "where version_id = any" not in statement.lower()
        and "okf_file_path = any" not in statement.lower()
    ]
    assert history_reads
    assert all(
        _has_e2a_owner_filter(statement, parameters)
        for statement, parameters in history_reads
    )

    full_inventory_reads = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if _is_sync_read(statement) and "where version_id = any" in statement.lower()
    ]
    assert full_inventory_reads
    assert all(
        "materialization_owner" in _sync_projection(statement)
        and _has_e2a_owner_filter(statement, parameters)
        for statement, parameters in full_inventory_reads
    )
