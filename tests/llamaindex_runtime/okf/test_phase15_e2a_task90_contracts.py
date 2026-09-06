"""Task #90 default-collected contract suite (admission determinism + SQL shape).

This file is the default-collected surface of the Task #90 slice. It
asserts, without any database or Docker:

- the single production SQL-shape contract of Task #90 (the E2a relations
  collision-preflight must select the derived
  ``qualifiers IS NULL AS qualifiers_is_sql_null`` expression, never the
  bare physical column),
- the strict M-D-S-M raw-pair admission is deterministic: the same corpus
  under natural / reverse / seeded-shuffle file ordering yields a complete
  ``E2aDesiredState`` with identical parents, spans, manual facts,
  ownership, evidence, and manifest SHA / canonical representation,
- the full 15-table primary / 10-denylist / 3-cache collections are pinned
  against the production contract (not a reduced 4-axis subset),
- malformed / legacy / path-invalid / unresolved-evidence / tampered-digest
  / span-mismatch / duplicate-natural-key admission cases fail closed
  (blocked before any DML).

No database, no Docker, no authorized live selector invocation, and no
production symbol change is performed here.
"""

from __future__ import annotations

import random
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf._e2a_manual_fact_collision_preflight import (
    preflight_manual_fact_collisions,
)
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aManualFact,
    E2aOwnershipFact,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanSidecar

from ._phase15_e2a_task90_types import (
    TASK90_CACHE_TABLES,
    TASK90_DENYLIST_TABLES,
    TASK90_PRIMARY_TABLES,
)

_DIGEST = "a" * 64
_RELATION_NATURAL_KEY = canonical_json(
    {
        "subject_entity_id": "00000000-0000-0000-0000-000000001f95",
        "predicate": "supports",
        "object_entity_id": "00000000-0000-0000-0000-000000001fa2",
    }
)

# A second deterministic relation used for multi-fact determinism.
_RELATION_TWO_NATURAL_KEY = canonical_json(
    {
        "subject_entity_id": "00000000-0000-0000-0000-000000001f95",
        "predicate": "opposes",
        "object_entity_id": "00000000-0000-0000-0000-000000001fa3",
    }
)


# =============================================================================
# SQL-shape regression (constraint A)
# =============================================================================


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


class _RecordingCursor:
    """A read-only cursor fake that records every issued statement."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        del parameters
        self.statements.append(statement)

    def fetchall(self) -> object:
        return ()


def _relation_desired_state() -> E2aDesiredState:
    """Build one admitted-style manual relation with its ownership fact."""
    fact = E2aManualFact(
        fact_id=deterministic_id("relation", _RELATION_NATURAL_KEY),
        fact_kind="relation",
        relative_path="facts/relation.md",
        source_digest=_DIGEST,
        qualifiers={
            "negation": False,
            "condition": None,
            "direction": None,
            "qualifiers": {},
        },
        natural_key=_RELATION_NATURAL_KEY,
    )
    owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="relation",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": owner.fact_kind,
                "path": owner.relative_path,
                "identity": owner.fact_id,
                "source_digest": owner.source_digest,
            }
        ],
    }
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
        manual_relations=(fact,),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(owner,),
        sync_state_rows=(),
        validation_metadata={"raw_pair_protocol": "M-D-S-M"},
        provenance_metadata={"authority": "okf"},
    )


def _relations_preflight_projection() -> str:
    cursor = _RecordingCursor()
    preflight_manual_fact_collisions(cursor, _relation_desired_state())
    relations = [
        statement
        for statement in cursor.statements
        if "from relations" in _normalized(statement)
    ]
    assert relations, "the relations collision-preflight SELECT must be issued"
    return _normalized(relations[0]).partition(" from ")[0]


def test_relations_preflight_select_derives_qualifiers_is_sql_null() -> None:
    """RED: the relations preflight must select the derived NULL predicate."""
    projection = _relations_preflight_projection()
    assert "qualifiers is null as qualifiers_is_sql_null" in projection


def test_relations_preflight_rejects_bare_qualifiers_is_sql_null_column() -> None:
    """RED: the alias must be a derived expression, never a bare column."""
    projection = _relations_preflight_projection()
    index = projection.find("qualifiers_is_sql_null")
    assert index != -1, "the derived alias must be present in the projection"
    assert projection[:index].rstrip().endswith("as")


# =============================================================================
# Full-table collection pin (constraint I)
# =============================================================================


def test_task90_primary_tables_match_production_contract() -> None:
    """The Task #90 primary collection is the full 15-table production set."""
    import llamaindex_runtime.okf.e2a_contracts as contracts_mod
    import llamaindex_runtime.okf.e2a_materialization_repository as repo_mod

    assert len(TASK90_PRIMARY_TABLES) == 15
    assert TASK90_PRIMARY_TABLES == frozenset(contracts_mod._E2A_PRIMARY_TABLES)
    assert TASK90_PRIMARY_TABLES == frozenset(repo_mod._PRIMARY_TABLES)


