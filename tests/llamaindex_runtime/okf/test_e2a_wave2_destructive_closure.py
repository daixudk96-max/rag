"""RED contracts for Wave 2 destructive-closure lock ordering."""

from __future__ import annotations

import re
from collections.abc import Mapping
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
_ENTITY_IDS = tuple(sorted((str(UUID(int=41)), str(UUID(int=42)))))
_RELATION_IDS = tuple(sorted((str(UUID(int=51)), str(UUID(int=52)))))
_PARENT_DOCUMENT_ID = str(UUID(int=1))
_PARENT_VERSION_ID = str(UUID(int=2))
_STALE_CHUNK_ID = str(UUID(int=61))
_STALE_NODE_ID = str(UUID(int=62))

_LOCK_STATEMENTS = {
    "entities": (
        "SELECT entity_id FROM entities WHERE entity_id = ANY(%s) "
        "ORDER BY entity_id FOR UPDATE"
    ),
    "relations": (
        "SELECT relation_id FROM relations WHERE relation_id = ANY(%s) "
        "ORDER BY relation_id FOR UPDATE"
    ),
}
_LOCK_FIELDS = {"entities": "entity_id", "relations": "relation_id"}


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


def _parented_empty_desired() -> E2aDesiredState:
    parent = E2aParent(
        document_id=_PARENT_DOCUMENT_ID,
        version_id=_PARENT_VERSION_ID,
        relative_path="raw/closure.pair.json",
        canonical_hash=_DIGEST,
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": (
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            },
        ),
    }
    return E2aDesiredState(
        **{
            **_empty_desired().__dict__,
            "corpus_manifest": manifest,
            "corpus_manifest_sha256": canonical_json_sha256(manifest),
            "parents": (parent,),
        }
    )


def _ownership_row(kind: str, fact_id: str, number: int) -> dict[str, object]:
    return {
        "ownership_id": str(UUID(int=number)),
        "okf_relative_path": f"{kind}/{number}.md",
        "fact_kind": kind,
        "fact_id": fact_id,
        "entity_id": fact_id if kind == "entity" else None,
        "relation_id": fact_id if kind == "relation" else None,
        "source_digest": _DIGEST,
        "document_id": None,
        "version_id": None,
        "scope_version_id": str(UUID(int=0)),
    }


def _entity_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "entity_id": entity_id,
            "entity_key": f"entity:{index}",
            "entity_type": "concept",
            "canonical_name": f"Entity {index}",
        }
        for index, entity_id in enumerate(_ENTITY_IDS)
    )


def _relation_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "relation_id": relation_id,
            "relation_key": f"relation:{index}",
            "relation_type": "related_to",
            "source_entity_id": _ENTITY_IDS[0],
            "target_entity_id": _ENTITY_IDS[1],
            "negation": False,
            "condition": None,
            "direction": None,
            "confidence": None,
            "qualifiers": {},
            "qualifiers_is_sql_null": False,
        }
        for index, relation_id in enumerate(_RELATION_IDS)
    )


def _normalized(statement: str) -> str:
    return " ".join(statement.split()).lower()


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


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


