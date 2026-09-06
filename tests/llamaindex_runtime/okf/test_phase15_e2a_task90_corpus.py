"""Task #90 default-collected corpus + evidence remediation suite (RED/GREEN).

Security review remediation (two MEDIUM findings):

1. The live corpus builder previously wrote ONLY ``relations/alpha.md``; the
   live desired state had empty parents/spans/vector/tree yet the live
   selector documented M-D-S-M. This suite requires the live corpus builder
   (``_write_manual_relation_corpus`` in the non-collected live cells) to
   emit a complete strict M-D-S-M raw pair (markdown + spans sidecar + pair
   manifest) with at least one real canonical span, two manual endpoint
   entities, and a manual relation whose ``evidence`` frontmatter resolves to
   that admitted doc/version/span.
   After admission the parents / canonical spans / manual entities / manual
   relations / ownership / evidence objects / evidence links are all non-empty
   with exact expectations, and the evidence links really reference admitted
   spans/versions/documents.

2. Manual evidence previously had only an unresolved fail-closed test; the
   positive ``evidence_objects`` / ``evidence_links`` were always empty, so
   the determinism / evidence claim was vacuous. This suite adds a positive
   determinism proof that honestly distinguishes the two ordering classes:

   - natural / reverse / seeded-shuffle file-creation order is byte-identical
     and must admit to a FULL ``E2aDesiredState`` equality with an identical
     corpus manifest SHA;
   - evidence-list frontmatter byte reorder keeps the evidence_id /
     evidence_link_id / span / document / target relation identity SETS
     stable and deterministic, but the relation ``source_digest`` and the
     corpus manifest SHA differ BY DESIGN because the relation's raw bytes
     changed. No cryptographic byte-identity claim is made for reordered
     frontmatter lists.

   All evidence tuples are NON-EMPTY in every admitted state.

No database, no Docker, and no authorized live selector invocation is
performed here; admission is the pure in-process BundleAuthority pipeline.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._phase15_e2a_task90_live_cells import (
    _OBJECT_ENTITY_TITLE,
    _OBJECT_ENTITY_TYPE,
    _SUBJECT_ENTITY_TITLE,
    _SUBJECT_ENTITY_TYPE,
    _is_complete_desired_state,
    _register_task90_parents,
    _relation_endpoints_resolve_to_admitted_entities,
    _task90_parent_identities,
    _write_manual_relation_corpus,
)

_DIGEST = "a" * 64
_PLACEHOLDER_SPAN_ID = "00000000-0000-0000-0000-000000000000"


def _computed_span_id(doc_id: str, version_id: str, offset: int) -> str:
    """Compute the canonical S_okf identity for a fixed coordinate span."""
    return recompute_span_id(
        SpanRecord(
            span_id=_PLACEHOLDER_SPAN_ID,
            page_no=1,
            heading_path=("Introduction",),
            offset=offset,
            text="Canonical span text.",
        ),
        doc_id=doc_id,
        version_id=version_id,
    )


def _span_records(
    doc_id: str, version_id: str, offsets: tuple[int, ...]
) -> tuple[SpanRecord, ...]:
    """Build strict schema-v1 span records whose ids match canonical coordinates."""
    return tuple(
        SpanRecord(
            span_id=_computed_span_id(doc_id, version_id, offset),
            page_no=1,
            heading_path=("Introduction",),
            offset=offset,
            text="Canonical span text.",
        )
        for offset in offsets
    )


def _raw_pair(
    root: Path,
    name: str,
    doc_id: str,
    version_id: str,
    *,
    offsets: tuple[int, ...] = (),
) -> None:
    """Write a complete strict M-D-S-M raw pair with the given canonical spans."""
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": _DIGEST,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "Raw corpus body.\n").encode("utf-8")
    sidecar = SpanSidecar(
        schema_version=1,
        doc_id=doc_id,
        version_id=version_id,
        spans=_span_records(doc_id, version_id, offsets),
    )
    sidecar_bytes = sidecar.to_bytes()
    md_path = raw / f"{name}.md"
    md_path.write_bytes(markdown)
    md_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=md_path.name,
        markdown_bytes=markdown,
        sidecar_file=f"{name}.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    )
    md_path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())


def _manual_relation(
    root: Path,
    name: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    *,
    evidence: tuple[dict[str, str], ...] = (),
) -> None:
    """Write a strict manual-relation markdown with an optional evidence list."""
    rel_dir = root / "relations"
    rel_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: relation",
        f"subject_entity_id: {subject_id}",
        f"predicate: {predicate}",
        f"object_entity_id: {object_id}",
        "timestamp: '2026-07-15T09:30:00Z'",
        "negation: false",
    ]
    if evidence:
        lines.append("evidence:")
        for item in evidence:
            lines.append(f"  - document_id: {item['document_id']}")
            lines.append(f"    version_id: {item['version_id']}")
            lines.append(f"    span_id: {item['span_id']}")
    lines.append("---")
    lines.append("Fact body.")
    (rel_dir / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _admit(root: Path) -> E2aDesiredState:
    with BundleAuthority(root) as authority:
        return e2a_admission.admit_e2a_corpus(authority)


def _evidence_links_reference_admitted_spans(state: E2aDesiredState) -> bool:
    span_keys = {
        (span.document_id, span.version_id, span.span_id)
        for span in state.canonical_spans
    }
    return bool(state.evidence_links) and all(
        (link.document_id, link.version_id, link.span_id) in span_keys
        for link in state.evidence_links
    )


def test_live_corpus_builder_admits_complete_raw_pair_and_evidence(
    tmp_path: Path,
) -> None:
    """RED: the live corpus builder must produce a strict raw pair + resolved evidence."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)

    # A complete M-D-S-M raw pair with one real canonical span.
    assert len(state.parents) == 1
    assert len(state.canonical_spans) == 1
    # Two manual endpoint entities plus one manual relation, each carrying
    # its own ownership provenance (three ownership facts total).
    assert len(state.manual_entities) == 2
    assert len(state.manual_relations) == 1
    assert len(state.ownership_facts) == 3
    # Resolved evidence is present (not a vacuous empty tuple).
    assert len(state.evidence_objects) == 1
    assert len(state.evidence_links) == 1
    # Honest production deferred_wave2: admission creates no vector/tree/sync rows.
    assert state.vector_chunks == ()
    assert state.tree_nodes == ()
    assert state.sync_state_rows == ()
    assert state.corpus_manifest_sha256 == e2a_admission.admit_e2a_corpus_hash(state)