def test_task90_primary_tables_names_are_pinned_explicitly() -> None:
    """The exact 15 primary table names stay pinned (no silent renaming)."""
    assert TASK90_PRIMARY_TABLES == frozenset(
        {
            "canonical_spans",
            "vector_chunks",
            "vector_chunk_spans",
            "tree_nodes",
            "tree_node_spans",
            "entities",
            "relations",
            "evidence",
            "evidence_links",
            "okf_manual_fact_ownership",
            "okf_manual_evidence_targets",
            "okf_sync_state",
            "summaries",
            "node_embeddings",
            "semantic_distribution",
        }
    )


def test_task90_denylist_and_cache_collections_match_production() -> None:
    """The 10 denylist and 3 cache collections match the production contract."""
    import llamaindex_runtime.okf.e2a_contracts as contracts_mod

    assert len(TASK90_DENYLIST_TABLES) == 10
    assert TASK90_DENYLIST_TABLES == frozenset(contracts_mod._E2A_DENYLIST_TABLES)
    assert len(TASK90_CACHE_TABLES) == 3
    assert TASK90_CACHE_TABLES == frozenset(contracts_mod._E2A_CACHE_TABLES)
    assert TASK90_CACHE_TABLES.issubset(TASK90_PRIMARY_TABLES)


def test_dml_recorder_rejects_table_outside_primary_or_denylist() -> None:
    """A DML target outside the 15 primary + 10 denylist tables is rejected."""
    from llamaindex_runtime.okf.e2a_contracts import DmlRecorder

    recorder = DmlRecorder()
    with pytest.raises(ValueError, match="outside the E2a allowlist"):
        recorder.record_issued(table="invented_table", operation="INSERT")


# =============================================================================
# Strict M-D-S-M corpus builders (constraint C)
# =============================================================================


def _write_raw_pair(root: Path, name: str, doc_id: str, version_id: str) -> None:
    """Write a valid strict M-D-S-M raw pair (markdown + sidecar + manifest)."""
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
    markdown = dump_raw_frontmatter(frontmatter, "raw body.\n").encode("utf-8")
    sidecar = SpanSidecar(
        schema_version=1, doc_id=doc_id, version_id=version_id, spans=()
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


def _write_manual_relation(
    root: Path,
    name: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    *,
    reverse_key_order: bool = False,
    evidence: object = None,
    negation: bool = False,
) -> Path:
    """Write a strict manual-relation markdown under ``relations/``.

    ``reverse_key_order`` renders the same frontmatter fields in the
    reverse YAML key order (identical semantic contract, different bytes).
    ``evidence`` is an optional frontmatter ``evidence`` list; ``negation``
    is an optional qualifier used to exercise natural-key collisions.
    """
    rel_dir = root / "relations"
    rel_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        ("type", "relation"),
        ("subject_entity_id", subject_id),
        ("predicate", predicate),
        ("object_entity_id", object_id),
        ("timestamp", "'2026-07-15T09:30:00Z'"),
        ("negation", "true" if negation else "false"),
    ]
    if evidence is not None:
        rendered = (
            "\n".join(
                f"  - document_id: {item['document_id']}\n"
                f"    version_id: {item['version_id']}\n"
                f"    span_id: {item['span_id']}"
                for item in evidence
            )
            if isinstance(evidence, (list, tuple))
            else ""
        )
        fields.append(("evidence", f"\n{rendered}"))
    if reverse_key_order:
        fields = list(reversed(fields))
    yaml_block = "\n".join(f"{key}: {value}" for key, value in fields)
    md_path = rel_dir / f"{name}.md"
    md_path.write_text(f"---\n{yaml_block}\n---\nFact body.\n", encoding="utf-8")
    return md_path


def _admit(root: Path) -> E2aDesiredState:
    with BundleAuthority(root) as authority:
        return e2a_admission.admit_e2a_corpus(authority)


