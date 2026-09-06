"""RED regressions for the remaining E2a reconciliation safety blockers.

All coverage uses cursor fakes: no connection, database, Docker, or transaction
ownership is required.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf._e2a_materialization_inventory import load_existing_scope
from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_CHUNK_ID = str(UUID(int=4))
_NODE_ID = str(UUID(int=5))
_FOREIGN_DOCUMENT_ID = str(UUID(int=90))
_FOREIGN_VERSION_ID = str(UUID(int=91))
_FOREIGN_SPAN_ID = str(UUID(int=92))
_FOREIGN_CHUNK_ID = str(UUID(int=93))
_FOREIGN_NODE_ID = str(UUID(int=94))


def _uuid(number: int) -> str:
    return str(UUID(int=number))


def _desired_kwargs(
    *, parents: tuple[E2aParent, ...] | None = None
) -> dict[str, object]:
    admitted_parents = (
        parents
        if parents is not None
        else (
            E2aParent(
                _DOCUMENT_ID,
                _VERSION_ID,
                "raw/guide.pair.json",
                _DIGEST,
            ),
        )
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
            for parent in admitted_parents
        ],
    }
    return {
        "corpus_manifest": manifest,
        "corpus_manifest_sha256": canonical_json_sha256(manifest),
        "parents": admitted_parents,
        "canonical_spans": (),
        "vector_chunks": (),
        "vector_chunk_span_links": (),
        "tree_nodes": (),
        "tree_node_span_links": (),
        "manual_entities": (),
        "manual_relations": (),
        "manual_concepts": (),
        "evidence_objects": (),
        "evidence_links": (),
        "ownership_facts": (),
        "sync_state_rows": (),
        "validation_metadata": MappingProxyType({}),
        "provenance_metadata": MappingProxyType({"authority": "okf"}),
    }


def _desired(**changes: object) -> E2aDesiredState:
    values = _desired_kwargs()
    values.update(changes)
    return E2aDesiredState(**values)


def _empty_desired() -> E2aDesiredState:
    return E2aDesiredState(**_desired_kwargs(parents=()))


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""
        self.closed = 0

    @property
    def connection(self) -> object:
        raise AssertionError("E2a repository must remain cursor-only")

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        return []

    def close(self) -> None:
        self.closed += 1


class _GlobalOwnershipCursor(_Cursor):
    def __init__(self, ownership_id: str) -> None:
        super().__init__()
        self._ownership_id = ownership_id

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self._last_statement.lower()
        if (
            "from okf_manual_fact_ownership" not in statement
            or "version_id is null" not in statement
        ):
            return []
        if "okf_relative_path" in statement:
            return [
                {
                    "ownership_id": self._ownership_id,
                    "okf_relative_path": "facts/entity.md",
                    "fact_kind": "entity",
                    "fact_id": _uuid(701),
                    "entity_id": _uuid(701),
                    "relation_id": None,
                    "source_digest": _DIGEST,
                    "document_id": None,
                    "version_id": None,
                    "scope_version_id": str(UUID(int=0)),
                }
            ]
        return [
            {
                "ownership_id": self._ownership_id,
                "fact_kind": "entity",
                "fact_id": _uuid(701),
            }
        ]


@pytest.mark.parametrize("state_factory", (_desired, _empty_desired))
def test_existing_scope_inventories_stale_global_ownership_without_desired_ownership(
    state_factory: Callable[[], E2aDesiredState],
) -> None:
    ownership_id = _uuid(700)
    cursor = _GlobalOwnershipCursor(ownership_id)

    existing = load_existing_scope(cursor, state_factory())

    assert [row["ownership_id"] for row in existing["okf_manual_fact_ownership"]] == [
        ownership_id
    ]
    assert any(
        "from okf_manual_fact_ownership" in statement.lower()
        and "version_id is null" in statement.lower()
        for statement, _ in cursor.calls
    )


def _contains(parameters: object | None, identifier: str) -> bool:
    if isinstance(parameters, (tuple, list)):
        return any(_contains(value, identifier) for value in parameters)
    return parameters == identifier


def _select_clause(statement: str) -> str:
    return statement.lower().partition("from")[0]


class _SyncHistoryCursor(_Cursor):
    def __init__(
        self,
        e2a_retired_version_id: str,
        legacy_retired_version_id: str,
        retired_span_id: str,
    ) -> None:
        super().__init__()
        self._e2a_retired_version_id = e2a_retired_version_id
        self._legacy_retired_version_id = legacy_retired_version_id
        self._retired_span_id = retired_span_id
        self._retired_path = "raw/retired.pair.json"

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self._last_statement.lower()
        if "from okf_sync_state" in statement:
            return self._sync_rows(statement, self.calls[-1][1])
        if (
            "from canonical_spans" in statement
            and "where version_id = any" in statement
            and _contains(self.calls[-1][1], self._e2a_retired_version_id)
        ):
            return [{"span_id": self._retired_span_id}]
        return []

    def _sync_rows(
        self, statement: str, parameters: object | None
    ) -> list[Mapping[str, object]]:
        if "materialization_owner" not in statement:
            return []
        if not (_contains(parameters, "e2a") or "'e2a'" in statement):
            return []
        if (
            "where version_id = any" in statement
            and not _contains(parameters, self._e2a_retired_version_id)
        ) or (
            "okf_file_path = any" in statement
            and not _contains(parameters, self._retired_path)
        ):
            return []
        selected = _select_clause(statement)
        values: Mapping[str, object] = {
            "okf_file_path": self._retired_path,
            "doc_id": _uuid(800),
            "version_id": self._e2a_retired_version_id,
            "source_checksum": "b" * 64,
            "canonical_hash": _DIGEST,
            "status": "materialized",
            "materialization_owner": "e2a",
        }
        row = {field: value for field, value in values.items() if field in selected}
        return [row] if row else []


def test_existing_scope_discovers_only_e2a_retired_versions_from_sync_history() -> None:
    e2a_retired_version_id = _uuid(801)
    legacy_retired_version_id = _uuid(803)
    retired_span_id = _uuid(802)
    cursor = _SyncHistoryCursor(
        e2a_retired_version_id,
        legacy_retired_version_id,
        retired_span_id,
    )

    existing = load_existing_scope(cursor, _desired())

    assert [row["span_id"] for row in existing["canonical_spans"]] == [retired_span_id]
    history_discovery_queries = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if "from okf_sync_state" in statement.lower()
        and "version_id" in _select_clause(statement)
        and "okf_file_path = any" not in statement.lower()
    ]
    assert history_discovery_queries
    assert all(
        "materialization_owner" in statement.lower()
        and (_contains(parameters, "e2a") or "'e2a'" in statement.lower())
        for statement, parameters in history_discovery_queries
    )
    canonical_inventory_parameters = [
        parameters
        for statement, parameters in cursor.calls
        if "from canonical_spans" in statement.lower()
        and "where version_id = any" in statement.lower()
    ]
    assert canonical_inventory_parameters
    assert all(
        not _contains(parameters, legacy_retired_version_id)
        for parameters in canonical_inventory_parameters
    )


def _projection_rows() -> dict[str, tuple[dict[str, object], ...]]:
    return {
        "canonical_spans": (
            E2aSpan(_DOCUMENT_ID, _VERSION_ID, _SPAN_ID, 0, "Admitted text."),
        ),
        "tree_nodes": (
            {
                "node_id": _NODE_ID,
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
        "tree_node_span_links": (
            {"node_id": _NODE_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
        ),
        "vector_chunks": (
            {
                "chunk_id": _CHUNK_ID,
                "version_id": _VERSION_ID,
                "chunk_type": "canonical_span",
                "chunk_order": 0,
                "token_count": 2,
                "text_preview": "Admitted text.",
                "page_no": 1,
                "heading_path": "Guide",
                "node_id": _NODE_ID,
                "embedding": [0.0] * 16,
            },
        ),
        "vector_chunk_span_links": (
            {"chunk_id": _CHUNK_ID, "span_id": _SPAN_ID, "ordinal_no": 0},
        ),
        "sync_state_rows": (
            {
                "okf_file_path": "raw/guide.pair.json",
                "doc_id": _DOCUMENT_ID,
                "version_id": _VERSION_ID,
                "source_checksum": "b" * 64,
                "canonical_hash": _DIGEST,
                "status": "materialized",
                "materialization_owner": "e2a",
            },
        ),
    }


def _projected_desired(**changes: object) -> E2aDesiredState:
    values = _desired_kwargs()
    values.update(_projection_rows())
    values.update(changes)
    return E2aDesiredState(**values)


def test_desired_state_accepts_json_projections_inside_the_admitted_graph() -> None:
    desired = _projected_desired()

    assert desired.vector_chunks[0]["version_id"] == _VERSION_ID
    assert desired.vector_chunk_span_links[0]["span_id"] == _SPAN_ID
    assert desired.tree_nodes[0]["node_id"] == _NODE_ID
    assert desired.tree_node_span_links[0]["node_id"] == _NODE_ID
    assert desired.sync_state_rows[0]["doc_id"] == _DOCUMENT_ID
    assert desired.sync_state_rows[0]["materialization_owner"] == "e2a"


@pytest.mark.parametrize(
    ("field", "replacement", "case"),
    (
        ("vector_chunks", {"version_id": _FOREIGN_VERSION_ID}, "foreign version"),
        ("vector_chunks", {"node_id": _FOREIGN_NODE_ID}, "foreign node"),
        (
            "vector_chunk_span_links",
            {"chunk_id": _FOREIGN_CHUNK_ID},
            "foreign chunk",
        ),
        (
            "vector_chunk_span_links",
            {"span_id": _FOREIGN_SPAN_ID},
            "foreign span",
        ),
        ("tree_nodes", {"version_id": _FOREIGN_VERSION_ID}, "foreign version"),
        (
            "tree_nodes",
            {"parent_node_id": _FOREIGN_NODE_ID},
            "foreign parent node",
        ),
        ("tree_node_span_links", {"node_id": _FOREIGN_NODE_ID}, "foreign node"),
        ("tree_node_span_links", {"span_id": _FOREIGN_SPAN_ID}, "foreign span"),
        ("sync_state_rows", {"doc_id": _FOREIGN_DOCUMENT_ID}, "foreign document"),
        ("sync_state_rows", {"version_id": _FOREIGN_VERSION_ID}, "foreign version"),
        ("sync_state_rows", {"okf_file_path": "raw/other.pair.json"}, "foreign path"),
        ("sync_state_rows", {"canonical_hash": "c" * 64}, "foreign hash"),
        ("sync_state_rows", {"status": "pending"}, "foreign status"),
    ),
    ids=lambda case: case if isinstance(case, str) else None,
)
def test_desired_state_rejects_json_projections_outside_admitted_parent_graph(
    field: str,
    replacement: Mapping[str, object],
    case: str,
) -> None:
    rows = _projection_rows()
    invalid = {**rows[field][0], **replacement}

    with pytest.raises(
        ValueError, match="parent|projection|graph|version|span|chunk|node|sync"
    ):
        _projected_desired(**{field: (invalid,)})


@pytest.mark.parametrize(
    "owner",
    ("legacy_pre_e2a", "legacy_🚫", None, 0),
    ids=("legacy", "unrecognized unicode", "null", "invalid type"),
)
def test_desired_state_rejects_sync_rows_not_owned_by_e2a(owner: object) -> None:
    invalid = {
        **_projection_rows()["sync_state_rows"][0],
        "materialization_owner": owner,
    }

    with pytest.raises(ValueError, match="owner|projection|sync"):
        _projected_desired(sync_state_rows=(invalid,))


def test_desired_state_rejects_sync_rows_missing_materialization_owner() -> None:
    invalid = dict(_projection_rows()["sync_state_rows"][0])
    del invalid["materialization_owner"]

    with pytest.raises(ValueError, match="owner|missing|required|sync"):
        _projected_desired(sync_state_rows=(invalid,))


class _MalformedDependencyCursor(_Cursor):
    def __init__(self, dependency_rows: tuple[Mapping[str, object], ...]) -> None:
        super().__init__()
        self._dependency_rows = dependency_rows

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self._last_statement.lower()
        for table, field in (
            ("canonical_spans", "span_id"),
            ("vector_chunks", "chunk_id"),
            ("tree_nodes", "node_id"),
            ("evidence", "evidence_id"),
        ):
            if f"select {field} from {table} where {field} = any" in statement:
                parameters = self.calls[-1][1]
                assert isinstance(parameters, tuple) and len(parameters) == 1
                identifiers = parameters[0]
                assert isinstance(identifiers, list)
                assert all(
                    isinstance(identifier, str) and identifier
                    for identifier in identifiers
                )
                return [{field: identifier} for identifier in sorted(identifiers)]
        if (
            "from canonical_spans" in statement
            and "where version_id = any" in statement
        ):
            return [{"span_id": _uuid(901)}]
        if "entity_mentions" in statement:
            return list(self._dependency_rows)
        return []


def _deletes(cursor: _Cursor) -> list[str]:
    return [
        statement
        for statement, _ in cursor.calls
        if statement.lstrip().upper().startswith("DELETE")
    ]


@pytest.mark.parametrize(
    ("dependency_rows", "case"),
    (
        ((), "zero rows"),
        (({"present": False}, {"present": False}), "multiple rows"),
        (({"unexpected": "value"},), "missing field"),
        (({"present": "false", "unexpected": "value"},), "extra field"),
        (({"present": "false"},), "non-boolean present"),
    ),
    ids=lambda case: case if isinstance(case, str) else None,
)
def test_destructive_closure_rejects_ambiguous_exists_probe_before_any_delete(
    dependency_rows: tuple[Mapping[str, object], ...],
    case: str,
) -> None:
    cursor = _MalformedDependencyCursor(dependency_rows)

    with pytest.raises(ValueError, match="dependency probe"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _desired(),
            recorder=DmlRecorder(),
        )

    assert _deletes(cursor) == []


class _StaleCandidateCursor(_Cursor):
    def __init__(self) -> None:
        super().__init__()
        self.span_ids = (_uuid(903), _uuid(901))
        self.chunk_ids = (_uuid(905), _uuid(904))
        self.node_ids = (_uuid(907), _uuid(906))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self._last_statement.lower()
        for field in ("span_id", "chunk_id", "node_id"):
            if f"where {field} = any" in statement and "for update" in statement:
                parameters = self.calls[-1][1]
                assert isinstance(parameters, tuple) and len(parameters) == 1
                identifiers = parameters[0]
                assert isinstance(identifiers, list)
                return [{field: identifier} for identifier in sorted(identifiers)]
        reverse_reference_probes = {
            "select exists (select 1 from vector_chunk_spans where span_id = any(%s) "
            "and chunk_id <> all(%s)) as present": (
                list(sorted(self.span_ids)),
                list(sorted(self.chunk_ids)),
            ),
            "select exists (select 1 from tree_node_spans where span_id = any(%s) "
            "and node_id <> all(%s)) as present": (
                list(sorted(self.span_ids)),
                list(sorted(self.node_ids)),
            ),
            "select exists (select 1 from vector_chunks where node_id = any(%s) "
            "and chunk_id <> all(%s)) as present": (
                list(sorted(self.node_ids)),
                list(sorted(self.chunk_ids)),
            ),
            "select exists (select 1 from tree_nodes where parent_node_id = any(%s) "
            "and node_id <> all(%s)) as present": (
                list(sorted(self.node_ids)),
                list(sorted(self.node_ids)),
            ),
        }
        expected_parameters = reverse_reference_probes.get(statement)
        if expected_parameters is not None:
            parameters = self.calls[-1][1]
            assert isinstance(parameters, tuple) and len(parameters) == 2
            assert all(isinstance(value, list) for value in parameters)
            assert parameters == expected_parameters
            return [{"present": False}]
        if "entity_mentions" in statement:
            return [{"present": False}]
        if "chunk_entity_links" in statement:
            return [{"present": False}]
        if "node_entity_links" in statement:
            return [{"present": False}]
        if (
            "from canonical_spans" in statement
            and "where version_id = any" in statement
        ):
            return [{"span_id": span_id} for span_id in self.span_ids]
        if "from vector_chunks" in statement and "where version_id = any" in statement:
            return [
                {"chunk_id": chunk_id, "version_id": _VERSION_ID, "node_id": None}
                for chunk_id in self.chunk_ids
            ]
        if "from tree_nodes" in statement and "where version_id = any" in statement:
            return [
                {
                    "node_id": node_id,
                    "version_id": _VERSION_ID,
                    "parent_node_id": None,
                }
                for node_id in self.node_ids
            ]
        return []


def _row_locks(
    cursor: _StaleCandidateCursor, table: str
) -> list[tuple[int, str, object | None]]:
    return [
        (index, statement, parameters)
        for index, (statement, parameters) in enumerate(cursor.calls)
        if "for update" in statement.lower() and f"from {table}" in statement.lower()
    ]


def _matching_parameter_ids(
    parameters: object | None, expected: tuple[str, ...]
) -> list[str]:
    flattened: list[str] = []

    def collect(value: object | None) -> None:
        if isinstance(value, (tuple, list)):
            for item in value:
                collect(item)
        elif isinstance(value, str) and value in expected:
            flattened.append(value)

    collect(parameters)
    return flattened


def _is_direct_candidate_lock(statement: str, identifier: str) -> bool:
    normalized = "".join(statement.lower().split())
    return f"{identifier}=any(" in normalized or f"{identifier}=%s" in normalized


def test_repository_locks_sorted_stale_candidates_before_dependency_probes_and_deletes() -> (
    None
):
    cursor = _StaleCandidateCursor()

    E2aMaterializationRepository().reconcile(
        cursor,
        _desired(),
        recorder=DmlRecorder(),
    )

    expected = {
        "canonical_spans": ("span_id", tuple(sorted(cursor.span_ids))),
        "vector_chunks": ("chunk_id", tuple(sorted(cursor.chunk_ids))),
        "tree_nodes": ("node_id", tuple(sorted(cursor.node_ids))),
    }
    lock_indexes: list[int] = []
    for table, (identifier, identifiers) in expected.items():
        locks = _row_locks(cursor, table)
        assert locks
        assert all(
            _is_direct_candidate_lock(statement, identifier)
            for _, statement, _ in locks
        )
        locked_ids = [
            candidate_id
            for _, _, parameters in locks
            for candidate_id in _matching_parameter_ids(parameters, identifiers)
        ]
        assert locked_ids == list(identifiers)
        assert all(
            "order by" in statement.lower()
            for _, statement, parameters in locks
            if len(_matching_parameter_ids(parameters, identifiers)) > 1
        )
        lock_indexes.extend(index for index, _, _ in locks)

    dependency_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if "select exists" in statement.lower()
        and any(
            f"from {table}" in statement.lower()
            for table in (
                "entity_mentions",
                "chunk_entity_links",
                "node_entity_links",
                "vector_chunk_spans",
                "tree_node_spans",
                "vector_chunks",
                "tree_nodes",
            )
        )
    ]
    delete_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if statement.lstrip().upper().startswith("DELETE")
    ]

    assert cursor.closed == 0
    assert dependency_indexes
    assert delete_indexes
    assert max(lock_indexes) < min(dependency_indexes)
    assert max(lock_indexes) < min(delete_indexes)


class _PartialGlobalOwnershipCursor(_Cursor):
    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self._last_statement.lower()
        if (
            "from okf_manual_fact_ownership" in statement
            and "version_id is null" in statement
        ):
            return [{"ownership_id": _uuid(701)}]
        return []


def test_partial_global_ownership_projection_rejects_before_dml() -> None:
    cursor = _PartialGlobalOwnershipCursor()

    with pytest.raises(ValueError, match="malformed full materialization row"):
        E2aMaterializationRepository().reconcile(
            cursor, _desired(), recorder=DmlRecorder()
        )

    assert not [
        statement
        for statement, _ in cursor.calls
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
