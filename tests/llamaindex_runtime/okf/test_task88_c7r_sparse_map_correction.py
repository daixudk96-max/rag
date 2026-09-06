"""Collected non-live regression coverage for the C7R sparse-map correction.

The Task #88 Stage 3 C7 live cell asserted the wrong sparse stale-ID count
map for the span-retired second desired state: its helper included
``evidence_links: 1``. This module collects three pure, non-live proofs:

1. A source-shape test pinning the corrected four-key expectation inside the
   NEW ``_phase15_e2a_task88_c7r_cells.py`` helper (the old Stage 3 helper
   is never modified) and requiring the explicit absence of the
   ``evidence_links`` key.
2. A source-shape test pinning the new C7R selector's DISTINCT identity,
   auth-first shape, and corrected-helper call (the old C7 selector
   identity is never reused).
3. An integration test that drives the REAL
   ``E2aMaterializationRepository().reconcile`` with a scripted cursor (the
   established whole-corpus-cleanup style, never a database) over the
   span-retired second desired state, proving the exact corrected sparse
   stale-ID count map and that evidence links are still deleted by stale
   evidence ids via DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS.

Why the corrected map has exactly four keys and no ``evidence_links``
entry: ``_span_retired_state`` retires the desired ``evidence_links``
collection, so ``load_existing_scope`` returns an empty evidence-links
identifier collection without even querying the table, and
``_delete_stale_evidence`` records an ``evidence_links`` stale count only
when its stale identifier set is nonempty. Evidence links are nonetheless
deleted downstream by stale evidence ids. Production behavior is correct;
nothing here changes production semantics.

This module never touches a database, Docker, the environment, or the live
selectors, and it never claims C14, Task #88, or Phase 15 completion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
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
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64
_DOCUMENT_ID = str(UUID(int=501))
_VERSION_ID = str(UUID(int=502))
_SPAN_ID = str(UUID(int=503))
_CHUNK_ID = str(UUID(int=504))
_NODE_ID = str(UUID(int=505))
_RELATIVE_PATH = "e2a-foundation/source.txt"
_SPAN_TEXT = (
    "Live E2A foundation source fixture. "
    "This text is registered through the real registry writer."
)
_ENTITY_KEY = canonical_json({"entity_type": "concept", "title": "Live Foundation"})
_ENTITY_ID = deterministic_id("entity", _ENTITY_KEY)
_OWNERSHIP_ID = deterministic_id("ownership", f"{_RELATIVE_PATH}:entity:{_ENTITY_ID}")
_EVIDENCE_ID = E2aEvidenceObject.create(
    version_id=_VERSION_ID, entity_id=_ENTITY_ID, relation_id=None
).evidence_id

# The exact corrected sparse stale-ID count map for the span-retired second
# desired state: tree_node_spans, vector_chunk_spans, evidence, and
# canonical_spans each 1, with NO evidence_links key (see the module
# docstring for the production-anchored reason).
_CORRECTED_SPARSE_MAP = {
    "tree_node_spans": 1,
    "vector_chunk_spans": 1,
    "evidence": 1,
    "canonical_spans": 1,
}

_C7R_HELPER_PATH = Path(__file__).with_name("_phase15_e2a_task88_c7r_cells.py")
_C7R_SELECTOR_PATH = Path(__file__).with_name(
    "phase15_e2a_task88_c7r_stale_span_deletion.py"
)


def _foundation_desired() -> E2aDesiredState:
    """Build the minimal single-parent foundation state (fixed constants)."""
    entity = E2aManualFact(
        _ENTITY_ID, "entity", _RELATIVE_PATH, _DIGEST, {}, _ENTITY_KEY
    )
    ownership = E2aOwnershipFact.create(
        relative_path=_RELATIVE_PATH,
        fact_kind="entity",
        fact_id=_ENTITY_ID,
        source_digest=_DIGEST,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
    )
    evidence = E2aEvidenceObject.create(
        version_id=_VERSION_ID, entity_id=_ENTITY_ID, relation_id=None
    )
    parent = E2aParent(_DOCUMENT_ID, _VERSION_ID, _RELATIVE_PATH, _DIGEST)
    span = E2aSpan(_DOCUMENT_ID, _VERSION_ID, _SPAN_ID, 0, _SPAN_TEXT)
    node = {
        "node_id": _NODE_ID,
        "version_id": _VERSION_ID,
        "parent_node_id": None,
        "node_type": "section",
        "level_no": 1,
        "title": "Live Foundation Section",
        "heading_path": "/e2a-foundation",
        "page_start": 1,
        "page_end": 1,
        "summary_text": "Foundation tree node summary.",
    }
    node_link = {"node_id": _NODE_ID, "span_id": _SPAN_ID, "ordinal_no": 0}
    chunk = {
        "chunk_id": _CHUNK_ID,
        "version_id": _VERSION_ID,
        "chunk_type": "text",
        "chunk_order": 0,
        "token_count": len(_SPAN_TEXT.split()),
        "text_preview": _SPAN_TEXT,
        "page_no": 1,
        "heading_path": "/e2a-foundation",
        "node_id": _NODE_ID,
        "embedding": tuple(float(index) for index in range(16)),
    }
    chunk_link = {"chunk_id": _CHUNK_ID, "span_id": _SPAN_ID, "ordinal_no": 0}
    sync_row = {
        "okf_file_path": _RELATIVE_PATH,
        "doc_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "source_checksum": _DIGEST,
        "canonical_hash": _DIGEST,
        "status": "materialized",
        "materialization_owner": "e2a",
    }
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": _RELATIVE_PATH,
                "identity": f"{_DOCUMENT_ID}:{_VERSION_ID}",
                "canonical_hash": _DIGEST,
            },
            {
                "kind": "entity",
                "path": _RELATIVE_PATH,
                "identity": _ENTITY_ID,
                "source_digest": _DIGEST,
            },
        ]
    }
    evidence_link = E2aEvidenceReference(
        _DOCUMENT_ID,
        _VERSION_ID,
        _SPAN_ID,
        _ENTITY_ID,
        None,
        _EVIDENCE_ID,
        _OWNERSHIP_ID,
        _VERSION_ID,
    )
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=(span,),
        vector_chunks=(chunk,),
        vector_chunk_span_links=(chunk_link,),
        tree_nodes=(node,),
        tree_node_span_links=(node_link,),
        manual_entities=(entity,),
        manual_relations=(),
        evidence_objects=(evidence,),
        evidence_links=(evidence_link,),
        ownership_facts=(ownership,),
        sync_state_rows=(sync_row,),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _span_retired_state(desired: E2aDesiredState) -> E2aDesiredState:
    """Retire the single span: spans, span links, evidence, evidence links."""
    return replace(
        desired,
        canonical_spans=(),
        vector_chunk_span_links=(),
        tree_node_span_links=(),
        evidence_objects=(),
        evidence_links=(),
    )


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


class _C7RScenarioCursor:
    """Scripted cursor for the span-retired C7R second-state reconcile.

    Every query is routed by normalized statement text (the established
    whole-corpus-cleanup style). Existing rows match the desired foundation
    projections exactly so every upsert is a no-op and only stale-span
    deletions are issued. Any unexpected statement or fetchone fails the
    test loudly instead of silently passing.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = _normalized(self._last_statement)
        if "for update" in statement:
            return self._locked_rows(statement)
        if "select exists" in statement:
            return [{"present": False}]
        if statement.startswith("select evidence_link_id from evidence_links"):
            return []
        if statement.startswith(
            "select version_id, materialization_owner from okf_sync_state"
        ):
            return [{"version_id": _VERSION_ID, "materialization_owner": "e2a"}]
        if statement.startswith(
            "select span_id from canonical_spans where version_id = any(%s)"
        ):
            return [{"span_id": _SPAN_ID}]
        if statement.startswith(
            "select chunk_id, version_id, node_id from vector_chunks"
        ):
            return [
                {
                    "chunk_id": _CHUNK_ID,
                    "version_id": _VERSION_ID,
                    "node_id": _NODE_ID,
                }
            ]
        if statement.startswith("select chunk_id, version_id, chunk_type, chunk_order"):
            return [self._chunk_row()]
        if statement.startswith(
            "select node_id, version_id, parent_node_id from tree_nodes"
        ):
            return [
                {
                    "node_id": _NODE_ID,
                    "version_id": _VERSION_ID,
                    "parent_node_id": None,
                }
            ]
        if statement.startswith(
            "select node_id, version_id, parent_node_id, node_type"
        ):
            return [self._node_row()]
        if "from vector_chunk_spans as link" in statement:
            return [{"chunk_id": _CHUNK_ID, "span_id": _SPAN_ID, "ordinal_no": 0}]
        if "from tree_node_spans as link" in statement:
            return [{"node_id": _NODE_ID, "span_id": _SPAN_ID, "ordinal_no": 0}]
        if "from evidence inner join okf_manual_evidence_targets" in statement:
            return [{"evidence_id": _EVIDENCE_ID}]
        if (
            "from okf_manual_fact_ownership" in statement
            and "where version_id = any(%s)" in statement
        ):
            return [
                {
                    "ownership_id": _OWNERSHIP_ID,
                    "fact_kind": "entity",
                    "fact_id": _ENTITY_ID,
                }
            ]
        if (
            "from okf_manual_fact_ownership" in statement
            and "where ownership_id = any(%s)" in statement
        ):
            return [self._ownership_row()]
        if (
            "from okf_manual_fact_ownership" in statement
            and "version_id is null" in statement
        ):
            return []
        if statement.startswith(
            "select okf_file_path, doc_id, version_id, source_checksum"
        ):
            return [self._sync_row()]
        if "from entities" in statement and "where entity_id = any(%s)" in statement:
            return [
                {
                    "entity_id": _ENTITY_ID,
                    "entity_key": _ENTITY_KEY,
                    "entity_type": "concept",
                    "canonical_name": "Live Foundation",
                }
            ]
        if statement.startswith(
            "select okf_file_path, materialization_owner from okf_sync_state"
        ):
            return [{"okf_file_path": _RELATIVE_PATH, "materialization_owner": "e2a"}]
        raise AssertionError(f"unexpected statement: {self._last_statement}")

    def fetchone(self) -> Mapping[str, object]:
        raise AssertionError(f"unexpected fetchone after: {self._last_statement}")

    @staticmethod
    def _locked_rows(statement: str) -> list[Mapping[str, object]]:
        if "from canonical_spans" in statement:
            return [{"span_id": _SPAN_ID}]
        if "from evidence" in statement:
            return [{"evidence_id": _EVIDENCE_ID}]
        raise AssertionError(f"unexpected locked relation: {statement}")

    @staticmethod
    def _chunk_row() -> Mapping[str, object]:
        return {
            "chunk_id": _CHUNK_ID,
            "version_id": _VERSION_ID,
            "chunk_type": "text",
            "chunk_order": 0,
            "token_count": len(_SPAN_TEXT.split()),
            "text_preview": _SPAN_TEXT,
            "page_no": 1,
            "heading_path": "/e2a-foundation",
            "node_id": _NODE_ID,
            "embedding": "[" + ",".join(str(float(index)) for index in range(16)) + "]",
        }

    @staticmethod
    def _node_row() -> Mapping[str, object]:
        return {
            "node_id": _NODE_ID,
            "version_id": _VERSION_ID,
            "parent_node_id": None,
            "node_type": "section",
            "level_no": 1,
            "title": "Live Foundation Section",
            "heading_path": "/e2a-foundation",
            "page_start": 1,
            "page_end": 1,
            "summary_text": "Foundation tree node summary.",
        }

    @staticmethod
    def _ownership_row() -> Mapping[str, object]:
        return {
            "ownership_id": _OWNERSHIP_ID,
            "okf_relative_path": _RELATIVE_PATH,
            "fact_kind": "entity",
            "fact_id": _ENTITY_ID,
            "entity_id": _ENTITY_ID,
            "relation_id": None,
            "source_digest": _DIGEST,
            "document_id": _DOCUMENT_ID,
            "version_id": _VERSION_ID,
            "scope_version_id": _VERSION_ID,
        }

    @staticmethod
    def _sync_row() -> Mapping[str, object]:
        return {
            "okf_file_path": _RELATIVE_PATH,
            "doc_id": _DOCUMENT_ID,
            "version_id": _VERSION_ID,
            "source_checksum": _DIGEST,
            "canonical_hash": _DIGEST,
            "status": "materialized",
            "materialization_owner": "e2a",
        }