def _assert_complete_state(state: E2aDesiredState) -> None:
    """Assert the admitted state is complete across every collection."""
    assert state.parents, "parents must be admitted"
    assert len(state.parents) == 2
    assert len(state.canonical_spans) == 0
    assert len(state.manual_relations) == 2
    assert len(state.manual_entities) == 0
    assert len(state.ownership_facts) == 2
    assert state.corpus_manifest_sha256 == e2a_admission.admit_e2a_corpus_hash(state)
    assert e2a_admission.admit_e2a_corpus_hash(state) == canonical_json_sha256(
        state.corpus_manifest
    )
    assert state.vector_chunks == ()
    assert state.tree_nodes == ()
    assert state.sync_state_rows == ()


# =============================================================================
# Admission determinism (constraint C)
# =============================================================================


def test_admission_deterministic_across_file_creation_orders(tmp_path: Path) -> None:
    """Natural vs reverse vs seeded-shuffle file order yields identical state.

    The SAME byte-identical corpus (identical doc/version UUIDs and fact
    files, only the materialization/enumeration order changes) must admit
    to byte-identical ``E2aDesiredState`` values, including manifest SHA and
    the canonical representation.
    """
    # Identical corpus identity across all orderings.
    pair_ant = (str(uuid4()), str(uuid4()))
    pair_zebra = (str(uuid4()), str(uuid4()))

    baseline_root = tmp_path / "natural"
    baseline_root.mkdir()
    _write_raw_pair(baseline_root, "ant", *pair_ant)
    _write_raw_pair(baseline_root, "zebra", *pair_zebra)
    _write_manual_relation(
        baseline_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    _write_manual_relation(
        baseline_root,
        "beta",
        "00000000-0000-0000-0000-000000001f95",
        "opposes",
        "00000000-0000-0000-0000-000000001fa3",
    )
    baseline = _admit(baseline_root)

    reverse_root = tmp_path / "reverse"
    reverse_root.mkdir()
    # Same corpus, written in reverse creation order.
    _write_raw_pair(reverse_root, "zebra", *pair_zebra)
    _write_manual_relation(
        reverse_root,
        "beta",
        "00000000-0000-0000-0000-000000001f95",
        "opposes",
        "00000000-0000-0000-0000-000000001fa3",
    )
    _write_raw_pair(reverse_root, "ant", *pair_ant)
    _write_manual_relation(
        reverse_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    reverse = _admit(reverse_root)

    assert reverse == baseline
    assert reverse.corpus_manifest_sha256 == baseline.corpus_manifest_sha256
    assert [p.relative_path for p in reverse.parents] == [
        "raw/ant.pair.json",
        "raw/zebra.pair.json",
    ]

    # Seeded shuffle: the same four logical files, written in a
    # deterministic pseudo-random order.
    for seed in (1, 7, 42):
        shuffled_root = tmp_path / f"shuffled_{seed}"
        shuffled_root.mkdir()
        order = ["ant", "zebra", "alpha", "beta"]
        random.Random(seed).shuffle(order)
        for item in order:
            if item == "ant":
                _write_raw_pair(shuffled_root, "ant", *pair_ant)
            elif item == "zebra":
                _write_raw_pair(shuffled_root, "zebra", *pair_zebra)
            elif item == "alpha":
                _write_manual_relation(
                    shuffled_root,
                    "alpha",
                    "00000000-0000-0000-0000-000000001f95",
                    "supports",
                    "00000000-0000-0000-0000-000000001fa2",
                )
            else:
                _write_manual_relation(
                    shuffled_root,
                    "beta",
                    "00000000-0000-0000-0000-000000001f95",
                    "opposes",
                    "00000000-0000-0000-0000-000000001fa3",
                )
        state = _admit(shuffled_root)
        assert state == baseline, f"seeded shuffle seed={seed} changed the state"
        _assert_complete_state(state)


def test_admission_manifest_is_canonical_across_orderings(tmp_path: Path) -> None:
    """The canonical manifest SHA is stable across artifact ordering."""
    baseline_root = tmp_path / "natural"
    baseline_root.mkdir()
    _write_raw_pair(baseline_root, "ant", str(uuid4()), str(uuid4()))
    _write_raw_pair(baseline_root, "zebra", str(uuid4()), str(uuid4()))
    _write_manual_relation(
        baseline_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    _write_manual_relation(
        baseline_root,
        "beta",
        "00000000-0000-0000-0000-000000001f95",
        "opposes",
        "00000000-0000-0000-0000-000000001fa3",
    )
    baseline = _admit(baseline_root)
    canonical = e2a_admission.admit_e2a_corpus_hash(baseline)
    assert canonical == baseline.corpus_manifest_sha256
    assert canonical == canonical_json_sha256(baseline.corpus_manifest)


def test_admission_manual_fact_identities_are_deterministic(tmp_path: Path) -> None:
    """Manual fact and ownership identities follow the natural key determinism."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_raw_pair(root, "ant", str(uuid4()), str(uuid4()))
    _write_manual_relation(
        root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    state = _admit(root)
    relation = state.manual_relations[0]
    expected_fact_id = deterministic_id("relation", _RELATION_NATURAL_KEY)
    assert relation.fact_id == expected_fact_id
    assert relation.natural_key == _RELATION_NATURAL_KEY
    owner = state.ownership_facts[0]
    assert owner.fact_id == expected_fact_id
    assert (
        owner.ownership_id
        == E2aOwnershipFact.create(
            relative_path=relation.relative_path,
            fact_kind="relation",
            fact_id=relation.fact_id,
            source_digest=relation.source_digest,
        ).ownership_id
    )
    assert owner.version_id is None and owner.document_id is None


def test_admission_two_distinct_relations_have_distinct_deterministic_ids(
    tmp_path: Path,
) -> None:
    """Different predicates yield different deterministic manual fact IDs."""
    root = tmp_path / "corpus"
    root.mkdir()
    _write_raw_pair(root, "ant", str(uuid4()), str(uuid4()))
    _write_manual_relation(
        root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    _write_manual_relation(
        root,
        "beta",
        "00000000-0000-0000-0000-000000001f95",
        "opposes",
        "00000000-0000-0000-0000-000000001fa3",
    )
    state = _admit(root)
    first, second = state.manual_relations
    assert first.fact_id == deterministic_id("relation", _RELATION_NATURAL_KEY)
    assert second.fact_id == deterministic_id("relation", _RELATION_TWO_NATURAL_KEY)
    assert first.fact_id != second.fact_id


def test_admission_frontmatter_key_order_preserves_semantic_identity(
    tmp_path: Path,
) -> None:
    """Reversed YAML key order keeps IDs/natural keys; only the content digest differs.

    The manual-fact identity is bound to the canonical natural key (a sorted
    canonical JSON), so a different frontmatter key ORDER cannot change the
    fact_id, ownership_id, or natural_key. The admission ``source_digest`` is
    the raw-bytes content hash by design, so the two admissions differ ONLY
    in that digest and in the manifest that embeds it.
    """
    natural_root = tmp_path / "natural"
    natural_root.mkdir()
    _write_manual_relation(
        natural_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
    )
    reversed_root = tmp_path / "reversed"
    reversed_root.mkdir()
    _write_manual_relation(
        reversed_root,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        reverse_key_order=True,
    )
    natural = _admit(natural_root)
    reversed_state = _admit(reversed_root)
    assert (
        natural.manual_relations[0].fact_id
        == reversed_state.manual_relations[0].fact_id
    )
    assert (
        natural.manual_relations[0].natural_key
        == reversed_state.manual_relations[0].natural_key
    )
    assert (
        natural.ownership_facts[0].ownership_id
        == reversed_state.ownership_facts[0].ownership_id
    )
    # Honest boundary: the raw-bytes source digest is content-bound.
    assert (
        natural.manual_relations[0].source_digest
        != reversed_state.manual_relations[0].source_digest
    )
    # And the semantic identity is unaffected by that content-bound digest.
    assert (
        deterministic_id("relation", natural.manual_relations[0].natural_key)
        == reversed_state.manual_relations[0].fact_id
    )


# =============================================================================
# Fail-closed admission (constraint C second half)
# =============================================================================


def test_admission_rejects_malformed_manual_frontmatter(tmp_path: Path) -> None:
    """Broken manual-fact YAML fails closed before any DML."""
    rel_dir = tmp_path / "relations"
    rel_dir.mkdir(parents=True, exist_ok=True)
    (rel_dir / "broken.md").write_text(
        "---\ntype: [unclosed\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        _admit(tmp_path)


def test_admission_rejects_legacy_raw_pair(tmp_path: Path) -> None:
    """A raw pair whose markdown declares a non-raw type fails closed."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    markdown = dump_raw_frontmatter(
        {"type": "legacy", "timestamp": 12345}, "legacy body.\n"
    ).encode("utf-8")
    sidecar = SpanSidecar(1, str(uuid4()), str(uuid4()), ())
    sidecar_bytes = sidecar.to_bytes()
    md_path = raw / "legacy.md"
    md_path.write_bytes(markdown)
    md_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=md_path.name,
        markdown_bytes=markdown,
        sidecar_file="legacy.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash({"type": "legacy", "timestamp": 12345}, sidecar),
    )
    md_path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())
    with pytest.raises(ValueError):
        _admit(tmp_path)