def test_live_corpus_builder_evidence_references_admitted_span(
    tmp_path: Path,
) -> None:
    """RED: the live evidence link must resolve to the admitted span/version/doc."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)

    assert state.evidence_links, "the live corpus must admit a resolved evidence link"
    assert _evidence_links_reference_admitted_spans(state)
    link = state.evidence_links[0]
    relation = state.manual_relations[0]
    assert link.relation_id == relation.fact_id
    assert any(
        obj.evidence_id == link.evidence_id and obj.version_id == link.version_id
        for obj in state.evidence_objects
    )


def _admitted_without_entities(state: E2aDesiredState) -> E2aDesiredState:
    """Return a valid desired state with the admitted entity facts removed.

    ``E2aDesiredState`` is frozen and re-validates ownership/manifest closure
    in ``__post_init__``, so removing the two entity facts also requires
    dropping their ownership rows and removing the entity artifacts from the
    canonical manifest. The relation, its evidence, and its ownership remain.
    """
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            artifact
            for artifact in state.corpus_manifest["artifacts"]
            if artifact.get("kind") != "entity"
        ],
    }
    return replace(
        state,
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        manual_entities=(),
        ownership_facts=tuple(
            owner for owner in state.ownership_facts if owner.fact_kind != "entity"
        ),
    )


def test_live_corpus_builder_relation_endpoints_resolve_to_admitted_entities(
    tmp_path: Path,
) -> None:
    """RED: every admitted relation endpoint must resolve to an admitted entity.

    The live corpus must admit the two endpoint entities so the relation's
    subject/object ids are owned manual facts, not dangling FK targets.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)
    assert _relation_endpoints_resolve_to_admitted_entities(state) is True


