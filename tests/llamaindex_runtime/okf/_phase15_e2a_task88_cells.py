"""Task #88 non-live cell contracts and approved composed-proof metadata.

This module provides the non-live contract surface of the Task #88 slice:

- The exact 10-key all-zero denylist map derived from the canonical
  production constant ``_E2A_DENYLIST_TABLES``, plus a typed validator
  that REJECTS missing, non-integer, negative, and unexpected keys
  (never a silent ``dict.get(..., 0)`` default).
- The ``E2aReconciliationResult`` field contract helper, which checks the
  runtime type of every result field against the real production class
  (``comparator_parity`` accepts exactly ``bool`` or ``None``, matching
  production, which emits ``None`` for rolled-back / unknown outcomes).
- The mandated prohibited-module family guard: retained exact module
  names plus the mandated family fragments, matched on plain module-name
  strings so the fresh-process guard can evaluate ``sys.modules`` keys in
  the child without importing a prohibited module.
- The single SHARED required-cell id ``TASK88_REQUIRED_CELL_ID``
  (``true_late_dml_failure``) behind the approved formal composed proof:
  there is NO parallel blocked definition; every stale Task #88 blocker
  API name (``TASK88_BLOCKED_*``, ``Task88BlockedStatus``,
  ``require_blocked_late_dml_proof``) is absent.
- Immutable cell-plan metadata for the future live acceptance selector,
  carrying the three plan-gate corrections:

  1. Reviews before live: every live cell requires the gate order
     unit_green -> general_review -> db_security_review -> authorized_live.
  2. Parent provenance: every parent-bearing cell declares the required
     provenance of its ``document_versions`` rows.
  3. The failure-audit cell and the approved composed-proof cell require
     an explicitly injected fresh attested connection factory, not the
     pure default constructor.

Nothing in this module creates a database session, touches credentials,
or imports any prohibited historical module. No live selector is
executed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from llamaindex_runtime.okf.e2a_contracts import (
    _E2A_CACHE_TABLES,
    _E2A_DENYLIST_TABLES,
    _E2A_PRIMARY_TABLES,
    E2aReconciliationResult,
)

# ---------------------------------------------------------------------------
# Task #88 shared required-cell id
# ---------------------------------------------------------------------------

TASK88_REQUIRED_CELL_ID = "true_late_dml_failure"


# ---------------------------------------------------------------------------
# Mandated prohibited-module family guard
# ---------------------------------------------------------------------------

# Retained exact module names from the original eight-name guard: the
# disposable execution module and the verification runner. Any loaded
# module whose name matches an exact name OR contains any mandated family
# fragment is a violation. Matching is pure string logic and never
# imports or reads a module, so it can be evaluated over ``sys.modules``
# keys in the fresh-process guard without touching a prohibited file.
BLOCKED_EXACT_MODULE_NAMES: frozenset[str] = frozenset(
    {
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
    }
)

# Mandated prohibited naming families. The previously guarded six
# ``test_real_e2a_reconciler_*`` / ``_real_e2a_reconciler_*`` names are
# covered by the ``real_e2a_reconciler`` / ``_real_e2a_`` fragments;
# future members (for example ``e2a_disposable_acceptance`` or a
# ``_real_e2a_reconciler_testkit``) match by fragment. The verification
# namespace itself stays guarded exactly (the runner name), never by
# family, per the mandate.
BLOCKED_MODULE_FRAGMENTS: frozenset[str] = frozenset(
    {
        "real_e2a_reconciler",
        "disposable_acceptance",
        "disposable_postgres",
        "_real_e2a_",
    }
)


def module_name_is_blocked(module_name: str) -> bool:
    """Return True when a module name matches a mandated prohibited family.

    Exact-name match or any family-fragment substring match. Operates on
    a plain string and never imports, reads, or loads the named module,
    so the fresh-process guard can evaluate every ``sys.modules`` key
    without touching a prohibited file. Fails closed: unknown future
    members of a mandated family are matched by fragment.
    """
    if module_name in BLOCKED_EXACT_MODULE_NAMES:
        return True
    return any(fragment in module_name for fragment in BLOCKED_MODULE_FRAGMENTS)


# ---------------------------------------------------------------------------
# Exact 10-key all-zero denylist map and typed validator
# ---------------------------------------------------------------------------

E2A_DENYLIST_TABLES_ALL_ZERO: MappingProxyType[str, int] = MappingProxyType(
    {table: 0 for table in _E2A_DENYLIST_TABLES}
)


def validate_denylist_dml_counts(
    counts: Mapping[str, object],
) -> MappingProxyType[str, int]:
    """Validate a denylist DML counts map with exact-key, typed checks.

    Rejects missing keys, unexpected keys, non-integer values, and
    negative values. Never silently defaults a missing key to zero.
    """
    if not isinstance(counts, Mapping):
        raise ValueError("denylist counts must be a mapping")
    expected_keys = frozenset(_E2A_DENYLIST_TABLES)
    actual_keys = frozenset(counts)
    missing = expected_keys - actual_keys
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"missing denylist key: {missing_names}")
    unexpected = actual_keys - expected_keys
    if unexpected:
        unexpected_names = ", ".join(sorted(unexpected))
        raise ValueError(f"unexpected denylist key: {unexpected_names}")
    validated: dict[str, int] = {}
    for name in _E2A_DENYLIST_TABLES:
        value = counts[name]
        if type(value) is not int or value < 0:
            raise ValueError(
                f"denylist count for {name} must be a non-negative integer"
            )
        validated[name] = value
    return MappingProxyType(validated)


# ---------------------------------------------------------------------------
# E2aReconciliationResult field contract helper
# ---------------------------------------------------------------------------

# Canonical stale-deletion domain: exactly the tables production writes into
# ``stale_deletion_counts`` (see ``e2a_materialization_repository`` and its
# stale-deletion helpers); every key is an E2a primary table.
E2A_STALE_DELETION_TABLES: frozenset[str] = frozenset(
    {
        "tree_node_spans",
        "vector_chunk_spans",
        "tree_nodes",
        "vector_chunks",
        "evidence",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_sync_state",
        "canonical_spans",
    }
)

RESULT_FIELD_CONTRACT: MappingProxyType[str, str] = MappingProxyType(
    {
        "outcome": "str",
        "manifest_sha256": "str",
        "primary_dml_by_table": "mapping of table -> non-negative int",
        "denylist_dml_counts": "mapping of denylist table -> non-negative int",
        "comparator_parity": "bool or None",
        "stale_deletion_counts": "mapping of table -> non-negative int",
        "cache_invalidation_counts": "mapping of table -> non-negative int",
        "failure_audit_outcome": "str or None",
        "post_rollback_failure_audit_outcome": "str or None",
        "reconciliation_required": "bool",
    }
)


def _nullable_str_fields() -> frozenset[str]:
    return frozenset(("failure_audit_outcome", "post_rollback_failure_audit_outcome"))


def _validate_full_count_mapping(
    result: object,
    field_name: str,
    allowed_keys: frozenset[str],
    domain_name: str,
) -> None:
    """Require the FULL canonical key set with non-negative exact-int values."""
    value = getattr(result, field_name)
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{field_name} has an unexpected runtime type {type(value).__name__}"
        )
    if set(value) != set(allowed_keys):
        raise ValueError(f"{field_name} must contain the full {domain_name} key set")
    for key, count in value.items():
        if type(key) is not str or type(count) is not int or count < 0:
            raise ValueError(f"{field_name} must be a non-negative integer mapping")


def _validate_sparse_count_mapping(
    result: object,
    field_name: str,
    allowed_keys: frozenset[str],
) -> None:
    """Allow production's intentional sparsity; reject foreign keys and bad values."""
    value = getattr(result, field_name)
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{field_name} has an unexpected runtime type {type(value).__name__}"
        )
    outside = set(value) - set(allowed_keys)
    if outside:
        outside_names = ", ".join(sorted(outside))
        raise ValueError(
            f"{field_name} contains keys outside the allowed domain: {outside_names}"
        )
    for key, count in value.items():
        if type(key) is not str or type(count) is not int or count < 0:
            raise ValueError(f"{field_name} must be a non-negative integer mapping")