def test_admission_rejects_unsupported_manual_extension(tmp_path: Path) -> None:
    """A non-``.md`` file under ``relations/`` fails closed (path-invalid)."""
    rel_dir = tmp_path / "relations"
    rel_dir.mkdir(parents=True, exist_ok=True)
    (rel_dir / "fact.txt").write_text("not a fact", encoding="utf-8")
    with pytest.raises(ValueError):
        _admit(tmp_path)


def test_admission_rejects_unresolved_evidence(tmp_path: Path) -> None:
    """Evidence referencing a span absent from any raw pair fails closed."""
    _write_manual_relation(
        tmp_path,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        evidence=[
            {
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "span_id": str(uuid4()),
            }
        ],
    )
    with pytest.raises(ValueError, match="e2a_admission_evidence_unresolved"):
        _admit(tmp_path)


def test_admission_rejects_tampered_pair_digest(tmp_path: Path) -> None:
    """Rewriting a raw-pair member after manifesting fails the hash check."""
    doc_id, version_id = str(uuid4()), str(uuid4())
    _write_raw_pair(tmp_path, "ant", doc_id, version_id)
    md_path = tmp_path / "raw" / "ant.md"
    original = md_path.read_bytes()
    md_path.write_bytes(original + b"\nTAMPERED\n")
    with pytest.raises(ValueError):
        _admit(tmp_path)


