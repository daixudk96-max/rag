"""Phase-15 Wave-1 sixth-remediation regression coverage without live services."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aEvidenceObject,
    E2aEvidenceReference,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

_DIGEST = "a" * 64
_GLOBAL_SCOPE = "00000000-0000-0000-0000-000000000000"


class _ManualReadAuthority:
    def __init__(self) -> None:
        self.maximums: list[int | None] = []

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        return b"manifest"

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        return b"sidecar"

    def read_document(self, _: tuple[str, ...], maximum: int | None = None) -> bytes:
        self.maximums.append(maximum)
        return b"cat"


def test_manual_reads_are_caller_bounded_and_clip_to_remaining_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two small manual files fit even when the second gets a smaller delegate cap."""
    monkeypatch.setattr(e2a_admission, "MAX_E2A_MANUAL_DOCUMENT_BYTES", 4)
    source = _ManualReadAuthority()
    authority = e2a_admission._BudgetedAuthority(source)  # noqa: SLF001
    authority._ledger = e2a_admission._ReadLedger(  # noqa: SLF001
        {"manifest": 16, "markdown": 16, "sidecar": 16, "manual": 6},
        {"manifest": 0, "markdown": 0, "sidecar": 0, "manual": 0},
    )

    assert authority.read_document(("entities", "one.md"), 99) == b"cat"
    assert authority.read_document(("entities", "two.md"), 99) == b"cat"

    assert source.maximums == [4, 3]
    assert authority._ledger.used["manual"] == 6  # noqa: SLF001


def _raw_artifact(parent: E2aParent) -> dict[str, str]:
    return {
        "kind": "raw_pair",
        "path": parent.relative_path,
        "identity": f"{parent.document_id}:{parent.version_id}",
        "canonical_hash": parent.canonical_hash,
    }


def _entity(path: str, digest: str = _DIGEST) -> E2aManualFact:
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    return E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        path,
        digest,
        natural_key=natural_key,
    )


def _state_values() -> (
    tuple[dict[str, object], E2aManualFact, E2aOwnershipFact, E2aParent, E2aSpan]
):
    document_id, version_id, span_id = str(uuid4()), str(uuid4()), str(uuid4())
    parent = E2aParent(document_id, version_id, "raw/source.pair.json", _DIGEST)
    span = E2aSpan(document_id, version_id, span_id, 0, "cat")
    fact = _entity("entities/cat.md")
    owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    manifest = {
        "artifacts": [
            _raw_artifact(parent),
            {
                "kind": "entity",
                "path": owner.relative_path,
                "identity": owner.fact_id,
                "source_digest": owner.source_digest,
            },
        ]
    }
    return (
        {
            "corpus_manifest": manifest,
            "corpus_manifest_sha256": canonical_json_sha256(manifest),
            "parents": (parent,),
            "canonical_spans": (span,),
            "vector_chunks": (),
            "vector_chunk_span_links": (),
            "tree_nodes": (),
            "tree_node_span_links": (),
            "manual_entities": (fact,),
            "manual_relations": (),
            "manual_concepts": (),
            "evidence_objects": (),
            "evidence_links": (),
            "ownership_facts": (owner,),
            "sync_state_rows": (),
            "validation_metadata": {},
            "provenance_metadata": {},
        },
        fact,
        owner,
        parent,
        span,
    )


def test_direct_dto_requires_bidirectional_raw_manual_and_evidence_closure() -> None:
    values, fact, owner, parent, span = _state_values()

    assert E2aDesiredState(**values).ownership_facts == (owner,)
    with pytest.raises(ValueError, match="raw-pair artifact"):
        E2aDesiredState(
            **{
                **values,
                "corpus_manifest": {
                    "artifacts": values["corpus_manifest"]["artifacts"][1:]
                },  # type: ignore[index]
                "corpus_manifest_sha256": canonical_json_sha256(
                    {"artifacts": values["corpus_manifest"]["artifacts"][1:]}  # type: ignore[index]
                ),
            }
        )
    with pytest.raises(ValueError, match="ownership"):
        E2aDesiredState(**{**values, "ownership_facts": ()})

    evidence = E2aEvidenceObject.create(
        version_id=parent.version_id, entity_id=fact.fact_id, relation_id=None
    )
    with pytest.raises(ValueError, match="evidence object requires a span-backed link"):
        E2aDesiredState(**{**values, "evidence_objects": (evidence,)})

    link = E2aEvidenceReference(
        parent.document_id,
        parent.version_id,
        span.span_id,
        fact.fact_id,
        None,
        evidence.evidence_id,
        owner.ownership_id,
        _GLOBAL_SCOPE,
    )
    assert E2aDesiredState(
        **{**values, "evidence_objects": (evidence,), "evidence_links": (link,)}
    ).evidence_links == (link,)


