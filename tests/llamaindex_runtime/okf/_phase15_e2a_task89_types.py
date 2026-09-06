"""Shared frozen observation types and constants for the Task #89 slice.

Non-collected (underscore prefix) support: pure data only. This module
contains no environment variable access, no database access, no Docker
access, and no production imports. It owns the redacted observation shape
for the Task #89 durable-integration composed proof's live component.

Security contract:

- No environment variable access of any kind; no DATABASE_URL anywhere.
- No URI, credential, target, container token, or raw fixture content is
  ever stored in an observation; the repr redacts ``error_reason`` so the
  bounded class/type-only diagnostic is the only string that could ever
  leave the observation surface.
- No test framework machinery, no skip or xfail mechanics.
"""

from __future__ import annotations

from typing import NamedTuple

# The 25 objective observation fields of the Task #89 durable-integration
# composed proof's live component, each asserted exactly once by the
# selected live acceptance test. Field names are pinned here so the live
# selector, the observation dataclass, the AST proof, and the contract
# tests all share one source of truth.
REQUIRED_OBSERVATION_FIELDS = frozenset(
    {
        "ingest_calls_exact_one",
        "convert_calls_exact_one",
        "serialize_calls_exact_one",
        "publish_raw_files_exact_three",
        "admit_calls_exact_one",
        "reconcile_calls_exact_one",
        "wrappers_call_originals",
        "admitted_is_reconcile_object",
        "result_real_reconciliation_result",
        "ingest_result_reconciliation_captured",
        "factory_conn_distinct",
        "factory_autocommit_false_pre_reconcile",
        "factory_closed_after",
        "registry_open_through_observer",
        "writer_closed_by_helper",
        "legacy_ingest_trap_active",
        "write_spans_trap_active",
        "write_tree_trap_active",
        "legacy_persistence_traps_active",
        "index_tree_fails_closed",
        "flatten_embedded_tree_fails_closed",
        "denylist_counts_exact_zero",
        "observer_primary_durable",
        "retrieve_hits_exact_ids",
        "smoke_no_quality_claim",
    }
)

# The four retrieval smoke query families are reachability-only and carry
# an explicit ``no_quality_claim`` label; no recall, precision, or Level
# assertion is ever made (per the Phase 15 acceptance matrix).
SMOKE_FAMILIES = ("R1", "R2a", "R2b", "p6")

# Repo-relative path (tuple of components) of the frozen sectioned-pdf
# source fixture used by the live integration helper. Kept as components
# so the live cells can resolve it against the worktree root without any
# environment reads.
SOURCE_PDF_RELATIVE = (
    "tests",
    "fixtures",
    "okf_roundtrip",
    "sectioned-pdf",
    "source.pdf",
)


class Task89Observations(NamedTuple):
    """Redacted observations for the Task #89 durable-integration cell.

    Every field is an objective boolean observed by the single real
    invocation of the durable integration helper. ``success`` defaults to
    True so a completed cell is honest, and ``error_reason`` carries only
    the bounded class/type-only diagnostic on failure. The repr redacts
    ``error_reason`` and never renders credentials, URIs, targets, or raw
    corpus text.
    """

    ingest_calls_exact_one: bool
    convert_calls_exact_one: bool
    serialize_calls_exact_one: bool
    publish_raw_files_exact_three: bool
    admit_calls_exact_one: bool
    reconcile_calls_exact_one: bool
    wrappers_call_originals: bool
    admitted_is_reconcile_object: bool
    result_real_reconciliation_result: bool
    ingest_result_reconciliation_captured: bool
    factory_conn_distinct: bool
    factory_autocommit_false_pre_reconcile: bool
    factory_closed_after: bool
    registry_open_through_observer: bool
    writer_closed_by_helper: bool
    legacy_ingest_trap_active: bool
    write_spans_trap_active: bool
    write_tree_trap_active: bool
    legacy_persistence_traps_active: bool
    index_tree_fails_closed: bool
    flatten_embedded_tree_fails_closed: bool
    denylist_counts_exact_zero: bool
    observer_primary_durable: bool
    retrieve_hits_exact_ids: bool
    smoke_no_quality_claim: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"Task89Observations({rendered}, details=<redacted>)"