def test_admission_rejects_span_sidecar_document_mismatch(tmp_path: Path) -> None:
    """A sidecar whose doc_id disagrees with the markdown fails closed."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "type": "raw",
        "doc_id": str(uuid4()),
        "version_id": str(uuid4()),
        "source_checksum": _DIGEST,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "raw body.\n").encode("utf-8")
    mismatched_doc = str(uuid4())
    sidecar = SpanSidecar(1, mismatched_doc, str(uuid4()), ())
    sidecar_bytes = sidecar.to_bytes()
    md_path = raw / "ant.md"
    md_path.write_bytes(markdown)
    md_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=md_path.name,
        markdown_bytes=markdown,
        sidecar_file="ant.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    )
    md_path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())
    with pytest.raises(ValueError):
        _admit(tmp_path)


def test_admission_rejects_natural_key_qualifier_collision(tmp_path: Path) -> None:
    """Two files with the same natural key but different qualifiers fail closed."""
    _write_manual_relation(
        tmp_path,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        negation=False,
    )
    _write_manual_relation(
        tmp_path,
        "alpha_copy",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        negation=True,
    )
    with pytest.raises(ValueError, match="e2a_admission_natural_key_collision"):
        _admit(tmp_path)


def test_admission_canonicalizes_same_natural_key_with_provenance(
    tmp_path: Path,
) -> None:
    """Two byte-identical sources for one natural key keep one fact + two owners.

    The same semantic fact admitted from two source files is canonicalized
    into a single manual relation while EACH source is retained as an
    ownership provenance row; the deterministic fact identity is preserved.
    """
    _write_raw_pair(tmp_path, "ant", str(uuid4()), str(uuid4()))
    _write_manual_relation(
        tmp_path,
        "alpha",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        negation=False,
    )
    _write_manual_relation(
        tmp_path,
        "alpha_copy",
        "00000000-0000-0000-0000-000000001f95",
        "supports",
        "00000000-0000-0000-0000-000000001fa2",
        negation=False,
    )
    state = _admit(tmp_path)
    assert len(state.manual_relations) == 1
    assert len(state.ownership_facts) == 2
    relation = state.manual_relations[0]
    assert relation.fact_id == deterministic_id("relation", _RELATION_NATURAL_KEY)
    assert {owner.relative_path for owner in state.ownership_facts} == {
        "relations/alpha.md",
        "relations/alpha_copy.md",
    }