def test_direct_dto_keeps_representative_fact_separate_from_all_owner_artifacts() -> (
    None
):
    values, fact, first_owner, _, _ = _state_values()
    second_owner = E2aOwnershipFact.create(
        relative_path="entities/cat-copy.md",
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest="b" * 64,
    )
    manifest = {
        "artifacts": [
            *values["corpus_manifest"]["artifacts"],  # type: ignore[index]
            {
                "kind": "entity",
                "path": second_owner.relative_path,
                "identity": fact.fact_id,
                "source_digest": second_owner.source_digest,
            },
        ]
    }

    state = E2aDesiredState(
        **{
            **values,
            "corpus_manifest": manifest,
            "corpus_manifest_sha256": canonical_json_sha256(manifest),
            "ownership_facts": (first_owner, second_owner),
        }
    )

    assert state.manual_entities == (fact,)
    assert state.ownership_facts == (first_owner, second_owner)


def _write_raw_pair(
    root: Path, document_id: str, version_id: str, span_id: str
) -> None:
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    frontmatter = {
        "type": "raw",
        "doc_id": document_id,
        "version_id": version_id,
        "source_checksum": _DIGEST,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "cat").encode("utf-8")
    sidecar = SpanSidecar(1, document_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    markdown_path = raw / "source.md"
    markdown_path.write_bytes(markdown)
    markdown_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    markdown_path.with_suffix(".pair.json").write_bytes(
        GenerationManifest.create(
            markdown_file="source.md",
            markdown_bytes=markdown,
            sidecar_file="source.spans.json",
            sidecar_bytes=sidecar_bytes,
            canonical_hash=canonical_hash(frontmatter, sidecar),
        ).to_bytes()
    )


def test_bundle_authority_retains_two_compatible_entity_owners_and_artifacts(
    tmp_path: Path,
) -> None:
    document_id, version_id, span_id = str(uuid4()), str(uuid4()), str(uuid4())
    _write_raw_pair(tmp_path, document_id, version_id, span_id)
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    entity_id = deterministic_id("entity", natural_key)
    for name in ("cat-primary", "cat-copy"):
        target = tmp_path / "entities" / f"{name}.md"
        target.parent.mkdir(exist_ok=True)
        target.write_text(
            "---\n"
            "type: entity\n"
            "title: Cat\n"
            "timestamp: '2026-07-18T00:00:00Z'\n"
            f"canonical_entity_id: {entity_id}\n"
            "entity_type: animal\n"
            "---\ncat\n",
            encoding="utf-8",
        )

    with BundleAuthority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)

    assert len(state.manual_entities) == 1
    assert {owner.relative_path for owner in state.ownership_facts} == {
        "entities/cat-primary.md",
        "entities/cat-copy.md",
    }
    assert {
        str(item["path"])
        for item in state.corpus_manifest["artifacts"]  # type: ignore[index]
        if item["kind"] == "entity"  # type: ignore[index]
    } == {"entities/cat-primary.md", "entities/cat-copy.md"}


def test_constraint_comparison_tolerates_only_outer_check_parentheses() -> None:
    expected = acceptance._ConstraintExpectation(
        "links", "check_links", "c", "CHECK (flag = 'Case Sensitive'::text)"
    )
    row = (
        "links",
        "check_links",
        "c",
        "CHECK ((( flag = 'Case Sensitive'::text )))",
        "",
        "",
        41,
        0,
        True,
        "a",
        "s",
        "a",
        False,
        False,
        0,
    )

    acceptance._validate_constraint_row(row, expected, {"links": 41})


class _CloseFailureConnection:
    def __init__(self, *, rollback_fails: bool) -> None:
        self.rollback_fails = rollback_fails
        self.closed = 0

    def cursor(self) -> object:
        class Cursor:
            def execute(self, _: str) -> None:
                raise RuntimeError("apply")

        return Cursor()

    def commit(self) -> None:
        raise AssertionError("not reached")

    def rollback(self) -> None:
        if self.rollback_fails:
            raise RuntimeError("rollback")

    def close(self) -> None:
        self.closed += 1
        raise RuntimeError("close")


def test_apply_rollback_failure_survives_close_failure_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _CloseFailureConnection(rollback_fails=True)
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: None
    )

    class Authority:
        authorized = True

    assert (
        acceptance.run_disposable_migration_acceptance(
            Authority(), "postgresql://not-used", "not-used", lambda _: connection
        )
        == "executed_apply_rollback_failed"
    )
    assert connection.closed == 1


