"""Live cells for the Phase 15 E2A Task #88 Stage 2 transition tranche.

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides the shared
cells for the explicitly selected live transition selector:

- C2 cell: real single-parent registration, one changed materialization, then
  a contract-valid manifest-only mutation (extra top-level manifest key with a
  recomputed canonical hash). The projected sync-state effect is FIXED to
  ``no_op`` from production source: the manifest hash appears in no sync-state
  field and in no DML template, the repository outcome is ``changed`` iff any
  primary count is positive, and the contract graph reads only the
  ``artifacts`` manifest key. The cell asserts that fixed outcome plus zero
  primary DML, comparator parity, unchanged committed state, and absent
  ``last_synced_at`` churn; it never accepts either outcome opportunistically.
- C3 cell: two real versions of one document; the first version is
  materialized, then a second-scope state deliberately reuses the first
  version's span id. The exact global primary-key preflight rejection message
  is compared against the production template and committed state is
  unchanged on a fresh observer.
- C4 cell: the same real collision through the default ``E2aReconciler()``
  with no audit factory. The unwrapped exact ``ValueError`` is asserted, the
  primary is closed after rollback, a fresh observer sees unchanged state and
  zero durable audit rows, and a later fresh reconcile with a fresh span id
  succeeds (no lingering transaction-scoped lock).
- C5 cell: a real manual-fact preflight collision. The conflicting base
  ``entities`` material is seeded with narrowly scoped parameterized SQL on
  its own fresh attested connection, the audit factory is explicitly injected
  as ``session.open_fresh_attested_connection``, and the result is a real
  ``rolled_back_failure`` with empty failure maps, ``comparator_parity is
  None``, and exactly one durable append-only audit row with exact fields,
  including the canonical ``scope_manifest`` body (manifest_sha256,
  parent_count, version_ids) and its sha256.
  This is preflight rollback plus audit ONLY; it is never late-DML evidence
  and never C14.

Security contract (identical to the foundation tranche):

- No environment variable access of any kind; no DATABASE_URL anywhere.
- No URI, credential, target, container token, or raw fixture content is ever
  printed, logged, returned, or included in observation reprs.
- All connections come from DisposableE2aSession.open_fresh_attested_connection.
- The registry writer, every reconciler primary, the injected audit factory,
  the C5 seed, and every observer are separate fresh attested connections.
  Role separation in this tranche means independent fresh attested
  connections/transactions, not distinct PostgreSQL principals; no principal
  or security model is implied or changed.
- Every cursor and connection is closed in a finally block; the reconciler
  closes its primary on success and on failure, and this frame also closes it
  in a finally path (the close is idempotent).
- Failures are absorbed into redacted observations that carry a bounded
  class/type-only diagnostic; exception messages, args, and reprs never
  leave the helper.
- No test framework machinery, no skip or xfail mechanics.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, NamedTuple

from ._phase15_e2a_task88_live_cells import (
    _FIXTURE_TITLE,
    _PRIMARY_TABLE_NAMES,
    _SOURCE_FIXTURE_TEXT,
    _SOURCE_RELATIVE_PATH,
    _SOURCE_URI,
    _build_foundation_desired_state,
    _close_quietly,
    _create_source_fixture,
    _error_reason,
    _open_observer_connection,
    _open_reconciler_primary_connection,
    _open_writer_connection,
    _verify_durable_state,
)


class C2Observations(NamedTuple):
    """Redacted observations for the C2 manifest no-op cell."""

    first_outcome: str
    outcome_fixed_match: bool
    zero_primary_counts: bool
    primary_shape_valid: bool
    comparator_parity_true: bool
    manifest_sha256_match: bool
    state_unchanged: bool
    timestamp_churn_absent: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C2Observations(first_outcome="
            + repr(self.first_outcome)
            + ", outcome_fixed_match="
            + repr(self.outcome_fixed_match)
            + ", zero_primary_counts="
            + repr(self.zero_primary_counts)
            + ", primary_shape_valid="
            + repr(self.primary_shape_valid)
            + ", comparator_parity_true="
            + repr(self.comparator_parity_true)
            + ", manifest_sha256_match="
            + repr(self.manifest_sha256_match)
            + ", state_unchanged="
            + repr(self.state_unchanged)
            + ", timestamp_churn_absent="
            + repr(self.timestamp_churn_absent)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


class C3Observations(NamedTuple):
    """Redacted observations for the C3 preflight rejection cell."""

    first_outcome: str
    exact_error_match: bool
    error_is_value_error: bool
    state_unchanged: bool
    span_count_singleton: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C3Observations(first_outcome="
            + repr(self.first_outcome)
            + ", exact_error_match="
            + repr(self.exact_error_match)
            + ", error_is_value_error="
            + repr(self.error_is_value_error)
            + ", state_unchanged="
            + repr(self.state_unchanged)
            + ", span_count_singleton="
            + repr(self.span_count_singleton)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


class C4Observations(NamedTuple):
    """Redacted observations for the C4 default failure-contract cell."""

    first_outcome: str
    exact_error_match: bool
    error_is_value_error: bool
    primary_closed: bool
    state_unchanged: bool
    span_count_singleton: bool
    audit_row_count_zero: bool
    later_reconcile_changed: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C4Observations(first_outcome="
            + repr(self.first_outcome)
            + ", exact_error_match="
            + repr(self.exact_error_match)
            + ", error_is_value_error="
            + repr(self.error_is_value_error)
            + ", primary_closed="
            + repr(self.primary_closed)
            + ", state_unchanged="
            + repr(self.state_unchanged)
            + ", span_count_singleton="
            + repr(self.span_count_singleton)
            + ", audit_row_count_zero="
            + repr(self.audit_row_count_zero)
            + ", later_reconcile_changed="
            + repr(self.later_reconcile_changed)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


class C5Observations(NamedTuple):
    """Redacted observations for the C5 audited preflight rollback cell."""

    outcome_rolled_back_failure: bool
    failure_maps_empty: bool
    comparator_parity_none: bool
    audit_outcome_written: bool
    audit_count_one: bool
    audit_fields_match: bool
    audit_scope_manifest_matches: bool
    audit_diagnostic_matches: bool
    append_only_triggers_present: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C5Observations(outcome_rolled_back_failure="
            + repr(self.outcome_rolled_back_failure)
            + ", failure_maps_empty="
            + repr(self.failure_maps_empty)
            + ", comparator_parity_none="
            + repr(self.comparator_parity_none)
            + ", audit_outcome_written="
            + repr(self.audit_outcome_written)
            + ", audit_count_one="
            + repr(self.audit_count_one)
            + ", audit_fields_match="
            + repr(self.audit_fields_match)
            + ", audit_scope_manifest_matches="
            + repr(self.audit_scope_manifest_matches)
            + ", audit_diagnostic_matches="
            + repr(self.audit_diagnostic_matches)
            + ", append_only_triggers_present="
            + repr(self.append_only_triggers_present)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


def _open_seed_connection(session: Any) -> Any:
    """Open the C5 seed connection on its own fresh attested connection.

    Role separation means independent fresh attested connections/transactions,
    not distinct PostgreSQL principals.
    """
    return session.open_fresh_attested_connection()


def _read_sync_timestamp(cursor: Any) -> Any:
    """Read the committed sync timestamp for the fixture path."""
    cursor.execute(
        "SELECT last_synced_at FROM okf_sync_state WHERE okf_file_path = %s",
        (_SOURCE_RELATIVE_PATH,),
    )
    row = cursor.fetchone()
    if row is None or len(row) != 1:
        raise RuntimeError("sync timestamp observation failed")
    return row[0]


def _span_total(cursor: Any) -> int:
    """Count all canonical span rows in the isolated session."""
    cursor.execute("SELECT COUNT(*) FROM canonical_spans")
    row = cursor.fetchone()
    if row is None or type(row[0]) is not int:
        raise RuntimeError("span count observation failed")
    return row[0]


_GLOBAL_PREFLIGHT_COLLISION_TEMPLATE = (
    "global canonical_spans span_id={span_id} is owned by incompatible "
    "scope version {version_id}"
)


def _expected_span_collision_message(span_id: str, version_id: Any) -> str:
    """Render the single-source production-anchored preflight template."""
    return _GLOBAL_PREFLIGHT_COLLISION_TEMPLATE.format(
        span_id=span_id, version_id=str(version_id)
    )


def _register_transition_pair(writer_conn: Any) -> tuple[Any, Any, Any, Any]:
    """Register two real versions (distinct content, same URI) on the writer.

    The caller must unlink both returned paths in a finally block. The second
    file carries distinct content so the registry writer creates a new
    version (version_no = MAX + 1) instead of returning the first one.
    """
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    first_path = _create_source_fixture()
    first_registration = PostgresRegistryWriter(writer_conn).register_document(
        source_path=first_path,
        source_uri=_SOURCE_URI,
        title=_FIXTURE_TITLE,
    )
    second_path = _create_source_fixture()
    second_path.write_text(_SOURCE_FIXTURE_TEXT + " (second version)", encoding="utf-8")
    second_registration = PostgresRegistryWriter(writer_conn).register_document(
        source_path=second_path,
        source_uri=_SOURCE_URI,
        title=_FIXTURE_TITLE,
    )
    return first_path, first_registration, second_path, second_registration


def _build_colliding_state(desired: Any, span_id: str) -> Any:
    """Rebuild a state that deliberately reuses an existing span id.

    The span id is replaced consistently in the canonical span, the tree node
    span links, the vector chunk span links, and the evidence links (whose
    deterministic link identity is recomputed by the frozen dataclass
    ``__post_init__``), so the only conflict is the global primary key owned
    by the first scope version.
    """
    return replace(
        desired,
        canonical_spans=tuple(
            replace(span, span_id=span_id) for span in desired.canonical_spans
        ),
        tree_node_span_links=tuple(
            dict(link, span_id=span_id) for link in desired.tree_node_span_links
        ),
        vector_chunk_span_links=tuple(
            dict(link, span_id=span_id) for link in desired.vector_chunk_span_links
        ),
        evidence_links=tuple(
            replace(link, span_id=span_id) for link in desired.evidence_links
        ),
    )


def _run_c2_impl(session: Any) -> C2Observations:
    """Run the C2 manifest-only mutation cell with the fixed no_op projection.

    Absorbs all failures into a redacted observation; no URI, credentials,
    fixture contents, connections, or cursors escape this frame.
    """
    from llamaindex_runtime.okf.e2a_contracts import canonical_json_sha256
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    second_primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        source_path = _create_source_fixture()
        writer_conn = _open_writer_connection(session)
        registration = PostgresRegistryWriter(writer_conn).register_document(
            source_path=source_path,
            source_uri=_SOURCE_URI,
            title=_FIXTURE_TITLE,
        )
        desired = _build_foundation_desired_state(registration, source_path)

        primary_conn = _open_reconciler_primary_connection(session)
        first_result = E2aReconciler().reconcile(primary_conn, desired)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        before_timestamp = _read_sync_timestamp(observer_cursor)
        # End the pre-mutation observer snapshot (read-only rollback, no
        # DML/DDL) so the post-mutation read is isolation-level independent.
        observer_conn.rollback()

        mutated_manifest = dict(desired.corpus_manifest)
        mutated_manifest["stage2_mutation"] = "c2-extra-manifest-key"
        mutated_sha = canonical_json_sha256(mutated_manifest)
        mutated = replace(
            desired,
            corpus_manifest=mutated_manifest,
            corpus_manifest_sha256=mutated_sha,
        )

        second_primary_conn = _open_reconciler_primary_connection(session)
        result = E2aReconciler().reconcile(second_primary_conn, mutated)

        after_timestamp = _read_sync_timestamp(observer_cursor)
        state_unchanged = _verify_durable_state(observer_cursor, registration, desired)
        return C2Observations(
            first_outcome=first_result.outcome,
            outcome_fixed_match=result.outcome == "no_op",
            zero_primary_counts=all(
                value == 0 for value in result.primary_dml_by_table.values()
            ),
            primary_shape_valid=(
                set(result.primary_dml_by_table) == _PRIMARY_TABLE_NAMES
            ),
            comparator_parity_true=result.comparator_parity is True,
            manifest_sha256_match=result.manifest_sha256 == mutated_sha,
            state_unchanged=state_unchanged,
            timestamp_churn_absent=before_timestamp == after_timestamp,
            success=True,
        )
    except Exception as failure:
        return C2Observations(
            first_outcome="",
            outcome_fixed_match=False,
            zero_primary_counts=False,
            primary_shape_valid=False,
            comparator_parity_true=False,
            manifest_sha256_match=False,
            state_unchanged=False,
            timestamp_churn_absent=False,
            success=False,
            error_reason=_error_reason("c2_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        if source_path is not None:
            try:
                source_path.unlink()
            except Exception:
                pass


def _run_c3_impl(session: Any) -> C3Observations:
    """Run the C3 global primary-key collision rejection cell.

    The collision reconcile runs through default construction so the exact
    preflight error is observable at all; the exact message is compared
    against the production template and only the bounded match flag and the
    error class category leave this frame.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    first_path: Path | None = None
    second_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    collision_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        first_path, first_registration, second_path, second_registration = (
            _register_transition_pair(writer_conn)
        )
        first_desired = _build_foundation_desired_state(first_registration, first_path)
        first_span_id = first_desired.canonical_spans[0].span_id

        primary_conn = _open_reconciler_primary_connection(session)
        first_result = E2aReconciler().reconcile(primary_conn, first_desired)

        second_desired = _build_foundation_desired_state(
            second_registration, second_path
        )
        colliding = _build_colliding_state(second_desired, first_span_id)
        expected_message = _expected_span_collision_message(
            first_span_id, first_registration.version_id
        )

        collision_conn = _open_reconciler_primary_connection(session)
        failure: Exception | None = None
        try:
            E2aReconciler().reconcile(collision_conn, colliding)
        except Exception as error:
            failure = error
        if failure is None:
            raise ValueError("expected global primary-key preflight rejection")

        exact_error_match = isinstance(failure, ValueError) and failure.args == (
            expected_message,
        )
        error_is_value_error = isinstance(failure, ValueError)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        state_unchanged = _verify_durable_state(
            observer_cursor, first_registration, first_desired
        )
        span_singleton = _span_total(observer_cursor) == 1

        return C3Observations(
            first_outcome=first_result.outcome,
            exact_error_match=exact_error_match,
            error_is_value_error=error_is_value_error,
            state_unchanged=state_unchanged,
            span_count_singleton=span_singleton,
            success=True,
        )
    except Exception as failure:
        return C3Observations(
            first_outcome="",
            exact_error_match=False,
            error_is_value_error=False,
            state_unchanged=False,
            span_count_singleton=False,
            success=False,
            error_reason=_error_reason("c3_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(collision_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        for path in (first_path, second_path):
            if path is not None:
                try:
                    path.unlink()
                except Exception:
                    pass


def _run_c4_impl(session: Any) -> C4Observations:
    """Run the C4 default failure-contract cell on the same real collision.

    Default ``E2aReconciler()`` with no audit factory must raise the unwrapped
    exact ``ValueError``; the primary is then rolled back and closed. A fresh
    observer verifies unchanged state and zero durable audit rows, and a later
    fresh reconcile with a fresh span id must succeed (the transaction-scoped
    advisory locks were released by the rollback).
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    first_path: Path | None = None
    second_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    collision_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    retry_conn: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        first_path, first_registration, second_path, second_registration = (
            _register_transition_pair(writer_conn)
        )
        first_desired = _build_foundation_desired_state(first_registration, first_path)
        first_span_id = first_desired.canonical_spans[0].span_id

        primary_conn = _open_reconciler_primary_connection(session)
        first_result = E2aReconciler().reconcile(primary_conn, first_desired)

        second_desired = _build_foundation_desired_state(
            second_registration, second_path
        )
        colliding = _build_colliding_state(second_desired, first_span_id)
        expected_message = _expected_span_collision_message(
            first_span_id, first_registration.version_id
        )

        collision_conn = _open_reconciler_primary_connection(session)
        failure: Exception | None = None
        try:
            E2aReconciler().reconcile(collision_conn, colliding)
        except Exception as error:
            failure = error
        if failure is None:
            raise ValueError("expected unwrapped preflight ValueError")
        exact_error_match = isinstance(failure, ValueError) and failure.args == (
            expected_message,
        )
        primary_closed = bool(collision_conn.closed)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        state_unchanged = _verify_durable_state(
            observer_cursor, first_registration, first_desired
        )
        span_singleton = _span_total(observer_cursor) == 1
        observer_cursor.execute("SELECT COUNT(*) FROM okf_rebuild_failure_audit")
        audit_zero = observer_cursor.fetchone() == (0,)

        retry_conn = _open_reconciler_primary_connection(session)
        later = E2aReconciler().reconcile(retry_conn, second_desired)
        later_changed = later.outcome == "changed"

        return C4Observations(
            first_outcome=first_result.outcome,
            exact_error_match=exact_error_match,
            error_is_value_error=isinstance(failure, ValueError),
            primary_closed=primary_closed,
            state_unchanged=state_unchanged,
            span_count_singleton=span_singleton,
            audit_row_count_zero=audit_zero,
            later_reconcile_changed=later_changed,
            success=True,
        )
    except Exception as failure:
        return C4Observations(
            first_outcome="",
            exact_error_match=False,
            error_is_value_error=False,
            primary_closed=False,
            state_unchanged=False,
            span_count_singleton=False,
            audit_row_count_zero=False,
            later_reconcile_changed=False,
            success=False,
            error_reason=_error_reason("c4_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(retry_conn)
        _close_quietly(collision_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        for path in (first_path, second_path):
            if path is not None:
                try:
                    path.unlink()
                except Exception:
                    pass


def _run_c5_impl(session: Any) -> C5Observations:
    """Run the C5 audited manual-fact preflight rollback cell.

    The conflicting base entities row is seeded through narrowly scoped
    parameterized SQL on its own fresh attested connection (entity_id matches
    the desired fact so the natural-key mismatch fires), the audit factory is
    explicitly injected, and the reconcile must return ``rolled_back_failure``
    with empty failure maps and exactly one durable append-only audit row
    with exact fields, including the canonical ``scope_manifest`` body
    (manifest_sha256, parent_count, version_ids) and its sha256.
    Preflight rollback plus audit only; never late-DML evidence, never C14.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path: Path | None = None
    writer_conn: Any = None
    seed_conn: Any = None
    seed_cursor: Any = None
    primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        source_path = _create_source_fixture()
        writer_conn = _open_writer_connection(session)
        registration = PostgresRegistryWriter(writer_conn).register_document(
            source_path=source_path,
            source_uri=_SOURCE_URI,
            title=_FIXTURE_TITLE,
        )
        desired = _build_foundation_desired_state(registration, source_path)
        entity = desired.manual_entities[0]

        seed_conn = _open_seed_connection(session)
        seed_cursor = seed_conn.cursor()
        natural = json.loads(entity.natural_key)
        seed_cursor.execute(
            "INSERT INTO entities (entity_id, entity_key, entity_type, "
            "canonical_name) VALUES (%s, %s, %s, %s)",
            (
                entity.fact_id,
                entity.natural_key + "-seeded",
                natural.get("entity_type"),
                natural.get("title"),
            ),
        )
        seed_conn.commit()

        primary_conn = _open_reconciler_primary_connection(session)
        reconciler = E2aReconciler(
            failure_audit_connection_factory=session.open_fresh_attested_connection
        )
        result = reconciler.reconcile(primary_conn, desired)

        outcome_ok = result.outcome == "rolled_back_failure"
        failure_maps_empty = (
            not result.primary_dml_by_table and not result.denylist_dml_counts
        )
        parity_none = result.comparator_parity is None
        audit_outcome_written = result.post_rollback_failure_audit_outcome == "written"

        expected_scope_manifest = {
            "manifest_sha256": desired.corpus_manifest_sha256,
            "parent_count": len(desired.parents),
            "version_ids": [parent.version_id for parent in desired.parents[:100]],
        }

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute("SELECT COUNT(*) FROM okf_rebuild_failure_audit")
        audit_count = observer_cursor.fetchone()
        audit_count_one = audit_count == (1,)
        fields_ok = False
        scope_manifest_ok = False
        diagnostic_ok = False
        triggers_present = False
        if audit_count_one:
            observer_cursor.execute(
                "SELECT failure_category, failure_code, failure_phase, "
                "rollback_confirmed, scope_count, scope_manifest, "
                "scope_manifest_sha256, failing_doc_id, failing_version_id, "
                "diagnostic FROM okf_rebuild_failure_audit"
            )
            row = observer_cursor.fetchone()
            if row is not None:
                fields_ok = (
                    row[0] == "internal"
                    and row[1] == "internal_failure"
                    and row[2] == "parent_reconciliation"
                    and row[3] is True
                    and row[4] == 1
                    and row[6] == desired.corpus_manifest_sha256
                    and row[7] is None
                    and row[8] is None
                )
                scope_manifest_ok = row[5] == expected_scope_manifest
                diagnostic_ok = row[9] == {"error_type": "ValueError"}
            observer_cursor.execute(
                "SELECT COUNT(*) FROM pg_trigger WHERE tgname = ANY(%s)",
                (
                    [
                        "trg_okf_rebuild_failure_audit_append_only",
                        "trg_okf_rebuild_failure_audit_no_truncate",
                    ],
                ),
            )
            triggers_present = observer_cursor.fetchone() == (2,)

        return C5Observations(
            outcome_rolled_back_failure=outcome_ok,
            failure_maps_empty=failure_maps_empty,
            comparator_parity_none=parity_none,
            audit_outcome_written=audit_outcome_written,
            audit_count_one=audit_count_one,
            audit_fields_match=fields_ok,
            audit_scope_manifest_matches=scope_manifest_ok,
            audit_diagnostic_matches=diagnostic_ok,
            append_only_triggers_present=triggers_present,
            success=True,
        )
    except Exception as failure:
        return C5Observations(
            outcome_rolled_back_failure=False,
            failure_maps_empty=False,
            comparator_parity_none=False,
            audit_outcome_written=False,
            audit_count_one=False,
            audit_fields_match=False,
            audit_scope_manifest_matches=False,
            audit_diagnostic_matches=False,
            append_only_triggers_present=False,
            success=False,
            error_reason=_error_reason("c5_cell_failed", failure),
        )
    finally:
        _close_quietly(seed_cursor)
        _close_quietly(seed_conn)
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        if source_path is not None:
            try:
                source_path.unlink()
            except Exception:
                pass
