from __future__ import annotations

from dataclasses import FrozenInstanceError
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


def _desired_state() -> E2aDesiredState:
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": "raw/source.pair.json",
                "identity": "00000000-0000-0000-0000-000000000001:00000000-0000-0000-0000-000000000002",
                "canonical_hash": "a" * 64,
            }
        ]
    }
    return E2aDesiredState(
        corpus_manifest=MappingProxyType(manifest),
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(
            E2aParent(
                document_id="00000000-0000-0000-0000-000000000001",
                version_id="00000000-0000-0000-0000-000000000002",
                relative_path="raw/source.pair.json",
                canonical_hash="a" * 64,
            ),
        ),
        canonical_spans=(
            E2aSpan(
                document_id="00000000-0000-0000-0000-000000000001",
                version_id="00000000-0000-0000-0000-000000000002",
                span_id="00000000-0000-0000-0000-000000000003",
                offset=0,
                text="Unicode evidence: 猫",
            ),
        ),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({"source": "strict_raw_pair"}),
        provenance_metadata=MappingProxyType({"schema": "e2a"}),
    )


def test_desired_state_is_frozen_and_has_all_e2a_collections() -> None:
    state = _desired_state()

    assert state.vector_chunks == ()
    assert state.tree_nodes == ()
    assert state.manual_entities == ()
    with pytest.raises(FrozenInstanceError):
        state.parents = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        state.validation_metadata["source"] = "changed"  # type: ignore[index]


def test_canonical_hash_is_reorder_invariant() -> None:
    left = {"b": ["猫", 2], "a": {"z": True}}
    right = {"a": {"z": True}, "b": ["猫", 2]}

    assert canonical_json_sha256(left) == canonical_json_sha256(right)


def test_manual_evidence_requires_one_target_and_span_backed_scope() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        E2aEvidenceReference(
            document_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
            span_id="00000000-0000-0000-0000-000000000003",
            entity_id="00000000-0000-0000-0000-000000000004",
            relation_id="00000000-0000-0000-0000-000000000005",
            evidence_id="00000000-0000-0000-0000-000000000006",
            ownership_id="00000000-0000-0000-0000-000000000007",
            ownership_scope_version_id="00000000-0000-0000-0000-000000000000",
        )
    with pytest.raises(ValueError, match="span_id"):
        E2aEvidenceReference(
            document_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
            span_id=None,
            entity_id="00000000-0000-0000-0000-000000000004",
            relation_id=None,
            evidence_id="00000000-0000-0000-0000-000000000006",
            ownership_id="00000000-0000-0000-0000-000000000007",
            ownership_scope_version_id="00000000-0000-0000-0000-000000000000",
        )


def test_paragraph_or_label_only_manual_evidence_without_span_is_rejected() -> None:
    # D-15-09 regression: paragraph-only or label-only manual evidence that
    # omits a canonical span target is rejected at construction with a static
    # ValueError contract. ``span_id is None`` is rejected in
    # E2aEvidenceReference.__post_init__ before target resolution, so evidence
    # scoped only to a paragraph or label (no span) can never be admitted. This
    # reuses the E2aEvidenceReference construction shape from the sibling test
    # but pins the full contract message rather than a loose "span_id"
    # substring, closing the audited assertion naming gap.
    with pytest.raises(ValueError, match=r"^manual evidence requires span_id$"):
        E2aEvidenceReference(
            document_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
            span_id=None,
            entity_id="00000000-0000-0000-0000-000000000004",
            relation_id=None,
            evidence_id="00000000-0000-0000-0000-000000000006",
            ownership_id="00000000-0000-0000-0000-000000000007",
            ownership_scope_version_id="00000000-0000-0000-0000-000000000000",
        )