def validate_result_field_contract(result: object) -> None:
    """Validate the runtime field types of a reconciliation result.

    The result must be an instance of the REAL production
    ``E2aReconciliationResult``; no fake or partial stand-in is accepted.
    The count maps are checked against the canonical production table
    constants:

    - ``primary_dml_by_table`` must contain the FULL E2a primary table
      key set with non-negative exact-int values;
    - ``denylist_dml_counts`` is delegated to
      ``validate_denylist_dml_counts`` (exact 10-key set, non-negative
      exact ints);
    - ``stale_deletion_counts`` / ``cache_invalidation_counts`` permit
      production's intentional sparsity but reject keys outside their
      canonical domains and any non-string / non-int / negative values;
    - ``comparator_parity`` accepts exactly ``bool`` or ``None``: the
      production reconciler emits ``None`` for ``rolled_back_failure``
      and ``outcome_unknown`` results. This helper validates runtime
      field types against the real production class; it does not judge
      outcome-specific semantics.
    """
    if type(result) is not E2aReconciliationResult:
        raise ValueError(
            "result field contract applies to E2aReconciliationResult, "
            f"got {type(result).__name__}"
        )
    nullable_str_fields = _nullable_str_fields()
    for field_name in RESULT_FIELD_CONTRACT:
        if field_name == "primary_dml_by_table":
            _validate_full_count_mapping(
                result, field_name, _E2A_PRIMARY_TABLES, "E2a primary table"
            )
        elif field_name == "denylist_dml_counts":
            denylist_counts = getattr(result, field_name)
            if not isinstance(denylist_counts, Mapping):
                raise ValueError(
                    f"{field_name} has an unexpected runtime type "
                    f"{type(denylist_counts).__name__}"
                )
            validate_denylist_dml_counts(denylist_counts)
        elif field_name == "stale_deletion_counts":
            _validate_sparse_count_mapping(
                result, field_name, E2A_STALE_DELETION_TABLES
            )
        elif field_name == "cache_invalidation_counts":
            _validate_sparse_count_mapping(result, field_name, _E2A_CACHE_TABLES)
        elif field_name in nullable_str_fields:
            value = getattr(result, field_name)
            if value is not None and type(value) is not str:
                raise ValueError(
                    f"{field_name} has an unexpected runtime type "
                    f"{type(value).__name__}"
                )
        elif field_name in ("outcome", "manifest_sha256"):
            value = getattr(result, field_name)
            if type(value) is not str:
                raise ValueError(
                    f"{field_name} has an unexpected runtime type "
                    f"{type(value).__name__}"
                )
        elif field_name == "comparator_parity":
            value = getattr(result, field_name)
            if value is not None and type(value) is not bool:
                raise ValueError(
                    f"{field_name} has an unexpected runtime type "
                    f"{type(value).__name__}"
                )
        elif field_name == "reconciliation_required":
            value = getattr(result, field_name)
            if type(value) is not bool:
                raise ValueError(
                    f"{field_name} has an unexpected runtime type "
                    f"{type(value).__name__}"
                )


