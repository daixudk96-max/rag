"""Shared pure types and constants for the Task #90 slice.

Non-collected (underscore prefix) support: pure data only. This module
contains no environment variable access, no database access, no Docker
access, and no production imports. It owns the redacted observation shape
for the Task #90 controlled live producer's wire-only component, the
full-collection scope snapshot shape, and the exact table/outcome/field
constants the Task #90 proof relies on.

Security contract:

- No environment variable access of any kind; no DATABASE_URL anywhere.
- No URI, credential, target, container token, or raw fixture content is
  ever stored in an observation; the repr redacts ``error_reason`` so the
  bounded class/type-only diagnostic is the only string that could ever
  leave the observation surface.
- No test framework machinery, no skip or xfail mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, NamedTuple

# The 15 canonical E2a primary tables and the 10 denylist tables, pinned to
# the exact key sets of the production E2aReconciliationResult count maps
# (verified against e2a_materialization_repository in the contract suite).
TASK90_PRIMARY_TABLES = frozenset(
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

TASK90_DENYLIST_TABLES = frozenset(
    {
        "chunk_entity_links",
        "node_entity_links",
        "entity_mentions",
        "entity_aliases",
        "entity_merge_log",
        "ner_entities",
        "ner_relations",
        "fusion_state",
        "r3_state",
        "external_projection_status",
    }
)

TASK90_CACHE_TABLES = frozenset(
    {"summaries", "node_embeddings", "semantic_distribution"}
)

# The only real reconciliation outcomes a Task #90 binding may certify.
# ``changed`` (first reconcile) and ``no_op`` (equivalent rerun) are the
# honest success contract; every other Outcome literal is rejected because
# a blocked/skipped/rolled-back/unknown reconciliation cannot certify the
# durable no-op idempotency claim.
TASK90_VALID_OUTCOMES = ("changed", "no_op")

# The 14 objective observation fields of the Task #90 controlled live
# producer, each asserted exactly once by the selected live acceptance
# test. Field names are pinned here so the live selector, the observation
# dataclass, the AST proof, and the contract tests share one source of
# truth.
REQUIRED_OBSERVATION_FIELDS = frozenset(
    {
        "admitted_state_complete",
        "admitted_has_manual_relation",
        "admitted_has_raw_pair",
        "admitted_has_resolved_evidence",
        "reconcile_first_changed",
        "rerun_no_op",
        "rerun_primary_dml_all_zero",
        "denylist_exact_zero",
        "default_reconciler_default_repository",
        "exact_returned_objects_kept",
        "pre_post_scope_snapshots_equal",
        "binding_built_in_invocation",
        "binding_verifies",
        "artifact_redacted",
    }
)

# Shell-hygiene variable set: never read, never passed to child processes.
SENSITIVE_ENV_VARS = frozenset(
    {
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    }
)

# Explicit allowlist of non-sensitive runtime keys read individually by the
# child-environment builders. Disjoint from SENSITIVE_ENV_VARS by contract.
SANITIZED_ALLOWLIST = (
    "PATH",
    "HOME",
    "SystemRoot",
    "PATHEXT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)

LIVE_SELECTOR_FILENAME = "phase15_e2a_task90_live_acceptance.py"
LIVE_TEST_NAME = "test_task90_authorized_live_acceptance"
METADATA_TEST_NAME = "test_task90_live_acceptance_metadata"
HELPER_IMPL_FUNCTION = "_run_task90_live_proof"


@dataclass(frozen=True)
class Task90ScopeSnapshot:
    """Independent fresh-observer observation of the full E2a table scope.

    Covers the exact 15 primary tables, the 10 denylist tables, and the 3
    cache-invalidation tables so a binding's scope digest is computed over
    the complete collection, not a reduced axis. Defensive copies are made
    at construction time; input mappings are frozen. Values are validated
    as exact built-in nonnegative int (bool rejected). ``denylist`` permits
    None for physically absent tables.
    """

    counts: Mapping[str, int]
    digests: Mapping[str, str]
    denylist: Mapping[str, int | None]
    cache_invalidation: Mapping[str, int]
    sync_ts: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))
        object.__setattr__(self, "digests", MappingProxyType(dict(self.digests)))
        object.__setattr__(self, "denylist", MappingProxyType(dict(self.denylist)))
        object.__setattr__(
            self,
            "cache_invalidation",
            MappingProxyType(dict(self.cache_invalidation)),
        )
        if set(self.counts) != TASK90_PRIMARY_TABLES:
            raise ValueError("task90_snapshot_primary_tables_invalid")
        if set(self.denylist) != TASK90_DENYLIST_TABLES:
            raise ValueError("task90_snapshot_denylist_invalid")
        if set(self.cache_invalidation) != TASK90_CACHE_TABLES:
            raise ValueError("task90_snapshot_cache_tables_invalid")
        for key, value in self.counts.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"task90_snapshot_counts[{key}]_invalid")
        for key, value in self.digests.items():
            if type(value) is not str or not value:
                raise ValueError(f"task90_snapshot_digests[{key}]_invalid")
        for key, value in self.denylist.items():
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"task90_snapshot_denylist[{key}]_invalid")
        for key, value in self.cache_invalidation.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"task90_snapshot_cache_invalidation[{key}]_invalid")
        if self.sync_ts is not None and type(self.sync_ts) is not str:
            raise ValueError("task90_snapshot_sync_ts_invalid")


def make_task90_scope_snapshot(
    counts: Mapping[str, int],
    digests: Mapping[str, str],
    denylist: Mapping[str, int | None],
    cache_invalidation: Mapping[str, int],
    sync_ts: str | None = None,
) -> Task90ScopeSnapshot:
    """Construct a Task90ScopeSnapshot with defensive copies of all inputs.

    The dataclass ``__post_init__`` creates additional independent copies,
    so this factory is the preferred entry point for callers that hold
    mutable source mappings.
    """
    return Task90ScopeSnapshot(
        counts=MappingProxyType(dict(counts)),
        digests=MappingProxyType(dict(digests)),
        denylist=MappingProxyType(dict(denylist)),
        cache_invalidation=MappingProxyType(dict(cache_invalidation)),
        sync_ts=sync_ts,
    )


class Task90Observations(NamedTuple):
    """Redacted observations for the Task #90 controlled live producer.

    Every field is an objective boolean observed by the single controlled
    invocation of the live producer. ``success`` defaults to True so a
    completed cell is honest, and ``error_reason`` carries only the bounded
    class/type-only diagnostic on failure. The repr redacts ``error_reason``
    and never renders credentials, URIs, targets, or raw corpus text.
    """

    admitted_state_complete: bool
    admitted_has_manual_relation: bool
    admitted_has_raw_pair: bool
    admitted_has_resolved_evidence: bool
    reconcile_first_changed: bool
    rerun_no_op: bool
    rerun_primary_dml_all_zero: bool
    denylist_exact_zero: bool
    default_reconciler_default_repository: bool
    exact_returned_objects_kept: bool
    pre_post_scope_snapshots_equal: bool
    binding_built_in_invocation: bool
    binding_verifies: bool
    artifact_redacted: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"Task90Observations({rendered}, details=<redacted>)"


__all__ = [
    "TASK90_CACHE_TABLES",
    "TASK90_DENYLIST_TABLES",
    "TASK90_PRIMARY_TABLES",
    "TASK90_VALID_OUTCOMES",
    "REQUIRED_OBSERVATION_FIELDS",
    "SENSITIVE_ENV_VARS",
    "SANITIZED_ALLOWLIST",
    "LIVE_SELECTOR_FILENAME",
    "LIVE_TEST_NAME",
    "METADATA_TEST_NAME",
    "HELPER_IMPL_FUNCTION",
    "Task90ScopeSnapshot",
    "make_task90_scope_snapshot",
    "Task90Observations",
]