def test_ownership_ids_are_stable_and_collision_is_rejected() -> None:
    first = E2aOwnershipFact.create(
        relative_path="entities/cat.md",
        fact_kind="entity",
        fact_id="00000000-0000-0000-0000-000000000004",
        source_digest="a" * 64,
    )
    second = E2aOwnershipFact.create(
        relative_path="entities/cat.md",
        fact_kind="entity",
        fact_id="00000000-0000-0000-0000-000000000004",
        source_digest="a" * 64,
    )

    assert first.ownership_id == second.ownership_id
    assert isinstance(UUID(first.ownership_id), UUID)
    with pytest.raises(ValueError, match="safe relative"):
        E2aOwnershipFact.create(
            relative_path="../entities/cat.md",
            fact_kind="entity",
            fact_id=first.fact_id,
            source_digest="a" * 64,
        )


def test_reconciliation_result_accepts_only_measured_outcomes() -> None:
    result = E2aReconciliationResult(
        outcome="acceptance_blocked",
        manifest_sha256="a" * 64,
        primary_dml_by_table=MappingProxyType({}),
        denylist_dml_counts=MappingProxyType({}),
        comparator_parity=None,
        stale_deletion_counts=MappingProxyType({}),
        cache_invalidation_counts=MappingProxyType({}),
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )
    assert result.outcome == "acceptance_blocked"
    with pytest.raises(ValueError, match="outcome"):
        E2aReconciliationResult(
            outcome="invented",  # type: ignore[arg-type]
            manifest_sha256="a" * 64,
            primary_dml_by_table=MappingProxyType({}),
            denylist_dml_counts=MappingProxyType({}),
            comparator_parity=None,
            stale_deletion_counts=MappingProxyType({}),
            cache_invalidation_counts=MappingProxyType({}),
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )


def test_canonical_freeze_is_recursive_and_hash_bound() -> None:
    nested = {"metadata": {"items": ["猫", {"enabled": True}]}}
    state = E2aDesiredState(
        corpus_manifest=nested,
        corpus_manifest_sha256=canonical_json_sha256(nested),
        parents=(),
        canonical_spans=(),
        vector_chunks=[],
        vector_chunk_span_links=[],
        tree_nodes=[],
        tree_node_span_links=[],
        manual_entities=[],
        manual_relations=[],
        manual_concepts=[],
        evidence_objects=[],
        evidence_links=[],
        ownership_facts=[],
        sync_state_rows=[],
        validation_metadata={"nested": {"tags": ["x"]}},
        provenance_metadata={},
    )

    nested["metadata"]["items"].append("mutated")
    assert (
        canonical_json(state.corpus_manifest)
        == '{"metadata":{"items":["猫",{"enabled":true}]}}'
    )
    assert state.vector_chunks == ()
    with pytest.raises(TypeError):
        state.validation_metadata["nested"]["tags"] += ("y",)  # type: ignore[index]


@pytest.mark.parametrize("path", ("C:fact.md", "aux.md", "name. ", "a\\b.md", "/a.md"))
def test_contract_paths_are_cross_platform_safe(path: str) -> None:
    with pytest.raises(ValueError, match="safe relative"):
        E2aManualFact(str(UUID(int=1)), "entity", path, "a" * 64)


def test_desired_state_retains_concepts_and_rejects_forged_cross_kind_identity() -> (
    None
):
    natural_key = "cat"
    fact = E2aManualFact(
        deterministic_id("concept", natural_key),
        "concept",
        "concepts/cat.md",
        "a" * 64,
        natural_key=natural_key,
    )
    state = _desired_state()
    manifest = {
        "artifacts": [
            *state.corpus_manifest["artifacts"],
            {
                "kind": "concept",
                "path": fact.relative_path,
                "identity": fact.fact_id,
                "source_digest": fact.source_digest,
            },
        ]
    }
    complete = E2aDesiredState(
        **{
            **state.__dict__,
            "corpus_manifest": manifest,
            "corpus_manifest_sha256": canonical_json_sha256(manifest),
            "manual_concepts": (fact,),
        }
    )
    assert complete.manual_concepts == (fact,)
    entity_natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    with pytest.raises(ValueError, match="manual fact identity"):
        E2aManualFact(
            fact.fact_id,
            "entity",
            "entities/cat.md",
            "a" * 64,
            natural_key=entity_natural_key,
        )