def test_relation_endpoint_integrity_helper_rejects_missing_entities(
    tmp_path: Path,
) -> None:
    """RED: the integrity helper must fail closed when the admitted entities
    are removed from an otherwise complete admitted state."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)
    without_entities = _admitted_without_entities(state)
    assert _relation_endpoints_resolve_to_admitted_entities(without_entities) is False


def test_live_corpus_relation_endpoint_ids_are_production_derived_entity_ids(
    tmp_path: Path,
) -> None:
    """RED: the relation endpoints must equal the production-derived entity ids.

    Each entity canonical id is derived from normalized lowercase ASCII
    title/entity_type constants via the production deterministic-id contract;
    the relation frontmatter must reference exactly those derived ids, never
    arbitrary hardcoded UUIDs.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)
    relation = state.manual_relations[0]
    natural = json.loads(relation.natural_key)
    expected_subject = deterministic_id(
        "entity",
        canonical_json(
            {"title": _SUBJECT_ENTITY_TITLE, "entity_type": _SUBJECT_ENTITY_TYPE}
        ),
    )
    expected_object = deterministic_id(
        "entity",
        canonical_json(
            {"title": _OBJECT_ENTITY_TITLE, "entity_type": _OBJECT_ENTITY_TYPE}
        ),
    )
    assert expected_subject != expected_object
    assert natural["subject_entity_id"] == expected_subject
    assert natural["object_entity_id"] == expected_object