class _FactClosureCursor:
    """Fake cursor that makes an unlocked E2b FK insertion window observable."""

    def __init__(
        self,
        *,
        lock_rows: Mapping[str, tuple[object, ...]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.lock_calls: list[tuple[str, tuple[str, ...]]] = []
        self._last_statement = ""
        self._last_lock_table: str | None = None
        self._lock_rows = lock_rows or {
            "entities": tuple({"entity_id": value} for value in _ENTITY_IDS),
            "relations": tuple({"relation_id": value} for value in _RELATION_IDS),
        }

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self._last_lock_table = None
        self.calls.append((statement, parameters))
        normalized = _normalized(statement)
        if "for update" in normalized:
            self._record_fact_lock(statement, parameters)
            return
        if "select exists" in normalized:
            assert self.lock_calls == [
                ("entities", _ENTITY_IDS),
                ("relations", _RELATION_IDS),
            ], (
                "E2b FK insertion race: global dependency SELECT EXISTS ran before "
                "every retiring fact base row was locked"
            )
        if _is_dml(statement):
            assert self.lock_calls == [
                ("entities", _ENTITY_IDS),
                ("relations", _RELATION_IDS),
            ], "retiring fact base rows must lock before destructive DML"

    def fetchall(self) -> list[object]:
        normalized = _normalized(self._last_statement)
        if self._last_lock_table is not None:
            return list(self._lock_rows[self._last_lock_table])
        if "select exists" in normalized:
            return [{"present": False}]
        if (
            "from okf_manual_fact_ownership" in normalized
            and "version_id is null" in normalized
        ):
            ownership = [
                _ownership_row("relation", fact_id, 100 + index)
                for index, fact_id in enumerate(reversed(_RELATION_IDS))
            ]
            ownership.extend(
                _ownership_row("entity", fact_id, 200 + index)
                for index, fact_id in enumerate(reversed(_ENTITY_IDS))
            )
            return ownership
        if "from entities" in normalized and "where entity_id = any(%s)" in normalized:
            return list(_entity_rows())
        if (
            "from relations" in normalized
            and "where relation_id = any(%s)" in normalized
        ):
            return list(_relation_rows())
        return []

    def _record_fact_lock(self, statement: str, parameters: object | None) -> None:
        normalized = _normalized(statement)
        for table, expected_statement in _LOCK_STATEMENTS.items():
            if f"from {table}" not in normalized:
                continue
            assert normalized == _normalized(
                expected_statement
            ), "retiring fact locks must use the exact identifier-only projection"
            expected_ids = _ENTITY_IDS if table == "entities" else _RELATION_IDS
            assert _parameter_identifiers(parameters) == expected_ids
            self.lock_calls.append((table, expected_ids))
            self._last_lock_table = table
            return
        raise AssertionError("unexpected FOR UPDATE lock in manual-fact closure")


@pytest.mark.parametrize(
    ("table", "case"),
    (
        ("entities", "missing"),
        ("relations", "duplicate"),
        ("entities", "tuple"),
        ("relations", "extra"),
        ("entities", "native_uuid"),
        ("relations", "wrong_id"),
    ),
)
def test_malformed_retiring_fact_lock_rows_abort_before_dependency_probes_or_dml(
    table: str, case: str
) -> None:
    cursor = _FactClosureCursor(lock_rows=_malformed_lock_rows(table, case))

    with pytest.raises(ValueError):
        E2aMaterializationRepository().reconcile(
            cursor,
            _empty_desired(),
            recorder=DmlRecorder(),
        )

    assert not any(
        "select exists" in _normalized(statement) for statement, _ in cursor.calls
    )
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)


def _malformed_lock_rows(table: str, case: str) -> dict[str, tuple[object, ...]]:
    field = _LOCK_FIELDS[table]
    expected_ids = _ENTITY_IDS if table == "entities" else _RELATION_IDS
    rows: tuple[object, ...]
    if case == "missing":
        rows = ()
    elif case == "duplicate":
        rows = ({field: expected_ids[0]}, {field: expected_ids[0]})
    elif case == "tuple":
        rows = ((expected_ids[0],),)
    elif case == "extra":
        rows = tuple(
            {field: identifier, "unexpected": "extra"} for identifier in expected_ids
        )
    elif case == "native_uuid":
        rows = tuple({field: UUID(identifier)} for identifier in expected_ids)
    elif case == "wrong_id":
        rows = tuple(
            {field: str(UUID(int=900 + index))} for index, _ in enumerate(expected_ids)
        )
    else:
        raise AssertionError(f"unknown malformed fact-lock case: {case}")
    valid = {
        "entities": tuple({"entity_id": value} for value in _ENTITY_IDS),
        "relations": tuple({"relation_id": value} for value in _RELATION_IDS),
    }
    return {**valid, table: rows}


def test_retiring_fact_locks_are_sorted_before_global_probes_and_destructive_dml() -> (
    None
):
    cursor = _FactClosureCursor()

    E2aMaterializationRepository().reconcile(
        cursor,
        _empty_desired(),
        recorder=DmlRecorder(),
    )

    lock_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if "for update" in statement.lower()
    ]
    probe_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if "select exists" in _normalized(statement)
    ]
    dml_indexes = [
        index for index, (statement, _) in enumerate(cursor.calls) if _is_dml(statement)
    ]

    assert cursor.lock_calls == [
        ("entities", _ENTITY_IDS),
        ("relations", _RELATION_IDS),
    ]
    assert lock_indexes and probe_indexes and dml_indexes
    assert max(lock_indexes) < min(probe_indexes)
    assert max(lock_indexes) < min(dml_indexes)
    assert any(
        "chunk_entity_links" in statement.lower() for statement, _ in cursor.calls
    )


class _StaleChunkBeforeTreeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        normalized = _normalized(self._last_statement)
        if "select exists" in normalized:
            return [{"present": False}]
        if (
            "select chunk_id, version_id, node_id from vector_chunks" in normalized
            and "where version_id = any(%s)" in normalized
        ):
            return [
                {
                    "chunk_id": _STALE_CHUNK_ID,
                    "version_id": _PARENT_VERSION_ID,
                    "node_id": _STALE_NODE_ID,
                }
            ]
        if (
            "select node_id, version_id, parent_node_id from tree_nodes" in normalized
            and "where version_id = any(%s)" in normalized
        ):
            return [
                {
                    "node_id": _STALE_NODE_ID,
                    "version_id": _PARENT_VERSION_ID,
                    "parent_node_id": None,
                }
            ]
        if "for update" in normalized and "from vector_chunks" in normalized:
            return [{"chunk_id": _STALE_CHUNK_ID}]
        if "for update" in normalized and "from tree_nodes" in normalized:
            return [{"node_id": _STALE_NODE_ID}]
        return []


def test_stale_vector_chunks_delete_before_stale_tree_nodes() -> None:
    cursor = _StaleChunkBeforeTreeCursor()

    E2aMaterializationRepository().reconcile(
        cursor,
        _parented_empty_desired(),
        recorder=DmlRecorder(),
    )

    delete_chunk = next(
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if _normalized(statement).startswith("delete from vector_chunks")
    )
    delete_node = next(
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if _normalized(statement).startswith("delete from tree_nodes")
    )

    assert delete_chunk < delete_node


_STALE_SPAN_ID = str(UUID(int=63))
_STALE_EVIDENCE_ID = str(UUID(int=64))
_RETAINED_STALE_CHUNK_ID = str(UUID(int=71))
_RETAINED_MOVED_CHUNK_ID = str(UUID(int=72))
_DESIRED_NODE_ID = str(UUID(int=73))

_STALE_LOCK_FIELDS = {
    "canonical_spans": "span_id",
    "vector_chunks": "chunk_id",
    "tree_nodes": "node_id",
    "evidence": "evidence_id",
}
_STALE_LOCK_IDS = {
    "canonical_spans": (_STALE_SPAN_ID,),
    "vector_chunks": (_STALE_CHUNK_ID,),
    "tree_nodes": (_STALE_NODE_ID,),
    "evidence": (_STALE_EVIDENCE_ID,),
}
_STALE_LOCK_STATEMENTS = {
    table: (
        f"SELECT {field} FROM {table} WHERE {field} = ANY(%s) "
        f"ORDER BY {field} FOR UPDATE"
    )
    for table, field in _STALE_LOCK_FIELDS.items()
}


def _retiring_ownership_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        _ownership_row("entity", identifier, 300 + index)
        for index, identifier in enumerate(_ENTITY_IDS)
    ) + tuple(
        _ownership_row("relation", identifier, 400 + index)
        for index, identifier in enumerate(_RELATION_IDS)
    )


def _default_stale_lock_rows() -> dict[str, tuple[object, ...]]:
    return {
        "entities": tuple({"entity_id": identifier} for identifier in _ENTITY_IDS),
        "relations": tuple({"relation_id": identifier} for identifier in _RELATION_IDS),
        **{
            table: tuple({field: identifier} for identifier in _STALE_LOCK_IDS[table])
            for table, field in _STALE_LOCK_FIELDS.items()
        },
    }