def test_c7r_helper_source_pins_corrected_sparse_map_without_evidence_links() -> None:
    """The C7R helper pins the corrected four-key map and no evidence_links."""
    source = _C7R_HELPER_PATH.read_text(encoding="utf-8")
    assert "_run_c7r_impl" in source
    assert "C7RStaleDeletionObservations" in source
    compact = " ".join(source.split())
    for key in (
        '"tree_node_spans": 1',
        '"vector_chunk_spans": 1',
        '"evidence": 1',
        '"canonical_spans": 1',
    ):
        assert key in compact
    assert '"evidence_links": 1' not in compact


def test_c7r_selector_source_pins_distinct_identity_and_auth_first() -> None:
    """The C7R selector keeps a distinct identity and fails closed first."""
    source = _C7R_SELECTOR_PATH.read_text(encoding="utf-8")
    assert "def test_phase15_e2a_task88_c7r_stale_span_deletion_live()" in source
    assert "_require_authorization()" in source
    assert "_run_c7r_impl(session)" in source
    assert "evidence_links_key_absent" in source
    assert "test_phase15_e2a_task88_c7_stale_span_deletion_live" not in source


def test_span_retired_reconcile_reports_exact_corrected_sparse_map() -> None:
    """The real repository reports the corrected map with no evidence_links."""
    cursor = _C7RScenarioCursor()
    desired_b = _span_retired_state(_foundation_desired())

    result = E2aMaterializationRepository().reconcile(
        cursor, desired_b, recorder=DmlRecorder()
    )

    assert result.outcome == "changed"
    assert result.stale_deletion_counts == _CORRECTED_SPARSE_MAP
    assert "evidence_links" not in result.stale_deletion_counts
    # The evidence_links DELETE statement is still issued by stale evidence
    # ids: statement presence is distinct from the sparse stale-ID count map.
    assert result.primary_dml_by_table["evidence_links"] == 1
    executed = [statement for statement, _ in cursor.calls]
    assert any(
        statement.startswith("DELETE FROM tree_node_spans WHERE node_id = %s")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM vector_chunk_spans WHERE chunk_id = %s")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM evidence_links WHERE evidence_id = ANY(%s)")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM okf_manual_evidence_targets")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM evidence WHERE evidence_id = ANY(%s)")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM tree_node_spans WHERE span_id = ANY(%s)")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM vector_chunk_spans WHERE span_id = ANY(%s)")
        for statement in executed
    )
    assert any(
        statement.startswith("DELETE FROM canonical_spans WHERE span_id = ANY(%s)")
        for statement in executed
    )
    # No per-link deletion was issued (no stale evidence-link identifiers),
    # and the evidence_links inventory query was never executed.
    assert not any(
        statement.startswith("DELETE FROM evidence_links WHERE evidence_link_id")
        for statement in executed
    )
    assert not any(
        "select evidence_link_id, source_kind, evidence_id" in statement.lower()
        for statement in executed
    )