# ---------------------------------------------------------------------------
# Immutable cell-plan metadata for the future live selector
# ---------------------------------------------------------------------------

LIVE_GATE_ORDER: tuple[str, ...] = (
    "unit_green",
    "general_review",
    "db_security_review",
    "authorized_live",
)

_PARENT_PROVENANCE_STATEMENT = (
    "document_versions rows must exist for every desired parent with exact "
    "doc_id/version_id; requires real PostgresRegistryWriter registration or "
    "an explicitly parameterized document_versions seed"
)


@dataclass(frozen=True)
class CellPlan:
    """Frozen descriptor of one future Task #88 acceptance cell."""

    cell_id: str
    cell_name: str
    source_supported_facts: Sequence[str]
    required_parent_provenance: str
    requires_injected_fresh_attested_factory: bool
    requires_reviews_before_live: bool


CELL_PLAN: tuple[CellPlan, ...] = (
    CellPlan(
        cell_id="parent_provenance_sync",
        cell_name="Parent lock-row sync",
        source_supported_facts=(
            "E2aReconciler acquires advisory + FOR UPDATE document_versions "
            "parent locks via production scope-lock code",
            "parent lock rows are validated exactly (one row per parent)",
        ),
        required_parent_provenance=_PARENT_PROVENANCE_STATEMENT,
        requires_injected_fresh_attested_factory=False,
        requires_reviews_before_live=True,
    ),
    CellPlan(
        cell_id="baseline_noop_reconcile",
        cell_name="Default reconciler + default repository no-op commit",
        source_supported_facts=(
            "E2aReconciler() default E2aMaterializationRepository contract "
            "for E2aDesiredState (no fake repository)",
            "fresh DisposableE2aSession.open_fresh_attested_connection with "
            "autocommit exactly False",
            "result outcome no_op, comparator_parity True, single commit, "
            "no failure audit",
        ),
        required_parent_provenance=_PARENT_PROVENANCE_STATEMENT,
        requires_injected_fresh_attested_factory=False,
        requires_reviews_before_live=True,
    ),
    CellPlan(
        cell_id="manual_fact_collision_preflight",
        cell_name="Manual fact collision preflight rejection",
        source_supported_facts=(
            "preflight_manual_fact_collisions rejects cross-scope natural-key "
            "collisions before any DML",
            "global primary-key preflight rejects cross-scope takeover with "
            "exact messages",
        ),
        required_parent_provenance=_PARENT_PROVENANCE_STATEMENT,
        requires_injected_fresh_attested_factory=False,
        requires_reviews_before_live=True,
    ),
    CellPlan(
        cell_id="failure_audit_written",
        cell_name="Post-rollback failure audit written",
        source_supported_facts=(
            "failure_audit_connection_factory must be an explicitly injected "
            "fresh attested factory from "
            "DisposableE2aSession.open_fresh_attested_connection; the pure "
            "default constructor (None factory) is NOT an audit path",
            "audit row INSERT into okf_rebuild_failure_audit on its own "
            "connection, then committed and closed",
            "post_rollback_failure_audit_outcome in written / failed / "
            "outcome_unknown / written_cleanup_unconfirmed",
        ),
        required_parent_provenance=_PARENT_PROVENANCE_STATEMENT,
        requires_injected_fresh_attested_factory=True,
        requires_reviews_before_live=True,
    ),
    CellPlan(
        cell_id=TASK88_REQUIRED_CELL_ID,
        cell_name="True late-DML failure (approved composed proof)",
        source_supported_facts=(
            "live V1/V2 rollback/audit/observer observations: "
            "rolled_back_failure outcome, empty primary/denylist maps, "
            "comparator_parity None, written post-rollback audit, closed "
            "primary, both registry versions durable, bare evidence seed "
            "durable with no evidence-target row, zero V1 materialization, "
            "exactly one audit row with matching fields/scope manifest/"
            "diagnostic",
            "production evidence UPSERT and _issue ordering: the "
            "WHERE version_id conflict guard, RETURNING 1, and "
            "_issue execute -> recorder.record_issued -> fetchone order",
            "repository source order before _upsert_evidence: "
            "_validate_desired, _existing_scope, _upsert_canonical_spans, "
            "_upsert_tree, _upsert_chunks, _delete_stale_evidence, "
            "_upsert_manual_facts all precede _upsert_evidence in reconcile",
            "V2 preflight admission and bare evidence inventory exclusion: "
            "global preflight admits any version in the desired parent set; "
            "scoped evidence inventory joins okf_manual_evidence_targets, so "
            "a bare seed with no target row is excluded from inventory",
            "migration 019 audit phase: the failure-audit phase check "
            "constraint permits parent_reconciliation",
            "explicit rollback-result-map boundary: the composed proof "
            "asserts the rolled-back failure result maps exactly (empty "
            "primary/denylist maps and comparator_parity None) and never "
            "claims any broader full-PASS global acceptance",
        ),
        required_parent_provenance=_PARENT_PROVENANCE_STATEMENT,
        requires_injected_fresh_attested_factory=True,
        requires_reviews_before_live=True,
    ),
)

PARENT_BEARING_CELL_IDS: frozenset[str] = frozenset(
    plan.cell_id for plan in CELL_PLAN if plan.required_parent_provenance
)

AUDIT_CELL_ID = "failure_audit_written"

__all__ = [
    "AUDIT_CELL_ID",
    "BLOCKED_EXACT_MODULE_NAMES",
    "BLOCKED_MODULE_FRAGMENTS",
    "CELL_PLAN",
    "E2A_DENYLIST_TABLES_ALL_ZERO",
    "E2A_STALE_DELETION_TABLES",
    "LIVE_GATE_ORDER",
    "PARENT_BEARING_CELL_IDS",
    "RESULT_FIELD_CONTRACT",
    "TASK88_REQUIRED_CELL_ID",
    "CellPlan",
    "module_name_is_blocked",
    "validate_denylist_dml_counts",
    "validate_result_field_contract",
]