def test_migration_019_is_one_schema_bound_three_state_do_block() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    assert migration.count("DO $e2a019$") == 1
    assert "fresh_signature :=" in migration
    assert "final_signature :=" in migration
    assert "fresh_signature AND final_signature" in migration
    assert "NOT fresh_signature AND NOT final_signature" in migration
    assert "e2a_preflight_malformed_partial" in migration
    assert "schema_oid" in migration
    assert "schema_name" in migration
    assert "format('%I.%I', schema_name" in migration


def test_migration_019_preserves_reused_indexes_and_validates_before_audit_replace() -> (
    None
):
    migration = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    for reused in (
        "idx_evidence_links_version",
        "idx_evidence_links_entity",
        "idx_evidence_links_relation",
    ):
        assert f"CREATE INDEX {reused}" not in migration
        assert f"CREATE UNIQUE INDEX {reused}" not in migration
    assert "old_audit_check_matches" in migration
    assert "DROP CONSTRAINT %I" in migration
    assert "chk_okf_rebuild_failure_audit_phase" in migration


def test_migration_019_final_data_query_has_from_and_shape_bound_cascade_selector() -> (
    None
):
    migration = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    assert "SELECT 1 FROM %s AS link" in migration
    assert "constraint_row.confdeltype = 'c'" in migration
    assert "constraint_row.confdeltype IN ('c', 'a')" in migration
    assert "constraint_row.conrelid = evidence_links_oid" in migration
    assert "constraint_row.conkey = ARRAY" in migration
    assert "constraint_row.confkey = ARRAY" in migration


def _write_raw_pair_with_span(
    root: Path, document_id: str, version_id: str, span_id: str
) -> str:
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    frontmatter = {
        "type": "raw",
        "doc_id": document_id,
        "version_id": version_id,
        "source_checksum": _DIGEST,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "cat").encode("utf-8")
    seed_span = SpanRecord(span_id, None, (), 0, "cat")
    canonical_span_id = recompute_span_id(
        seed_span, doc_id=document_id, version_id=version_id
    )
    sidecar = SpanSidecar(
        1,
        document_id,
        version_id,
        (SpanRecord(canonical_span_id, None, (), 0, "cat"),),
    )
    sidecar_bytes = sidecar.to_bytes()
    markdown_path = raw / "source.md"
    markdown_path.write_bytes(markdown)
    markdown_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    markdown_path.with_suffix(".pair.json").write_bytes(
        GenerationManifest.create(
            markdown_file="source.md",
            markdown_bytes=markdown,
            sidecar_file="source.spans.json",
            sidecar_bytes=sidecar_bytes,
            canonical_hash=canonical_hash(frontmatter, sidecar),
        ).to_bytes()
    )
    return canonical_span_id


def test_bundle_authority_admits_qualified_negated_relation_with_span_evidence(
    tmp_path: Path,
) -> None:
    document_id, version_id, span_id = str(uuid4()), str(uuid4()), str(uuid4())
    span_id = _write_raw_pair_with_span(tmp_path, document_id, version_id, span_id)
    subject_id, object_id = str(uuid4()), str(uuid4())
    natural_key = canonical_json(
        {
            "subject_entity_id": subject_id,
            "predicate": "protects",
            "object_entity_id": object_id,
        }
    )
    relation_id = deterministic_id("relation", natural_key)
    relation = tmp_path / "relations" / "cat-protects.md"
    relation.parent.mkdir(exist_ok=True)
    relation.write_text(
        "---\n"
        "type: relation\n"
        f"subject_entity_id: {subject_id}\n"
        "predicate: protects\n"
        f"object_entity_id: {object_id}\n"
        "timestamp: '2026-07-18T00:00:00Z'\n"
        "negation: true\n"
        "condition: 'during winter'\n"
        "direction: outbound\n"
        "confidence: 0.75\n"
        "qualifiers:\n"
        "  valid_time:\n"
        "    start: '2026-01-01T00:00:00Z'\n"
        "  label: '猫'\n"
        "evidence:\n"
        f"  - document_id: {document_id}\n"
        f"    version_id: {version_id}\n"
        f"    span_id: {span_id}\n"
        "---\ncat protects\n",
        encoding="utf-8",
    )

    with BundleAuthority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)

    assert len(state.manual_relations) == 1
    fact = state.manual_relations[0]
    assert fact.fact_id == relation_id
    assert dict(fact.qualifiers) == {
        "negation": True,
        "condition": "during winter",
        "direction": "outbound",
        "confidence": 0.75,
        "qualifiers": {
            "valid_time": {"start": "2026-01-01T00:00:00Z"},
            "label": "猫",
        },
    }
    assert len(state.ownership_facts) == 1
    assert len(state.evidence_objects) == len(state.evidence_links) == 1
    assert state.evidence_links[0].relation_id == relation_id
    assert state.evidence_links[0].entity_id is None