class _DestructiveClosureCursor:
    """Fake complete enough to observe destructive-closure cursor behavior."""

    def __init__(
        self, *, lock_rows: Mapping[str, tuple[object, ...]] | None = None
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.dependency_call_indexes: list[int] = []
        self._last_lock_table: str | None = None
        self._last_statement = ""
        self._lock_rows = {**_default_stale_lock_rows(), **(lock_rows or {})}

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self._last_lock_table = None
        self.calls.append((statement, parameters))
        normalized = _normalized(statement)
        if "for update" in normalized:
            self._last_lock_table = self._lock_table(normalized)
        if self._is_dependency_probe(normalized):
            self.dependency_call_indexes.append(len(self.calls) - 1)

    def fetchall(self) -> list[Mapping[str, object] | object]:
        normalized = _normalized(self._last_statement)
        if self._last_lock_table is not None:
            return list(self._lock_rows[self._last_lock_table])
        if "select exists" in normalized:
            return [{"present": False}]
        if self._is_selected_dependency_probe(normalized):
            return []
        inventory_rows = {
            "select span_id from canonical_spans": [{"span_id": _STALE_SPAN_ID}],
            "select chunk_id, version_id, node_id from vector_chunks": [
                {
                    "chunk_id": _STALE_CHUNK_ID,
                    "version_id": _PARENT_VERSION_ID,
                    "node_id": _STALE_NODE_ID,
                }
            ],
            "select node_id, version_id, parent_node_id from tree_nodes": [
                {
                    "node_id": _STALE_NODE_ID,
                    "version_id": _PARENT_VERSION_ID,
                    "parent_node_id": None,
                }
            ],
            "from evidence inner join okf_manual_evidence_targets": [
                {"evidence_id": _STALE_EVIDENCE_ID}
            ],
        }
        for query, rows in inventory_rows.items():
            if query in normalized:
                return rows
        if (
            "from okf_manual_fact_ownership" in normalized
            and "version_id is null" in normalized
        ):
            return list(_retiring_ownership_rows())
        if "from entities" in normalized and "where entity_id = any(%s)" in normalized:
            return list(_entity_rows())
        if (
            "from relations" in normalized
            and "where relation_id = any(%s)" in normalized
        ):
            return list(_relation_rows())
        return []

    @staticmethod
    def _lock_table(normalized: str) -> str:
        for table in (*_LOCK_STATEMENTS, *_STALE_LOCK_STATEMENTS):
            if f"from {table}" in normalized:
                return table
        raise AssertionError("unexpected destructive-closure lock")

    @staticmethod
    def _is_dependency_probe(normalized: str) -> bool:
        return (
            "select exists" in normalized
            or _DestructiveClosureCursor._is_selected_dependency_probe(normalized)
        )

    @staticmethod
    def _is_selected_dependency_probe(normalized: str) -> bool:
        return (
            "from evidence_links" in normalized
            and "source_kind is distinct from" in normalized
        )


def _malformed_stale_lock_rows(table: str, case: str) -> dict[str, tuple[object, ...]]:
    field = _STALE_LOCK_FIELDS[table]
    expected_ids = _STALE_LOCK_IDS[table]
    rows: tuple[object, ...]
    if case == "missing":
        rows = ()
    elif case == "duplicate":
        rows = ({field: expected_ids[0]}, {field: expected_ids[0]})
    elif case == "tuple":
        rows = ((expected_ids[0],),)
    elif case == "extra":
        rows = ({field: expected_ids[0], "unexpected": "extra"},)
    elif case == "native_uuid":
        rows = ({field: UUID(expected_ids[0])},)
    elif case == "wrong_id":
        rows = ({field: str(UUID(int=900))},)
    else:
        raise AssertionError(f"unknown malformed stale-lock case: {case}")
    return {**_default_stale_lock_rows(), table: rows}


def _lock_call(
    cursor: _DestructiveClosureCursor, table: str
) -> tuple[str, object | None]:
    return next(
        (statement, parameters)
        for statement, parameters in cursor.calls
        if "for update" in _normalized(statement)
        and f"from {table}" in _normalized(statement)
    )


@pytest.mark.parametrize(
    ("table", "cases"),
    (
        ("canonical_spans", ("missing", "extra")),
        ("vector_chunks", ("duplicate", "native_uuid")),
        ("tree_nodes", ("tuple", "wrong_id")),
    ),
)
def test_malformed_direct_stale_lock_rows_abort_before_dependency_probes_or_dml(
    table: str, cases: tuple[str, ...]
) -> None:
    for case in cases:
        cursor = _DestructiveClosureCursor(
            lock_rows=_malformed_stale_lock_rows(table, case)
        )

        with pytest.raises(ValueError):
            E2aMaterializationRepository().reconcile(
                cursor,
                _parented_empty_desired(),
                recorder=DmlRecorder(),
            )

        statement, parameters = _lock_call(cursor, table)
        assert _normalized(statement) == _normalized(_STALE_LOCK_STATEMENTS[table])
        assert _parameter_identifiers(parameters) == _STALE_LOCK_IDS[table]
        assert not cursor.dependency_call_indexes
        assert not any(_is_dml(statement) for statement, _ in cursor.calls)


def _postgres_array_values(
    calls: list[tuple[str, object | None]],
) -> list[tuple[str, object | None]]:
    values: list[tuple[str, object | None]] = []
    for statement, parameters in calls:
        for match in re.finditer(r"\b(?:ANY|ALL)\(%s\)", statement, flags=re.I):
            placeholder_index = statement[: match.start()].count("%s")
            if type(parameters) is not tuple or placeholder_index >= len(parameters):
                values.append((statement, None))
            else:
                values.append((statement, parameters[placeholder_index]))
    return values


def test_destructive_closure_uses_psycopg_lists_for_every_array_parameter() -> None:
    cursor = _DestructiveClosureCursor()

    E2aMaterializationRepository().reconcile(
        cursor,
        _parented_empty_desired(),
        recorder=DmlRecorder(),
    )

    array_values = _postgres_array_values(cursor.calls)
    tuple_arrays = [
        statement for statement, value in array_values if type(value) is not list
    ]
    required_statements = (
        *_LOCK_STATEMENTS.values(),
        *_STALE_LOCK_STATEMENTS.values(),
        "DELETE FROM vector_chunk_spans WHERE chunk_id = ANY(%s)",
        "DELETE FROM vector_chunks WHERE chunk_id = ANY(%s)",
        *(
            f"DELETE FROM {table} WHERE node_id = ANY(%s)"
            for table in ("summaries", "node_embeddings", "semantic_distribution")
        ),
        "DELETE FROM tree_node_spans WHERE node_id = ANY(%s)",
        "DELETE FROM tree_nodes WHERE node_id = ANY(%s)",
    )
    issued_statements = {_normalized(statement) for statement, _ in cursor.calls}

    assert array_values
    assert not tuple_arrays, (
        "PostgreSQL ANY/ALL parameters must be Python lists inside the outer "
        f"parameter tuple: {tuple_arrays}"
    )
    assert {
        _normalized(statement) for statement in required_statements
    } <= issued_statements


def test_stale_evidence_is_locked_before_every_dependency_probe_and_dml() -> None:
    cursor = _DestructiveClosureCursor()

    E2aMaterializationRepository().reconcile(
        cursor,
        _parented_empty_desired(),
        recorder=DmlRecorder(),
    )

    evidence_lock_statement = _STALE_LOCK_STATEMENTS["evidence"]
    expected_locks = {
        _normalized(statement)
        for statement in (*_LOCK_STATEMENTS.values(), *_STALE_LOCK_STATEMENTS.values())
    }
    issued_locks = {
        _normalized(statement)
        for statement, _ in cursor.calls
        if "for update" in _normalized(statement)
    }
    lock_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if "for update" in _normalized(statement)
    ]
    dml_indexes = [
        index for index, (statement, _) in enumerate(cursor.calls) if _is_dml(statement)
    ]

    assert _normalized(evidence_lock_statement) in issued_locks
    assert expected_locks <= issued_locks
    assert lock_indexes and cursor.dependency_call_indexes and dml_indexes
    assert max(lock_indexes) < min(cursor.dependency_call_indexes)
    assert max(lock_indexes) < min(dml_indexes)


@pytest.mark.parametrize(
    "case", ("missing", "duplicate", "tuple", "extra", "native_uuid", "wrong_id")
)
def test_malformed_stale_evidence_lock_rows_abort_before_dependency_probes_or_dml(
    case: str,
) -> None:
    cursor = _DestructiveClosureCursor(
        lock_rows=_malformed_stale_lock_rows("evidence", case)
    )

    with pytest.raises(ValueError):
        E2aMaterializationRepository().reconcile(
            cursor,
            _parented_empty_desired(),
            recorder=DmlRecorder(),
        )

    statement, parameters = _lock_call(cursor, "evidence")
    assert _normalized(statement) == _normalized(_STALE_LOCK_STATEMENTS["evidence"])
    assert _parameter_identifiers(parameters) == _STALE_LOCK_IDS["evidence"]
    assert not cursor.dependency_call_indexes
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