def test_live_corpus_builder_completeness_predicate_requires_resolved_evidence(
    tmp_path: Path,
) -> None:
    """RED: the completeness predicate must require the raw pair + resolved evidence."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)

    # The state shape itself must be complete before the predicate is consulted.
    assert len(state.parents) == 1
    assert len(state.canonical_spans) >= 1
    assert len(state.evidence_objects) >= 1
    assert len(state.evidence_links) >= 1
    assert _is_complete_desired_state(state) is True


def test_admission_evidence_deterministic_across_file_and_evidence_orders(
    tmp_path: Path,
) -> None:
    """GREEN: non-empty evidence is deterministic across all corpus orderings.

    The SAME corpus (identical doc/version/span UUIDs, two raw pairs each
    carrying one canonical span, one relation with two resolved evidence
    entries) is admitted under two distinct ordering classes, and the
    determinism claim is stated honestly per class:

    - Byte-identical file-creation order (natural vs reverse vs seeded
      shuffle): the FULL ``E2aDesiredState`` -- every tuple, digest, and
      identity -- is byte-identical, including the corpus manifest SHA.
    - Evidence-list frontmatter byte reorder (forward vs reversed evidence
      list in the relation markdown): the evidence_id / evidence_link_id /
      span / document / target relation identity SETS are stable and
      deterministic, but the relation ``source_digest`` and the corpus
      manifest SHA differ BY DESIGN because the relation's raw bytes
      changed. No byte-identity claim is made for reordered frontmatter
      lists.

    The full state is compared (not just two empty evidence tuples), and
    every evidence tuple is NON-EMPTY.
    """
    pair_ant = (str(uuid4()), str(uuid4()))
    pair_zebra = (str(uuid4()), str(uuid4()))
    ant_span = _computed_span_id(pair_ant[0], pair_ant[1], 0)
    zebra_span = _computed_span_id(pair_zebra[0], pair_zebra[1], 10)

    def build(
        root: Path, *, evidence_order: tuple[dict[str, str], ...]
    ) -> E2aDesiredState:
        _raw_pair(root, "ant", *pair_ant, offsets=(0,))
        _raw_pair(root, "zebra", *pair_zebra, offsets=(10,))
        _manual_relation(
            root,
            "alpha",
            "00000000-0000-0000-0000-000000001f95",
            "supports",
            "00000000-0000-0000-0000-000000001fa2",
            evidence=evidence_order,
        )
        return _admit(root)

    evidence_forward = (
        {
            "document_id": pair_ant[0],
            "version_id": pair_ant[1],
            "span_id": ant_span,
        },
        {
            "document_id": pair_zebra[0],
            "version_id": pair_zebra[1],
            "span_id": zebra_span,
        },
    )
    evidence_reversed = (evidence_forward[1], evidence_forward[0])

    baseline_root = tmp_path / "natural"
    baseline_root.mkdir()
    baseline = build(baseline_root, evidence_order=evidence_forward)
    # Non-empty evidence: exactly two resolved objects and two links.
    assert len(baseline.evidence_objects) == 2
    assert len(baseline.evidence_links) == 2
    assert _evidence_links_reference_admitted_spans(baseline)
    relation = baseline.manual_relations[0]
    assert all(link.relation_id == relation.fact_id for link in baseline.evidence_links)

    # Reverse file-creation order (relation written before the two raw pairs).
    reverse_root = tmp_path / "reverse"
    reverse_root.mkdir()
    _manual_relation(
        reverse_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        evidence=evidence_forward,
    )
    _raw_pair(reverse_root, "zebra", *pair_zebra, offsets=(10,))
    _raw_pair(reverse_root, "ant", *pair_ant, offsets=(0,))
    reverse_state = _admit(reverse_root)
    assert reverse_state == baseline

    # Reversed evidence-list order (natural file order). The evidence ids,
    # evidence link ids, span references, and target relation identity are
    # all deterministic regardless of the order the evidence list appears in
    # the frontmatter. The relation's raw bytes differ, so its content-bound
    # source_digest (and the manifest embedding it) differs by design -- the
    # same honest boundary already pinned by the frontmatter key-order test.
    ev_root = tmp_path / "evidence_reversed"
    ev_root.mkdir()
    ev_rev_state = build(ev_root, evidence_order=evidence_reversed)
    assert {link.evidence_link_id for link in ev_rev_state.evidence_links} == {
        link.evidence_link_id for link in baseline.evidence_links
    }
    assert {obj.evidence_id for obj in ev_rev_state.evidence_objects} == {
        obj.evidence_id for obj in baseline.evidence_objects
    }
    assert {link.span_id for link in ev_rev_state.evidence_links} == {
        link.span_id for link in baseline.evidence_links
    }
    assert {link.document_id for link in ev_rev_state.evidence_links} == {
        pair_ant[0],
        pair_zebra[0],
    }
    assert all(
        link.relation_id == relation.fact_id for link in ev_rev_state.evidence_links
    )
    # Honest content-bound boundary: different evidence-list byte order yields
    # a different raw source_digest (and thus manifest SHA), never a claim of
    # cryptographic byte-identity across reordered frontmatter lists.
    assert (
        ev_rev_state.manual_relations[0].source_digest
        != baseline.manual_relations[0].source_digest
    )
    assert ev_rev_state.corpus_manifest_sha256 != baseline.corpus_manifest_sha256

    # Seeded shuffle of the three logical files (bytes identical to baseline).
    for seed in (3, 11):
        sh_root = tmp_path / f"shuffle_{seed}"
        sh_root.mkdir()
        order = ["ant", "zebra", "alpha"]
        random.Random(seed).shuffle(order)
        for item in order:
            if item == "ant":
                _raw_pair(sh_root, "ant", *pair_ant, offsets=(0,))
            elif item == "zebra":
                _raw_pair(sh_root, "zebra", *pair_zebra, offsets=(10,))
            else:
                _manual_relation(
                    sh_root,
                    "alpha",
                    "00000000-0000-0000-0000-000000001f95",
                    "supports",
                    "00000000-0000-0000-0000-000000001fa2",
                    evidence=evidence_forward,
                )
        assert _admit(sh_root) == baseline

    # Stable manifest SHA across every byte-identical file-creation ordering
    # (natural, reverse, seeded shuffle). The evidence-list-order variant is
    # byte-different and is honestly excluded above.
    expected_manifest_sha = baseline.corpus_manifest_sha256
    assert reverse_state.corpus_manifest_sha256 == expected_manifest_sha

    # Stable evidence identities across every ordering (file-creation and
    # evidence-list alike).
    assert {link.evidence_link_id for link in baseline.evidence_links} == {
        link.evidence_link_id for link in reverse_state.evidence_links
    }
    assert {obj.evidence_id for obj in baseline.evidence_objects} == {
        obj.evidence_id for obj in ev_rev_state.evidence_objects
    }
    assert {link.document_id for link in baseline.evidence_links} == {
        pair_ant[0],
        pair_zebra[0],
    }
    assert {link.span_id for link in baseline.evidence_links} == {
        ant_span,
        zebra_span,
    }


# =============================================================================
# Parent-registration harness precondition (Task #90 remediation)
# =============================================================================
#
# Production ``E2aReconciler._acquire_scope_locks`` runs a ``FOR UPDATE`` on
# ``document_versions`` for every admitted parent and fail-closes unless it
# finds EXACTLY one row. The live harness therefore must register each
# admitted parent (one ``documents`` row + one ``document_versions`` row) on
# a fresh caller-owned connection BEFORE the first reconcile. These pure
# contract tests pin that registration shape without any database/Docker.


class _RecordingCursor:
    """Pure in-memory cursor recording every (statement, parameters) pair."""

    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: object | None = None) -> None:
        params = tuple(parameters) if parameters is not None else ()
        self.executions.append((statement, params))


class _RecordingConnection:
    """Pure in-memory connection: the helper never creates its own connection."""

    def __init__(self) -> None:
        self._cursor = _RecordingCursor()
        self.commit_calls = 0
        self.close_calls = 0

    def cursor(self) -> _RecordingCursor:
        return self._cursor

    def commit(self) -> None:
        self.commit_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    @property
    def executions(self) -> list[tuple[str, tuple[object, ...]]]:
        return self._cursor.executions


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _inserts(
    conn: _RecordingConnection, table: str
) -> list[tuple[str, tuple[object, ...]]]:
    target = f"insert into {table} "
    return [
        (statement, params)
        for statement, params in conn.executions
        if _normalized(statement).startswith("insert into")
        and target in _normalized(statement)
    ]


def _empty_parents_desired_state() -> E2aDesiredState:
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
        validation_metadata={},
        provenance_metadata={},
    )


def test_task90_register_parents_pins_exact_parameterized_inserts_and_commit(
    tmp_path: Path,
) -> None:
    """RED: registering the admitted parent emits exactly one ``documents``
    INSERT and one ``document_versions`` INSERT, fully parameterized, with a
    deterministic valid 64-hex content hash derived from the admitted parent,
    then commits the caller-owned connection.

    This is the harness precondition for the production
    ``E2aReconciler._acquire_scope_locks`` FOR UPDATE row requirement.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    state = _admit(root)
    parent = state.parents[0]

    conn = _RecordingConnection()
    _register_task90_parents(conn, state)

    documents = _inserts(conn, "documents")
    versions = _inserts(conn, "document_versions")
    assert len(conn.executions) == 2, "only the two registration inserts may run"
    assert len(documents) == 1
    assert len(versions) == 1

    doc_statement, doc_params = documents[0]
    ver_statement, ver_params = versions[0]

    # Parameterized SQL: identity values are never interpolated into the text.
    assert parent.document_id not in doc_statement
    assert parent.document_id not in ver_statement
    assert parent.version_id not in ver_statement
    assert "%s" in doc_statement
    assert "%s" in ver_statement

    # The exact admitted doc/version is the row target; the three identity
    # values are the ONLY parameters.
    assert doc_params == (parent.document_id,)
    assert ver_params[:2] == (parent.version_id, parent.document_id)

    # Deterministic valid 64-hex content hash derived from the admitted data.
    content_hash = ver_params[2]
    assert type(content_hash) is str
    assert len(content_hash) == 64
    assert all(char in "0123456789abcdef" for char in content_hash)
    assert content_hash == parent.canonical_hash
    assert len(ver_params) == 3

    # The proven schema-compatible literals are pinned in the statement text.
    assert "1, TRUE, 'active'" in ver_statement

    # The caller owns the connection; the helper commits but never closes it.
    assert conn.commit_calls == 1
    assert conn.close_calls == 0


def test_task90_register_parents_fails_closed_on_empty_parents() -> None:
    """RED: an admitted state with no parents must fail closed before any SQL."""
    conn = _RecordingConnection()
    with pytest.raises(ValueError, match="task90_parent_registration_empty"):
        _register_task90_parents(conn, _empty_parents_desired_state())
    assert conn.executions == []
    assert conn.commit_calls == 0


def test_task90_register_parents_fails_closed_on_duplicate_identity(
    tmp_path: Path,
) -> None:
    """RED: duplicate parent identities must fail closed."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_manual_relation_corpus(root)
    parent = _admit(root).parents[0]
    twin = E2aParent(
        document_id=parent.document_id,
        version_id=parent.version_id,
        relative_path=parent.relative_path,
        canonical_hash=parent.canonical_hash,
    )
    with pytest.raises(ValueError, match="task90_parent_registration_duplicate"):
        _task90_parent_identities((parent, twin))


def test_task90_register_parents_fails_closed_on_malformed_identity() -> None:
    """RED: a non-E2aParent identity must fail closed."""
    with pytest.raises(ValueError, match="task90_parent_registration_malformed"):
        _task90_parent_identities(("not-a-parent",))  # type: ignore[arg-type]
