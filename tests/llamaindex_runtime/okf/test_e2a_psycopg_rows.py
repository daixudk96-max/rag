"""RED specifications for E2a's per-cursor Psycopg row boundary.

The future row-factory module is imported lazily so its intentional absence does
not turn into a pytest collection failure. All database-facing collaborators are
local fakes; this suite never opens a database connection.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from psycopg.pq import ExecStatus

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

_ROWS_MODULE = "llamaindex_runtime.okf._e2a_psycopg_rows"
_DIGEST = "a" * 64


def _e2a_dict_row() -> object:
    specification = importlib.util.find_spec(_ROWS_MODULE)
    assert specification is not None, (
        "Wave 2 RED: add the private E2a Psycopg row-boundary module "
        "llamaindex_runtime.okf._e2a_psycopg_rows"
    )
    module = importlib.import_module(_ROWS_MODULE)
    factory = getattr(module, "e2a_dict_row", None)
    assert callable(factory), (
        "Wave 2 RED: the private E2a row-boundary module must expose "
        "callable e2a_dict_row"
    )
    return factory


def _uuid(number: int) -> str:
    return str(UUID(int=number))


def _desired() -> E2aDesiredState:
    parent = E2aParent(
        _uuid(1),
        _uuid(101),
        "raw/one.pair.json",
        _DIGEST,
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
        validation_metadata={},
        provenance_metadata={"authority": "okf"},
    )


def _result(desired: E2aDesiredState) -> E2aReconciliationResult:
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


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


class _AdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _Cursor:
    def __init__(self, rows: object | None = None) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object | None]] = []
        self.adapters = _AdapterRegistry()
        self.connection = object()
        self.closed = 0
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> object:
        if self.rows is not None:
            return self.rows
        if "document_versions" in self._last_statement.lower():
            return [{"doc_id": _uuid(1), "version_id": _uuid(101)}]
        return ()

    def close(self) -> None:
        self.closed += 1


class _PsycopgResult:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names
        self.nfields = len(names)
        self.status = ExecStatus.TUPLES_OK

    def fname(self, index: int) -> bytes:
        return self._names[index].encode("utf-8")


class _PsycopgCursor:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.pgresult = _PsycopgResult(names)
        self._encoding = "utf-8"


class _PrimaryConnection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor
        self.cursor_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.original_row_factory = object()
        self.row_factory = self.original_row_factory
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, *args: object, **kwargs: object) -> _Cursor:
        self.cursor_calls.append((args, dict(kwargs)))
        assert args == ()
        assert set(kwargs) == {
            "row_factory"
        }, "primary reconciliation cursor must receive row_factory by keyword"
        assert (
            kwargs["row_factory"] is not None
        ), "primary reconciliation cursor row_factory must not be None"
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class _NoOpRepository:
    def reconcile(
        self,
        cursor: _Cursor,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        del cursor, recorder
        return _result(desired)


class _PlainCursorConnection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor
        self.autocommit = False
        self.cursor_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, *args: object, **kwargs: object) -> _Cursor:
        self.cursor_calls.append((args, dict(kwargs)))
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class _FailingRepository:
    def reconcile(
        self,
        cursor: _Cursor,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        del cursor, desired, recorder
        raise RuntimeError("primary reconciliation failed")


def test_reconciler_uses_only_a_keyword_non_none_primary_row_factory_without_connection_mutation() -> (
    None
):
    cursor = _Cursor()
    connection = _PrimaryConnection(cursor)

    result = E2aReconciler(repository=_NoOpRepository()).reconcile(
        connection,
        _desired(),
    )

    assert result.outcome == "no_op"
    assert len(connection.cursor_calls) == 1
    assert connection.row_factory is connection.original_row_factory
    assert connection.autocommit is False
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_e2a_dict_row_returns_fresh_mapping_containers_and_only_normalizes_uuid_values() -> (
    None
):
    top_level_uuid = UUID(int=201)
    nested_uuid = UUID(int=202)
    list_uuid = UUID(int=203)
    tuple_uuid = UUID(int=204)
    inner_list_uuid = UUID(int=205)
    mapping_key = UUID(int=206)
    uuid_looking_text = "00000000-0000-0000-0000-0000000000cf"
    decimal = Decimal("1.250")
    calendar_date = date(2026, 7, 20)
    binary = b"unchanged"
    source = {
        "top_level": top_level_uuid,
        "nested": {
            "value": nested_uuid,
            "uuid_looking_text": uuid_looking_text,
            "decimal": decimal,
            "calendar_date": calendar_date,
            "binary": binary,
            mapping_key: top_level_uuid,
        },
        "items": [list_uuid, {"value": nested_uuid}],
        "pair": (tuple_uuid, [inner_list_uuid]),
    }
    row_maker = _e2a_dict_row()(_PsycopgCursor(("payload",)))

    row = row_maker((source,))

    payload = row["payload"]
    assert type(row) is dict
    assert type(payload) is dict
    assert type(payload["nested"]) is dict
    assert type(payload["items"]) is list
    assert type(payload["items"][1]) is dict
    assert type(payload["pair"]) is tuple
    assert type(payload["pair"][1]) is list
    assert payload is not source
    assert payload["nested"] is not source["nested"]
    assert payload["items"] is not source["items"]
    assert payload["items"][1] is not source["items"][1]
    assert payload["pair"] is not source["pair"]
    assert payload["pair"][1] is not source["pair"][1]
    assert payload["top_level"] == str(top_level_uuid)
    assert payload["nested"]["value"] == str(nested_uuid)
    assert payload["items"][0] == str(list_uuid)
    assert payload["items"][1]["value"] == str(nested_uuid)
    assert payload["pair"][0] == str(tuple_uuid)
    assert payload["pair"][1][0] == str(inner_list_uuid)
    assert mapping_key in payload["nested"]
    assert payload["nested"][mapping_key] == str(top_level_uuid)
    assert payload["nested"]["uuid_looking_text"] == uuid_looking_text
    assert payload["nested"]["decimal"] is decimal
    assert payload["nested"]["calendar_date"] is calendar_date
    assert payload["nested"]["binary"] is binary
    assert source["top_level"] is top_level_uuid
    assert source["nested"]["value"] is nested_uuid
    assert source["items"][0] is list_uuid
    assert source["pair"][0] is tuple_uuid


def test_repository_rejects_mapping_rows_with_native_uuid_identifiers_before_dml() -> (
    None
):
    cursor = _Cursor([{"version_id": UUID(int=101), "materialization_owner": "e2a"}])

    with pytest.raises(ValueError, match="materialization identifier is invalid"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(),
            recorder=importlib.import_module(
                "llamaindex_runtime.okf.e2a_materialization_repository"
            ).DmlRecorder(),
        )

    assert not any(_is_dml(statement) for statement, _ in cursor.calls)


def test_repository_rejects_tuple_rows_before_dml() -> None:
    cursor = _Cursor([(UUID(int=101), "e2a")])

    with pytest.raises(ValueError, match="malformed full materialization row"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(),
            recorder=importlib.import_module(
                "llamaindex_runtime.okf.e2a_materialization_repository"
            ).DmlRecorder(),
        )

    assert not any(_is_dml(statement) for statement, _ in cursor.calls)


def test_row_factory_does_not_relax_exact_top_level_repository_projections() -> None:
    row_maker = _e2a_dict_row()(
        _PsycopgCursor(("version_id", "materialization_owner", "unexpected"))
    )
    transformed_row = row_maker((UUID(int=101), "e2a", "extra column"))
    cursor = _Cursor([transformed_row])

    with pytest.raises(ValueError, match="malformed full materialization row"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(),
            recorder=importlib.import_module(
                "llamaindex_runtime.okf.e2a_materialization_repository"
            ).DmlRecorder(),
        )

    assert isinstance(transformed_row, Mapping)
    assert transformed_row["version_id"] == _uuid(101)
    assert set(transformed_row) == {
        "version_id",
        "materialization_owner",
        "unexpected",
    }
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)


def test_failure_audit_cursor_remains_plain_even_when_primary_reconciliation_fails() -> (
    None
):
    primary = _PlainCursorConnection(_Cursor())
    audit = _PlainCursorConnection(_Cursor())
    reconciler = E2aReconciler(
        repository=_FailingRepository(),
        failure_audit_connection_factory=lambda: audit,
    )

    result = reconciler.reconcile(primary, _desired())

    assert result.outcome == "rolled_back_failure"
    assert audit.cursor_calls == [((), {})]
    assert audit.commits == 1
    assert audit.closed == 1
