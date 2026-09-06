"""Live cells for the Phase 15 Task #88 C14 late-DML candidate (PARTIAL only).

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides the two
parent desired-state builder and the explicit live cell behind the
explicit-only selector ``phase15_e2a_late_dml_candidate.py``.

PARTIAL(C14-candidate)
    Two real versions of one document are registered through the real
    registry writer path (reusing ``_register_transition_pair``; no
    synthetic parent rows). A V1-complete/V2-empty two-parent desired state
    is built: V1 keeps its full legal E2a graph and sync row from
    ``_build_foundation_desired_state``, V2 is an admitted parent with no
    projections and no sync row, and the manifest carries exactly one
    raw-pair artifact per admitted parent plus V1's entity provenance
    artifact with a recomputed canonical hash. Before any V1
    materialization, a separately committed, parameterized bare evidence
    seed binding the desired V1 evidence ID and the real V2 registered
    version ID is written on its own fresh seed connection; it creates no
    evidence-target row, so it is excluded from scoped inventory and from
    stale-evidence deletion. Production ``E2aReconciler`` then runs real
    earlier primary DML and the evidence upsert guard raises ``ValueError``;
    the primary transaction rolls back and an independently opened,
    fresh-attested connection commits the durable failure audit. A fresh
    observer proves both registry versions, the durable bare seed, zero V1
    materialization, and the exact audit row. This is PARTIAL(C14-candidate)
    evidence only: its live rollback/audit/observer observations form the
    live component of the approved formal composed proof for the Task #88
    required cell ``true_late_dml_failure``. Standalone execution of this
    candidate cell does not itself close Task #88, #79, or Phase 15.

Security contract (identical to the Task #88 tranches):

- No environment variable access of any kind; no database-routing or
  credential environment variables anywhere.
- No URI, credential, target, container token, or raw fixture content is
  ever printed, logged, returned, or included in observation reprs.
- Every live role is an independently opened fresh attested connection:
  registry writer, bare-evidence seed writer, primary reconciler,
  failure-audit writer (the injected factory), and observer. Role
  separation means independent fresh attested connections/transactions,
  not distinct PostgreSQL principals.
- Every cursor and connection is closed in a finally block; the reconciler
  closes its primary on failure, and this frame also closes it in a
  finally path (the close is idempotent).
- Failures are absorbed into redacted observations that carry a bounded
  class/type-only diagnostic; exception messages, args, and reprs never
  leave the helper.
- No test framework machinery, no skip or xfail mechanics, no fakes, no
  DDL, no triggers, no advisory-lock SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from ._phase15_e2a_task88_live_cells import (
    _SOURCE_RELATIVE_PATH,
    _build_foundation_desired_state,
    _close_quietly,
    _error_reason,
    _file_sha256,
    _open_observer_connection,
    _open_reconciler_primary_connection,
    _open_writer_connection,
)
from ._phase15_e2a_task88_transition_cells import (
    _open_seed_connection,
    _register_transition_pair,
)


class LateDmlCandidateObservations(NamedTuple):
    """Redacted observations for the C14 late-DML candidate cell."""

    outcome_rolled_back_failure: bool
    failure_maps_empty: bool
    comparator_parity_none: bool
    audit_outcome_written: bool
    primary_closed: bool
    both_registry_versions_exist: bool
    bare_seed_durable: bool
    v1_materialization_absent: bool
    audit_count_one: bool
    audit_fields_match: bool
    audit_scope_manifest_matches: bool
    audit_diagnostic_matches: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "LateDmlCandidateObservations(outcome_rolled_back_failure="
            + repr(self.outcome_rolled_back_failure)
            + ", failure_maps_empty="
            + repr(self.failure_maps_empty)
            + ", comparator_parity_none="
            + repr(self.comparator_parity_none)
            + ", audit_outcome_written="
            + repr(self.audit_outcome_written)
            + ", primary_closed="
            + repr(self.primary_closed)
            + ", both_registry_versions_exist="
            + repr(self.both_registry_versions_exist)
            + ", bare_seed_durable="
            + repr(self.bare_seed_durable)
            + ", v1_materialization_absent="
            + repr(self.v1_materialization_absent)
            + ", audit_count_one="
            + repr(self.audit_count_one)
            + ", audit_fields_match="
            + repr(self.audit_fields_match)
            + ", audit_scope_manifest_matches="
            + repr(self.audit_scope_manifest_matches)
            + ", audit_diagnostic_matches="
            + repr(self.audit_diagnostic_matches)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


def _build_two_parent_desired_state(
    first_registration: Any,
    first_path: Path,
    second_registration: Any,
    second_path: Path,
) -> Any:
    """Build the V1-complete/V2-empty two-parent desired state.

    V1 comes from the real first registration through the shared foundation
    builder (full span/tree/chunk/manual fact/ownership/evidence graph plus
    its sync row). V2 is an admitted ``E2aParent`` from the real second
    registration and second file hash with no projections and no sync row.
    The manifest is rebuilt with exactly one raw-pair artifact per admitted
    parent plus V1's entity provenance artifact, and the canonical hash is
    recomputed so the constructed state validates through the public
    ``E2aDesiredState`` contract.
    """
    from llamaindex_runtime.okf.e2a_contracts import (
        E2aDesiredState,
        E2aParent,
        canonical_json_sha256,
    )

    first_desired = _build_foundation_desired_state(first_registration, first_path)
    first_parent = first_desired.parents[0]
    v2_parent = E2aParent(
        str(second_registration.doc_id),
        str(second_registration.version_id),
        _SOURCE_RELATIVE_PATH,
        _file_sha256(second_path),
    )
    entity_artifact = next(
        artifact
        for artifact in first_desired.corpus_manifest["artifacts"]
        if artifact["kind"] == "entity"
    )
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": first_parent.relative_path,
                "identity": f"{first_parent.document_id}:{first_parent.version_id}",
                "canonical_hash": first_parent.canonical_hash,
            },
            {
                "kind": "raw_pair",
                "path": v2_parent.relative_path,
                "identity": f"{v2_parent.document_id}:{v2_parent.version_id}",
                "canonical_hash": v2_parent.canonical_hash,
            },
            {
                "kind": "entity",
                "path": entity_artifact["path"],
                "identity": entity_artifact["identity"],
                "source_digest": entity_artifact["source_digest"],
            },
        ]
    }
    return E2aDesiredState(
        manifest,
        canonical_json_sha256(manifest),
        (first_parent, v2_parent),
        first_desired.canonical_spans,
        first_desired.vector_chunks,
        first_desired.vector_chunk_span_links,
        first_desired.tree_nodes,
        first_desired.tree_node_span_links,
        first_desired.manual_entities,
        first_desired.manual_relations,
        first_desired.evidence_objects,
        first_desired.evidence_links,
        first_desired.ownership_facts,
        first_desired.sync_state_rows,
        first_desired.validation_metadata,
        first_desired.provenance_metadata,
    )


def _v1_materialization_absent(
    cursor: Any, desired: Any, v1_version_id: str
) -> bool:
    """Prove the rolled-back primary transaction committed no V1 state.

    Every V1-derived artifact from the desired state (canonical span, tree
    node, vector chunk, entity, ownership, evidence link, V1 evidence row,
    E2a sync row) must be absent; the only durable E2a state is the bare
    V2-versioned evidence seed.
    """
    checks: list[bool] = []
    cursor.execute(
        "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        (v1_version_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s",
        (v1_version_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        (v1_version_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM entities WHERE entity_id = %s",
        (desired.manual_entities[0].fact_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM okf_manual_fact_ownership WHERE ownership_id = %s",
        (desired.ownership_facts[0].ownership_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM evidence_links WHERE evidence_link_id = %s",
        (desired.evidence_links[0].evidence_link_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM evidence WHERE version_id = %s",
        (v1_version_id,),
    )
    checks.append(cursor.fetchone() == (0,))
    cursor.execute(
        "SELECT COUNT(*) FROM okf_sync_state WHERE materialization_owner = %s",
        ("e2a",),
    )
    checks.append(cursor.fetchone() == (0,))
    return all(checks)


def _run_late_dml_candidate_impl(session: Any) -> LateDmlCandidateObservations:
    """Run the C14 late-DML candidate cell (details in the module docstring).

    The bare evidence seed is committed before any V1 materialization, the
    production reconciler receives the injected fresh audit connection
    factory, and the returned result must be ``rolled_back_failure`` with
    empty public maps, ``comparator_parity is None``, a written
    post-rollback audit, and a closed primary connection. PARTIAL(C14-
    candidate) only; its live rollback/audit/observer observations are the
    live component of the approved formal composed proof, and standalone
    execution does not itself close Task #88, #79, or Phase 15.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    first_path: Path | None = None
    second_path: Path | None = None
    writer_conn: Any = None
    seed_conn: Any = None
    seed_cursor: Any = None
    primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        first_path, first_registration, second_path, second_registration = (
            _register_transition_pair(writer_conn)
        )
        v1_version_id = str(first_registration.version_id)
        v2_version_id = str(second_registration.version_id)
        two_parent_desired = _build_two_parent_desired_state(
            first_registration, first_path, second_registration, second_path
        )
        evidence = two_parent_desired.evidence_objects[0]

        # The only deliberate manual DML: a bare evidence seed committed on
        # its own fresh seed connection before any V1 materialization. It
        # binds the desired V1 evidence ID to the real V2 version ID and
        # creates no okf_manual_evidence_targets row.
        seed_conn = _open_seed_connection(session)
        seed_cursor = seed_conn.cursor()
        seed_cursor.execute(
            "INSERT INTO evidence (evidence_id, version_id) VALUES (%s, %s)",
            (evidence.evidence_id, v2_version_id),
        )
        seed_conn.commit()

        primary_conn = _open_reconciler_primary_connection(session)
        reconciler = E2aReconciler(
            failure_audit_connection_factory=session.open_fresh_attested_connection
        )
        result = reconciler.reconcile(primary_conn, two_parent_desired)

        outcome_rolled_back_failure = result.outcome == "rolled_back_failure"
        failure_maps_empty = (
            not result.primary_dml_by_table and not result.denylist_dml_counts
        )
        comparator_parity_none = result.comparator_parity is None
        audit_outcome_written = (
            result.post_rollback_failure_audit_outcome == "written"
        )
        primary_closed = bool(primary_conn.closed)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT COUNT(*) FROM document_versions WHERE version_id = ANY(%s)",
            ([v1_version_id, v2_version_id],),
        )
        both_registry_versions_exist = observer_cursor.fetchone() == (2,)
        observer_cursor.execute(
            "SELECT evidence_id, version_id FROM evidence ORDER BY evidence_id"
        )
        evidence_rows = observer_cursor.fetchall()
        normalized_rows = [
            (str(row[0]), str(row[1]))
            for row in evidence_rows
        ]
        bare_seed_durable = normalized_rows == [
            (evidence.evidence_id, v2_version_id)
        ]
        observer_cursor.execute(
            "SELECT COUNT(*) FROM okf_manual_evidence_targets"
        )
        bare_seed_durable = bare_seed_durable and observer_cursor.fetchone() == (0,)
        v1_materialization_absent = _v1_materialization_absent(
            observer_cursor, two_parent_desired, v1_version_id
        )

        observer_cursor.execute("SELECT COUNT(*) FROM okf_rebuild_failure_audit")
        audit_count_one = observer_cursor.fetchone() == (1,)
        audit_fields_match = False
        audit_scope_manifest_matches = False
        audit_diagnostic_matches = False
        if audit_count_one:
            observer_cursor.execute(
                "SELECT failure_category, failure_code, failure_phase, "
                "rollback_confirmed, scope_count, scope_manifest, "
                "scope_manifest_sha256, failing_doc_id, failing_version_id, "
                "diagnostic FROM okf_rebuild_failure_audit"
            )
            row = observer_cursor.fetchone()
            if row is not None:
                expected_scope_manifest = {
                    "manifest_sha256": two_parent_desired.corpus_manifest_sha256,
                    "parent_count": len(two_parent_desired.parents),
                    "version_ids": [
                        parent.version_id
                        for parent in two_parent_desired.parents[:100]
                    ],
                }
                audit_fields_match = (
                    row[0] == "internal"
                    and row[1] == "internal_failure"
                    and row[2] == "parent_reconciliation"
                    and row[3] is True
                    and row[4] == 2
                    and row[6] == two_parent_desired.corpus_manifest_sha256
                    and row[7] is None
                    and row[8] is None
                )
                audit_scope_manifest_matches = row[5] == expected_scope_manifest
                audit_diagnostic_matches = row[9] == {"error_type": "ValueError"}

        return LateDmlCandidateObservations(
            outcome_rolled_back_failure=outcome_rolled_back_failure,
            failure_maps_empty=failure_maps_empty,
            comparator_parity_none=comparator_parity_none,
            audit_outcome_written=audit_outcome_written,
            primary_closed=primary_closed,
            both_registry_versions_exist=both_registry_versions_exist,
            bare_seed_durable=bare_seed_durable,
            v1_materialization_absent=v1_materialization_absent,
            audit_count_one=audit_count_one,
            audit_fields_match=audit_fields_match,
            audit_scope_manifest_matches=audit_scope_manifest_matches,
            audit_diagnostic_matches=audit_diagnostic_matches,
            success=True,
        )
    except Exception as failure:
        return LateDmlCandidateObservations(
            outcome_rolled_back_failure=False,
            failure_maps_empty=False,
            comparator_parity_none=False,
            audit_outcome_written=False,
            primary_closed=False,
            both_registry_versions_exist=False,
            bare_seed_durable=False,
            v1_materialization_absent=False,
            audit_count_one=False,
            audit_fields_match=False,
            audit_scope_manifest_matches=False,
            audit_diagnostic_matches=False,
            success=False,
            error_reason=_error_reason("late_dml_candidate_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(primary_conn)
        _close_quietly(seed_cursor)
        _close_quietly(seed_conn)
        _close_quietly(writer_conn)
        for path in (first_path, second_path):
            if path is not None:
                try:
                    path.unlink()
                except Exception:
                    pass
