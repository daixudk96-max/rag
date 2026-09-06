"""Wave-1 fifth-remediation tests using filesystem and catalog fakes only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf import e2a_disposable_catalog as catalog
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
from llamaindex_runtime.okf.sidecar import SpanSidecar

_DIGEST = "a" * 64
_GLOBAL_SCOPE = "00000000-0000-0000-0000-000000000000"


def _write_raw_pair(root: Path, name: str, document_id: str, version_id: str) -> None:
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    markdown = dump_raw_frontmatter(
        {
            "type": "raw",
            "doc_id": document_id,
            "version_id": version_id,
            "source_checksum": _DIGEST,
            "docling_version": "test",
            "generated_by": "test",
        },
        "body",
    ).encode("utf-8")
    sidecar = SpanSidecar(1, document_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    markdown_path = raw / f"{name}.md"
    markdown_path.write_bytes(markdown)
    markdown_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=markdown_path.name,
        markdown_bytes=markdown,
        sidecar_file=f"{name}.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(
            {
                "type": "raw",
                "doc_id": document_id,
                "version_id": version_id,
                "source_checksum": _DIGEST,
                "docling_version": "test",
                "generated_by": "test",
            },
            sidecar,
        ),
    )
    markdown_path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())


def test_real_raw_pair_corpus_rejects_a_version_shared_by_different_documents(
    tmp_path: Path,
) -> None:
    version_id = str(uuid4())
    _write_raw_pair(tmp_path, "one", str(uuid4()), version_id)
    _write_raw_pair(tmp_path, "two", str(uuid4()), version_id)

    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError, match="duplicate parent version"):
            e2a_admission.admit_e2a_corpus(authority)


def test_desired_state_rejects_a_canonical_span_without_exact_parent() -> None:
    state = _minimal_state(
        parents=(),
        spans=(E2aSpan(str(uuid4()), str(uuid4()), str(uuid4()), 0, "body"),),
    )

    with pytest.raises(ValueError, match="canonical span.*admitted parent"):
        E2aDesiredState(**state)


class _AttemptAuthority:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.calls: list[tuple[str, int | None]] = []

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.calls.append(("manifest", None))
        value = self.values["manifest"]
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]

    def read_document(self, _: tuple[str, ...], maximum: int | None = None) -> bytes:
        self.calls.append(("document", maximum))
        value = self.values["document"]
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.calls.append(("sidecar", None))
        value = self.values["sidecar"]
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]


def _budgeted(
    source: _AttemptAuthority, *, limit: int
) -> e2a_admission._BudgetedAuthority:
    value = e2a_admission._BudgetedAuthority(source)
    value._ledger = e2a_admission._ReadLedger(  # noqa: SLF001
        {"manifest": limit, "markdown": limit, "sidecar": limit, "manual": limit},
        {"manifest": 0, "markdown": 0, "sidecar": 0, "manual": 0},
    )
    return value


@pytest.mark.parametrize("attempt", ("manifest", "document", "sidecar"))
def test_read_ledger_reserves_full_cap_before_failed_delegate(attempt: str) -> None:
    cap = 16 * 1024 if attempt == "manifest" else 64 * 1024 * 1024
    source = _AttemptAuthority(
        {
            "manifest": b"ok",
            "document": b"ok",
            "sidecar": b"ok",
            attempt: ValueError("controlled"),
        }
    )
    authority = _budgeted(source, limit=cap)

    with pytest.raises(ValueError, match="controlled"):
        if attempt == "manifest":
            authority.read_manifest(("raw", "source.pair.json"))
        elif attempt == "document":
            authority.read_document(("raw", "source.md"), cap)
        else:
            authority.read_sidecar(("raw", "source.spans.json"))

    bucket = "markdown" if attempt == "document" else attempt
    assert authority._ledger.used[bucket] == cap  # noqa: SLF001
    assert [name for name, _ in source.calls] == [attempt]


def test_read_ledger_reserves_retry_m2_and_refunds_only_successful_bytes() -> None:
    cap = 16 * 1024
    source = _AttemptAuthority({"manifest": b"x", "document": b"x", "sidecar": b"x"})
    authority = _budgeted(source, limit=cap * 2)

    assert authority.read_manifest(("raw", "source.pair.json")) == b"x"
    assert authority.read_manifest(("raw", "source.pair.json")) == b"x"

    assert authority._ledger.used["manifest"] == 2  # noqa: SLF001
    assert source.calls == [("manifest", None), ("manifest", None)]


def test_read_ledger_blocks_before_delegate_when_remaining_is_below_cap() -> None:
    source = _AttemptAuthority({"manifest": b"x", "document": b"x", "sidecar": b"x"})
    authority = _budgeted(source, limit=(16 * 1024) - 1)

    with pytest.raises(ValueError, match="^e2a_admission_resource_limit$"):
        authority.read_manifest(("raw", "source.pair.json"))

    assert source.calls == []


@pytest.mark.parametrize("payload", (b"x" * ((16 * 1024) + 1), "not-bytes"))
def test_read_ledger_keeps_full_reservation_for_oversize_or_nonbytes(
    payload: object,
) -> None:
    source = _AttemptAuthority({"manifest": payload, "document": b"x", "sidecar": b"x"})
    authority = _budgeted(source, limit=16 * 1024)

    with pytest.raises(ValueError, match="^e2a_admission_resource_limit$"):
        authority.read_manifest(("raw", "source.pair.json"))

    assert authority._ledger.used["manifest"] == 16 * 1024  # noqa: SLF001


def _manual_graph() -> (
    tuple[E2aParent, E2aSpan, E2aManualFact, E2aOwnershipFact, E2aEvidenceObject]
):
    document_id, version_id, span_id = str(uuid4()), str(uuid4()), str(uuid4())
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    fact = E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        "entities/cat.md",
        _DIGEST,
        natural_key=natural_key,
    )
    owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    parent = E2aParent(document_id, version_id, "raw/source.pair.json", _DIGEST)
    span = E2aSpan(document_id, version_id, span_id, 0, "body")
    evidence = E2aEvidenceObject.create(
        version_id=version_id, entity_id=fact.fact_id, relation_id=None
    )
    return parent, span, fact, owner, evidence


def _minimal_state(
    *, parents: tuple[E2aParent, ...], spans: tuple[E2aSpan, ...]
) -> dict[str, object]:
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
            for parent in parents
        ]
    }
    return {
        "corpus_manifest": manifest,
        "corpus_manifest_sha256": canonical_json_sha256(manifest),
        "parents": parents,
        "canonical_spans": spans,
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
        "provenance_metadata": MappingProxyType({}),
    }


def test_local_e2a_evidence_link_dto_derives_all_wave2_cursor_values() -> None:
    parent, span, fact, owner, evidence = _manual_graph()
    link = E2aEvidenceReference(
        parent.document_id,
        parent.version_id,
        span.span_id,
        fact.fact_id,
        None,
        evidence.evidence_id,
        owner.ownership_id,
        owner.scope_version_id,
    )
    expected = deterministic_id(
        "manual_evidence_link",
        canonical_json(
            {
                "evidence_id": evidence.evidence_id,
                "ownership_id": owner.ownership_id,
                "ownership_scope_version_id": owner.scope_version_id,
                "source_kind": "manual_okf",
                "span_id": span.span_id,
                "target_id": fact.fact_id,
                "target_kind": "entity",
                "version_id": parent.version_id,
            }
        ),
    )

    assert link.evidence_link_id == expected
    assert link.source_kind == "manual_okf"
    assert link.confidence is None
    assert link.target_kind == "entity"
    assert link.target_id == fact.fact_id
    assert link.manual_entity_id == fact.fact_id
    assert link.manual_relation_id is None


def test_desired_state_rejects_forged_evidence_link_id_and_keeps_two_owners_distinct() -> (
    None
):
    parent, span, fact, first_owner, evidence = _manual_graph()
    second_owner = E2aOwnershipFact.create(
        relative_path="entities/cat-copy.md",
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest="b" * 64,
    )
    first = E2aEvidenceReference(
        parent.document_id,
        parent.version_id,
        span.span_id,
        fact.fact_id,
        None,
        evidence.evidence_id,
        first_owner.ownership_id,
        first_owner.scope_version_id,
    )
    second = replace(first, ownership_id=second_owner.ownership_id)
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
                    "kind": "entity",
                    "path": owner.relative_path,
                    "identity": owner.fact_id,
                    "source_digest": owner.source_digest,
                }
                for owner in (first_owner, second_owner)
            ],
        ]
    }
    values = {
        **_minimal_state(parents=(parent,), spans=(span,)),
        "corpus_manifest": manifest,
        "corpus_manifest_sha256": canonical_json_sha256(manifest),
        "manual_entities": (fact,),
        "ownership_facts": (first_owner, second_owner),
        "evidence_objects": (evidence,),
        "evidence_links": (first, second),
    }

    state = E2aDesiredState(**values)
    assert len({link.evidence_link_id for link in state.evidence_links}) == 2
    object.__setattr__(first, "evidence_link_id", str(uuid4()))
    with pytest.raises(ValueError, match="evidence link identity"):
        E2aDesiredState(**{**values, "evidence_links": (first, second)})


def test_migration_019_uses_manual_shadows_without_mutable_boolean_discriminator() -> (
    None
):
    migration = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    for required in (
        "manual_entity_id UUID",
        "manual_relation_id UUID",
        "source_kind <> 'manual_okf'",
        "manual_entity_id IS NULL",
        "manual_relation_id IS NULL",
        "manual_entity_id = entity_id",
        "manual_relation_id = relation_id",
        "FOREIGN KEY (ownership_id, manual_entity_id)",
        "FOREIGN KEY (ownership_id, manual_relation_id)",
        "FOREIGN KEY (version_id, evidence_id, manual_entity_id)",
        "FOREIGN KEY (version_id, evidence_id, manual_relation_id)",
        "idx_evidence_links_version_evidence_manual_entity",
        "idx_evidence_links_version_evidence_manual_relation",
    ):
        assert required in migration
    assert "is_manual_okf" not in migration


def test_acceptance_gate_rejects_truthy_or_raising_authorization_before_parsing() -> (
    None
):
    calls: list[str] = []

    class TruthyAuthority:
        authorized = 1

    class RaisingAuthority:
        @property
        def authorized(self) -> bool:
            raise RuntimeError("do not inspect target")

    def parse(*_: object) -> None:
        calls.append("parse")

    for authority in (TruthyAuthority(), RaisingAuthority()):
        assert (
            acceptance.run_disposable_migration_acceptance(
                authority, "not-a-target", "not-a-database", lambda _: None
            )
            == "blocked_not_executed"
        )
    assert calls == []


def test_definition_preserves_quoted_identifiers_and_case() -> None:
    assert acceptance._definition('FOREIGN KEY ("A") REFERENCES "Shadow"("A")') == (
        'FOREIGN KEY ("A") REFERENCES "Shadow"("A")'
    )


def test_acceptance_catalog_queries_include_oid_and_full_index_shape() -> None:
    source = Path(catalog.__file__).read_text(encoding="utf-8")

    for token in (
        "constraint_row.conrelid",
        "constraint_row.confrelid",
        "constraint_row.convalidated",
        "constraint_row.confmatchtype",
        "index_row.indisunique",
        "index_row.indisvalid",
        "index_row.indkey",
        "index_row.indrelid",
        "index_row.indexrelid",
    ):
        assert token in source


def test_apply_rollback_failure_has_a_distinct_redacted_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Authority:
        authorized = True

    class Cursor:
        def execute(self, _: str) -> None:
            raise RuntimeError("controlled")

    class Connection:
        def __init__(self) -> None:
            self.closed = 0

        def cursor(self) -> Cursor:
            return Cursor()

        def commit(self) -> None:
            raise AssertionError("not reached")

        def rollback(self) -> None:
            raise RuntimeError("rollback")

        def close(self) -> None:
            self.closed += 1

    connection = Connection()
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: None
    )

    result = acceptance.run_disposable_migration_acceptance(
        Authority(), "postgresql://fake", "fake", lambda _: connection
    )

    assert result == "executed_apply_rollback_failed"
    assert connection.closed == 1


def test_ledger_test_inputs_are_canonical_uuid_values() -> None:
    assert UUID(_GLOBAL_SCOPE).int == 0