def test_unauthorized_acceptance_never_invokes_production_parser_or_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class UnauthorizedAuthority:
        authorized = False

    def parser(*_: object) -> None:
        calls.append("parser")
        raise AssertionError("parser must not be called")

    def connector(*_: object) -> object:
        calls.append("connector")
        raise AssertionError("connector must not be called")

    monkeypatch.setattr(acceptance, "parse_disposable_postgresql_target", parser)

    assert (
        acceptance.run_disposable_migration_acceptance(
            UnauthorizedAuthority(), "not-a-target", "not-a-database", connector
        )
        == "blocked_not_executed"
    )
    assert calls == []


def test_migration_019_static_contract_covers_state_partition_and_final_inventory() -> (
    None
):
    migration = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    assert migration.count("DO $e2a019$") == 1
    assert "fresh_signature :=" in migration
    assert "final_signature :=" in migration
    assert "fresh_signature AND final_signature" in migration
    assert "NOT fresh_signature AND NOT final_signature" in migration
    assert "schema_oid := pg_catalog.pg_my_temp_schema()" not in migration
    assert "schema_oid pg_catalog.oid :=" in migration
    assert "SELECT pg_catalog.pg_namespace.oid" in migration
    assert "schema_name := pg_catalog.current_schema()" in migration
    assert "format('%I.%I', schema_name" in migration
    assert "pg_catalog.pg_constraint" in migration
    assert "pg_catalog.pg_attribute" in migration
    assert "SELECT 1 FROM %s AS link" in migration
    assert "constraint_row.confdeltype IN ('c', 'a')" in migration
    assert "constraint_row.confdeltype = 'c'" in migration
    assert "old_audit_check_matches" in migration
    assert "VALIDATE CONSTRAINT %I" in migration
    assert "e2a_preflight_malformed_partial" in migration
    assert "e2a_preflight_final_catalog_drift" in migration
    for inventory_guard in (
        "expected_final_columns",
        "expected_final_constraints",
        "expected_final_indexes",
        "pg_catalog.pg_get_constraintdef",
        "constraint_row.conkey = ARRAY",
        "constraint_row.confkey = ARRAY",
        "pg_catalog.unnest(expected_final_indexes.columns) WITH ORDINALITY",
    ):
        assert inventory_guard in migration
    assert "pg_catalog.smallint[]" not in migration
    for vector in ("indkey", "indclass", "indcollation", "indoption"):
        assert f"index_row.{vector}[column_row.ordinality - 1]" in migration
    for reused in (
        "idx_evidence_links_version",
        "idx_evidence_links_entity",
        "idx_evidence_links_relation",
    ):
        assert f"CREATE INDEX {reused}" not in migration
        assert f"CREATE UNIQUE INDEX {reused}" not in migration
    for expected in acceptance._EXPECTED_019_CONSTRAINT_ROWS:  # noqa: SLF001
        assert expected.name in migration
    for expected in acceptance._EXPECTED_019_INDEX_ROWS:  # noqa: SLF001
        assert expected.name in migration
    for expression in (
        "ANY (ARRAY",
        "::text",
        "::uuid",
        "num_nonnulls(entity_id, relation_id) = 1",
    ):
        assert expression in migration


def test_predicate_comparison_strips_only_redundant_outer_parentheses() -> None:
    expectation = acceptance._IndexExpectation(
        "links",
        "idx_links_manual",
        "version_id,entity_id",
        True,
        "(source_kind = 'Manual_OKF'::text) AND (entity_id IS NOT NULL)",
        "CREATE UNIQUE INDEX idx_links_manual ON links USING btree (version_id, entity_id) WHERE (source_kind = 'Manual_OKF'::text) AND (entity_id IS NOT NULL)",
    )
    row = (
        "links",
        "idx_links_manual",
        41,
        52,
        True,
        True,
        "version_id,entity_id",
        "",
        "(((source_kind = 'Manual_OKF'::text) AND (entity_id IS NOT NULL)))",
        "CREATE UNIQUE INDEX idx_links_manual ON links USING btree (version_id, entity_id) WHERE (source_kind = 'Manual_OKF'::text) AND (entity_id IS NOT NULL)",
    )

    acceptance._validate_index_row(row, expectation, {"links": 41})
