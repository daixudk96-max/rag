"""RED regression for Wave 2 entity-mention destructive-closure protection."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aManualFact,
    E2aOwnershipFact,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64
_ENTITY_NATURAL_KEY = '{"entity_type":"concept","title":"Retired entity"}'
_ENTITY_ID = deterministic_id("entity", _ENTITY_NATURAL_KEY)
_ENTITY_OWNERSHIP_ID = str(UUID(int=1502))


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


def _renamed_entity_ownership_desired() -> tuple[E2aDesiredState, E2aOwnershipFact]:
    relative_path = "facts/renamed-entity.md"
    entity = E2aManualFact(
        fact_id=_ENTITY_ID,
        fact_kind="entity",
        relative_path=relative_path,
        source_digest=_DIGEST,
        natural_key=_ENTITY_NATURAL_KEY,
    )
    ownership = E2aOwnershipFact.create(
        relative_path=relative_path,
        fact_kind="entity",
        fact_id=entity.fact_id,
        source_digest=entity.source_digest,
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "entity",
                "path": entity.relative_path,
                "identity": entity.fact_id,
                "source_digest": entity.source_digest,
            }
        ],
    }
    return (
        E2aDesiredState(
            corpus_manifest=manifest,
            corpus_manifest_sha256=canonical_json_sha256(manifest),
            parents=(),
            canonical_spans=(),
            vector_chunks=(),
            vector_chunk_span_links=(),
            tree_nodes=(),
            tree_node_span_links=(),
            manual_entities=(entity,),
            manual_relations=(),
            manual_concepts=(),
            evidence_objects=(),
            evidence_links=(),
            ownership_facts=(ownership,),
            sync_state_rows=(),
            validation_metadata=MappingProxyType({}),
            provenance_metadata=MappingProxyType({"authority": "okf"}),
        ),
        ownership,
    )


def _ownership_row(*, ownership_id: str, entity_id: str) -> Mapping[str, object]:
    return {
        "ownership_id": ownership_id,
        "okf_relative_path": "facts/retired-entity.md",
        "fact_kind": "entity",
        "fact_id": entity_id,
        "entity_id": entity_id,
        "relation_id": None,
        "source_digest": _DIGEST,
        "document_id": None,
        "version_id": None,
        "scope_version_id": str(UUID(int=0)),
    }


class _EntityMentionDependencyCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = _normalized(self._last_statement)
        if "for update" in statement and "from entities" in statement:
            return [{"entity_id": _ENTITY_ID}]
        if (
            "from okf_manual_fact_ownership" in statement
            and "version_id is null" in statement
        ):
            return [
                _ownership_row(
                    ownership_id=_ENTITY_OWNERSHIP_ID,
                    entity_id=_ENTITY_ID,
                )
            ]
        if "from entities" in statement and "where entity_id = any(%s)" in statement:
            return [
                {
                    "entity_id": _ENTITY_ID,
                    "entity_key": _ENTITY_NATURAL_KEY,
                    "entity_type": "concept",
                    "canonical_name": "Retired entity",
                }
            ]
        if "from entity_mentions" in statement and "where entity_id = %s" in statement:
            if self.calls[-1][1] != (_ENTITY_ID,):
                raise AssertionError("entity_mentions probe used an incorrect binding")
            return [{"present": True}]
        if "select exists" in statement:
            return [{"present": False}]
        return []


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _delete_calls(
    calls: list[tuple[str, object | None]],
) -> list[tuple[int, str, object | None]]:
    return [
        (index, statement, parameters)
        for index, (statement, parameters) in enumerate(calls)
        if statement.lstrip().upper().startswith("DELETE")
    ]


def test_entity_mentions_dependency_preserves_entity_but_deletes_stale_ownership() -> (
    None
):
    cursor = _EntityMentionDependencyCursor()

    result = E2aMaterializationRepository().reconcile(
        cursor,
        _empty_desired(),
        recorder=DmlRecorder(),
    )

    mention_probe_indexes = [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if "from entity_mentions" in _normalized(statement)
        and "where entity_id = %s" in _normalized(statement)
    ]
    delete_calls = _delete_calls(cursor.calls)
    ownership_deletes = [
        (statement, parameters)
        for _, statement, parameters in delete_calls
        if "from okf_manual_fact_ownership" in _normalized(statement)
    ]
    entity_deletes = [
        (statement, parameters)
        for _, statement, parameters in delete_calls
        if "from entities" in _normalized(statement) and parameters == (_ENTITY_ID,)
    ]
    entity_mention_dml = [
        statement
        for statement, _ in cursor.calls
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        and "entity_mentions" in _normalized(statement)
    ]

    assert mention_probe_indexes
    assert delete_calls
    assert max(mention_probe_indexes) < min(index for index, _, _ in delete_calls)
    assert ownership_deletes == [
        (
            "DELETE FROM okf_manual_fact_ownership WHERE ownership_id = ANY(%s)",
            ([_ENTITY_OWNERSHIP_ID],),
        )
    ]
    assert not entity_deletes
    assert not entity_mention_dml
    assert result.stale_deletion_counts["okf_manual_fact_ownership"] == 1


def test_renamed_ownership_deletes_stale_row_without_deleting_retained_entity() -> None:
    desired, new_ownership = _renamed_entity_ownership_desired()
    cursor = _EntityMentionDependencyCursor()

    result = E2aMaterializationRepository().reconcile(
        cursor,
        desired,
        recorder=DmlRecorder(),
    )

    delete_calls = _delete_calls(cursor.calls)
    ownership_deletes = [
        (statement, parameters)
        for _, statement, parameters in delete_calls
        if "from okf_manual_fact_ownership" in _normalized(statement)
    ]
    entity_deletes = [
        (statement, parameters)
        for _, statement, parameters in delete_calls
        if "from entities" in _normalized(statement) and parameters == (_ENTITY_ID,)
    ]
    ownership_upserts = [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if statement.lstrip().upper().startswith("INSERT")
        and "into okf_manual_fact_ownership" in _normalized(statement)
    ]

    assert ownership_deletes == [
        (
            "DELETE FROM okf_manual_fact_ownership WHERE ownership_id = ANY(%s)",
            ([_ENTITY_OWNERSHIP_ID],),
        )
    ]
    assert not entity_deletes
    assert ownership_upserts
    ownership_upsert_parameters = ownership_upserts[0][1]
    assert isinstance(ownership_upsert_parameters, tuple)
    assert ownership_upsert_parameters[0] == new_ownership.ownership_id
    assert result.stale_deletion_counts["okf_manual_fact_ownership"] == 1
