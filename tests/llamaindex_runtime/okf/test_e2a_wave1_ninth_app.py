"""Phase-15 Wave-1 ninth-remediation desired-state regressions."""

from __future__ import annotations

from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)


def _fact(path: str, digest: str) -> E2aManualFact:
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    return E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        path,
        digest,
        natural_key=natural_key,
    )


def _state_values(
    fact: E2aManualFact, owners: tuple[E2aOwnershipFact, ...]
) -> dict[str, object]:
    parent = E2aParent(
        str(UUID(int=1)),
        str(UUID(int=2)),
        "raw/source.pair.json",
        "d" * 64,
    )
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            },
            *[
                {
                    "kind": owner.fact_kind,
                    "path": owner.relative_path,
                    "identity": owner.fact_id,
                    "source_digest": owner.source_digest,
                }
                for owner in owners
            ],
        ]
    }
    return {
        "corpus_manifest": manifest,
        "corpus_manifest_sha256": canonical_json_sha256(manifest),
        "parents": (parent,),
        "canonical_spans": (),
        "vector_chunks": (),
        "vector_chunk_span_links": (),
        "tree_nodes": (),
        "tree_node_span_links": (),
        "manual_entities": (fact,),
        "manual_relations": (),
        "manual_concepts": (),
        "evidence_objects": (),
        "evidence_links": (),
        "ownership_facts": owners,
        "sync_state_rows": (),
        "validation_metadata": {},
        "provenance_metadata": {},
    }


def test_desired_state_rejects_forged_entity_representative_provenance() -> None:
    representative = _fact("entities/forged.md", "c" * 64)
    owners = (
        E2aOwnershipFact.create(
            relative_path="entities/first.md",
            fact_kind="entity",
            fact_id=representative.fact_id,
            source_digest="a" * 64,
        ),
        E2aOwnershipFact.create(
            relative_path="entities/second.md",
            fact_kind="entity",
            fact_id=representative.fact_id,
            source_digest="b" * 64,
        ),
    )

    with pytest.raises(ValueError, match="representative provenance"):
        E2aDesiredState(**_state_values(representative, owners))


def test_desired_state_accepts_representative_from_one_of_multiple_owners() -> None:
    representative = _fact("entities/second.md", "b" * 64)
    owners = (
        E2aOwnershipFact.create(
            relative_path="entities/first.md",
            fact_kind="entity",
            fact_id=representative.fact_id,
            source_digest="a" * 64,
        ),
        E2aOwnershipFact.create(
            relative_path=representative.relative_path,
            fact_kind="entity",
            fact_id=representative.fact_id,
            source_digest=representative.source_digest,
        ),
    )

    state = E2aDesiredState(**_state_values(representative, owners))

    assert state.manual_entities == (representative,)
    assert state.ownership_facts == owners