def test_manual_evidence_object_identity_is_deterministic_per_target_and_version() -> (
    None
):
    version_id = str(UUID(int=2))
    entity_id = str(UUID(int=4))

    first = E2aEvidenceObject.create(
        version_id=version_id,
        entity_id=entity_id,
        relation_id=None,
    )
    second = E2aEvidenceObject.create(
        version_id=version_id,
        entity_id=entity_id,
        relation_id=None,
    )
    other_version = E2aEvidenceObject.create(
        version_id=str(UUID(int=9)),
        entity_id=entity_id,
        relation_id=None,
    )

    assert first == second
    assert first.evidence_id != other_version.evidence_id
    assert isinstance(UUID(first.evidence_id), UUID)


def test_desired_state_requires_admitted_evidence_object_and_unique_link_identity() -> (
    None
):
    document_id = str(UUID(int=1))
    version_id = str(UUID(int=2))
    span_id = str(UUID(int=3))
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    entity_id = deterministic_id("entity", natural_key)
    fact = E2aManualFact(
        entity_id,
        "entity",
        "entities/cat.md",
        "a" * 64,
        natural_key=natural_key,
    )
    owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    parent = E2aParent(document_id, version_id, "raw/source.pair.json", "b" * 64)
    span = E2aSpan(document_id, version_id, span_id, 0, "body")
    evidence = E2aEvidenceObject.create(
        version_id=version_id,
        entity_id=entity_id,
        relation_id=None,
    )
    link = E2aEvidenceReference(
        document_id=document_id,
        version_id=version_id,
        span_id=span_id,
        entity_id=entity_id,
        relation_id=None,
        evidence_id=evidence.evidence_id,
        ownership_id=owner.ownership_id,
        ownership_scope_version_id="00000000-0000-0000-0000-000000000000",
    )
    base = _desired_state()
    values = {
        **base.__dict__,
        "corpus_manifest": {
            "artifacts": [
                {
                    "kind": "raw_pair",
                    "path": parent.relative_path,
                    "identity": f"{parent.document_id}:{parent.version_id}",
                    "canonical_hash": parent.canonical_hash,
                },
                {
                    "kind": "entity",
                    "path": fact.relative_path,
                    "identity": fact.fact_id,
                    "source_digest": fact.source_digest,
                },
            ]
        },
        "corpus_manifest_sha256": canonical_json_sha256(
            {
                "artifacts": [
                    {
                        "kind": "raw_pair",
                        "path": parent.relative_path,
                        "identity": f"{parent.document_id}:{parent.version_id}",
                        "canonical_hash": parent.canonical_hash,
                    },
                    {
                        "kind": "entity",
                        "path": fact.relative_path,
                        "identity": fact.fact_id,
                        "source_digest": fact.source_digest,
                    },
                ]
            }
        ),
        "parents": (parent,),
        "canonical_spans": (span,),
        "manual_entities": (fact,),
        "ownership_facts": (owner,),
        "evidence_objects": (evidence,),
        "evidence_links": (link,),
    }

    state = E2aDesiredState(**values)
    assert state.evidence_links == (link,)
    with pytest.raises(ValueError, match="duplicate evidence link"):
        E2aDesiredState(**{**values, "evidence_links": (link, link)})
    with pytest.raises(ValueError, match="admitted evidence"):
        E2aDesiredState(**{**values, "evidence_objects": ()})


@pytest.mark.parametrize(
    "value",
    ("\ud800", "safe\udfff"),
)
def test_canonical_e2a_strings_reject_surrogate_code_points(value: str) -> None:
    with pytest.raises(ValueError, match="Unicode scalar"):
        canonical_json({"value": value})
    with pytest.raises(ValueError, match="Unicode scalar"):
        E2aSpan(str(UUID(int=1)), str(UUID(int=2)), str(UUID(int=3)), 0, value)


def test_e2a_contracts_require_canonical_uuid_strings_before_identity_lookup() -> None:
    with pytest.raises(ValueError, match="UUID"):
        E2aSpan(
            "{00000000-0000-0000-0000-000000000001}",
            str(UUID(int=2)),
            str(UUID(int=3)),
            0,
            "safe",
        )
