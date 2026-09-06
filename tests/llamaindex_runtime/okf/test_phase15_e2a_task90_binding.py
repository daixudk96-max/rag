"""Task #90 default-collected binding contract suite (constraints D and E).

This file is the default-collected surface of the Task #90 process-local
structural binding. It asserts, without any database or Docker:

- the binding holds the EXACT ``E2aReconciliationResult`` object identity
  (``is``), the invocation UUID, the canonical digest of the FULL result
  fields (derived at runtime via ``dataclasses.fields``), and the
  independent fresh-observer full-collection ``Task90ScopeSnapshot`` plus
  its digest; only the controlled producer (a single-use build token) can
  build a verifiable binding;
- the redacted canonical artifact is structural metadata only and is NOT
  re-constructible into a verifiable binding;
- negative cases are rejected: plain dicts, hand-built exact-type results
  without a producer binding, fake/stub reconciler routes,
  serializer-only artifacts, blocked/skipped/rolled-back/unknown
  outcomes, invented result fields, tampered result/scope identity, and
  missing or stale invocations;
- the full 15-table primary collection is required of every scope snapshot.

No database, no Docker, no authorized live selector invocation, and no
production symbol change is performed here.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aReconciliationResult,
    canonical_json,
    canonical_json_sha256,
)

from ._phase15_e2a_task90_support import (
    TASK90_ARTIFACT_SCHEMA,
    TASK90_CANONICAL_ROUTE,
    Task90EvidenceBinding,
    _artifact_digest,
    _canonical_artifact_json,
    _error_reason,
    _result_fields_digest,
    _scope_snapshot_digest,
    acquire_build_token,
    build_evidence_binding,
)
from ._phase15_e2a_task90_types import (
    TASK90_CACHE_TABLES,
    TASK90_DENYLIST_TABLES,
    TASK90_PRIMARY_TABLES,
    make_task90_scope_snapshot,
)

_DIGEST = "a" * 64


def _result(*, outcome: str = "changed") -> E2aReconciliationResult:
    """Build a real E2aReconciliationResult with one relations DML row."""
    return E2aReconciliationResult(
        outcome=outcome,  # type: ignore[arg-type]
        manifest_sha256=_DIGEST,
        primary_dml_by_table={
            **{table: 0 for table in TASK90_PRIMARY_TABLES},
            "relations": 1,
        },
        denylist_dml_counts={table: 0 for table in TASK90_DENYLIST_TABLES},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={table: 0 for table in TASK90_CACHE_TABLES},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )


def _snapshot() -> Any:
    """Build a complete independent fresh-observer Task90ScopeSnapshot."""
    return make_task90_scope_snapshot(
        counts={
            table: (1 if table == "relations" else 0) for table in TASK90_PRIMARY_TABLES
        },
        digests={table: f"{table}-scope-digest" for table in TASK90_PRIMARY_TABLES},
        denylist={table: 0 for table in TASK90_DENYLIST_TABLES},
        cache_invalidation={table: 0 for table in TASK90_CACHE_TABLES},
        sync_ts=None,
    )


def _binding() -> Task90EvidenceBinding:
    return build_evidence_binding(
        acquire_build_token(),
        _result(),
        _snapshot(),
    )


# =============================================================================
# Constraint D: binding positive surface
# =============================================================================


def test_binding_builds_and_verifies() -> None:
    """A producer-built binding verifies and exposes the structural surface."""
    result = _result()
    snapshot = _snapshot()
    token = acquire_build_token()
    binding = build_evidence_binding(token, result, snapshot)

    binding.verify()
    assert binding.outcome == "changed"
    assert binding.invocation_id == token.invocation_id
    assert len(binding.invocation_id) == 36
    assert binding.result_digest == _result_fields_digest(result)
    assert binding.scope_digest == _scope_snapshot_digest(snapshot)
    assert binding.result is result
    assert binding.scope_snapshot is snapshot


def test_binding_holds_exact_returned_result_identity() -> None:
    """The binding verifies the EXACT returned object via ``is``."""
    result = _result()
    binding = build_evidence_binding(acquire_build_token(), result, _snapshot())
    assert binding.verify_exact_result(result) is True
    forged = dataclasses.replace(result, manifest_sha256=result.manifest_sha256)
    assert forged == result
    assert forged is not result
    assert binding.verify_exact_result(forged) is False


def test_binding_verify_exact_scope_requires_identity() -> None:
    """The binding verifies the exact fresh-observer scope snapshot via ``is``."""
    snapshot = _snapshot()
    binding = build_evidence_binding(acquire_build_token(), _result(), snapshot)
    assert binding.verify_exact_scope(snapshot) is True
    forged = make_task90_scope_snapshot(
        counts=dict(snapshot.counts),
        digests=dict(snapshot.digests),
        denylist=dict(snapshot.denylist),
        cache_invalidation=dict(snapshot.cache_invalidation),
    )
    assert forged == snapshot
    assert forged is not snapshot
    assert binding.verify_exact_scope(forged) is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda result: dataclasses.replace(result, manifest_sha256="b" * 64),
        lambda result: dataclasses.replace(
            result, primary_dml_by_table={**result.primary_dml_by_table, "relations": 2}
        ),
        lambda result: dataclasses.replace(result, comparator_parity=False),
        lambda result: dataclasses.replace(
            result, stale_deletion_counts={"relations": 1}
        ),
    ],
)
def test_binding_result_digest_covers_every_contract_field(mutator: Any) -> None:
    """Changing any full-contract field changes the canonical result digest."""
    baseline = _result()
    baseline_digest = _result_fields_digest(baseline)
    altered = mutator(baseline)
    assert _result_fields_digest(altered) != baseline_digest


def test_binding_result_digest_field_names_come_from_production_fields() -> None:
    """The digest derives its field list at runtime from the production contract."""
    result = _result()
    names = tuple(field.name for field in dataclasses.fields(E2aReconciliationResult))
    assert len(names) == 10
    digest = _result_fields_digest(result)
    payload = {
        "schema": "e2a-task90-binding-v1",
        "field_names": names,
        "values": {
            field.name: getattr(result, field.name)
            for field in dataclasses.fields(E2aReconciliationResult)
        },
    }
    assert digest == canonical_json_sha256(payload)


def test_binding_artifact_redacted_and_canonical() -> None:
    """The redacted artifact carries structural metadata only, deterministically."""
    binding = _binding()
    artifact: Mapping[str, object] = binding.artifact_dict()
    assert artifact["schema"] == TASK90_ARTIFACT_SCHEMA
    assert artifact["invocation_id"] == binding.invocation_id
    assert artifact["outcome"] == "changed"
    assert artifact["result_digest"] == binding.result_digest
    assert artifact["scope_digest"] == binding.scope_digest
    assert set(artifact["primary_counts"]) == TASK90_PRIMARY_TABLES  # type: ignore[arg-type]
    assert set(artifact["denylist_counts"]) == TASK90_DENYLIST_TABLES  # type: ignore[arg-type]
    for forbidden in ("error_reason", "credentials", "password", "DATABASE_URL"):
        assert forbidden not in artifact
        assert forbidden not in _canonical_artifact_json(artifact)
    assert _canonical_artifact_json(artifact) == canonical_json(artifact)
    assert _artifact_digest(artifact) == canonical_json_sha256(artifact)
    assert _artifact_digest(artifact) == _artifact_digest(dict(artifact))


def test_binding_artifact_no_rebuild_api() -> None:
    """A serializer-only artifact cannot be rebuilt into a verifiable binding."""
    assert not hasattr(Task90EvidenceBinding, "from_dict")
    assert not hasattr(Task90EvidenceBinding, "from_artifact")
    assert not hasattr(Task90EvidenceBinding, "load")
    artifact = _binding().artifact_dict()
    token = acquire_build_token()
    with pytest.raises(TypeError):
        build_evidence_binding(token, artifact, _snapshot())


# =============================================================================
# Constraint E: negative rejection surface
# =============================================================================


def test_binding_rejects_plain_dict_result() -> None:
    """A plain dict result is rejected (not the exact production type)."""
    result_dict = {"outcome": "changed", "invented": 1}
    with pytest.raises(TypeError, match="task90_binding_result_must_be_exact"):
        build_evidence_binding(acquire_build_token(), result_dict, _snapshot())


def test_binding_rejects_hand_built_exact_type_without_producer_binding() -> None:
    """A hand-built exact-type result without a producer token is rejected."""
    result = _result()
    snapshot = _snapshot()
    with pytest.raises(TypeError, match="task90_binding_token_required"):
        Task90EvidenceBinding(
            token=object(),  # type: ignore[arg-type]
            result=result,
            scope_snapshot=snapshot,
            route=TASK90_CANONICAL_ROUTE,
        )
    with pytest.raises(TypeError, match="task90_binding_token_required"):
        Task90EvidenceBinding(
            token=None,  # type: ignore[arg-type]
            result=result,
            scope_snapshot=snapshot,
            route=TASK90_CANONICAL_ROUTE,
        )


def test_binding_rejects_fake_stub_reconciler_route() -> None:
    """A fake/stub reconciler route string is rejected by the factory."""
    with pytest.raises(ValueError, match="task90_route_not_controlled"):
        build_evidence_binding(
            acquire_build_token(),
            _result(),
            _snapshot(),
            route="fake-stub-reconciler",
        )


def test_binding_rejects_serializer_only_artifact() -> None:
    """Feeding a serializer-only artifact to the builder is rejected."""
    artifact = _binding().artifact_dict()
    with pytest.raises(TypeError, match="task90_binding_result_must_be_exact"):
        build_evidence_binding(acquire_build_token(), artifact, _snapshot())


@pytest.mark.parametrize(
    "outcome",
    ["rolled_back_failure", "acceptance_blocked", "outcome_unknown"],
)
def test_binding_rejects_blocked_or_unknown_outcomes(outcome: str) -> None:
    """Only real changed/no_op reconciliation may be certified by a binding."""
    result = _result(outcome=outcome)
    assert result.outcome == outcome
    with pytest.raises(ValueError, match="task90_outcome_unsupported"):
        build_evidence_binding(acquire_build_token(), result, _snapshot())


def test_outcome_literal_rejects_skipped_invented_value() -> None:
    """'skipped' is not a real reconciliation Outcome literal at all."""
    with pytest.raises(ValueError):
        _result(outcome="skipped")


def test_binding_rejects_invented_result_field() -> None:
    """An invented extra field on the result surface is rejected."""
    invented = {
        **{
            field.name: getattr(_result(), field.name)
            for field in dataclasses.fields(E2aReconciliationResult)
        },
        "invented_field": True,
    }
    with pytest.raises(TypeError, match="task90_binding_result_must_be_exact"):
        build_evidence_binding(acquire_build_token(), invented, _snapshot())


def test_binding_verify_rejects_tampered_result_identity() -> None:
    """A value-equal but distinct result object is not the exact returned one."""
    result = _result()
    binding = build_evidence_binding(acquire_build_token(), result, _snapshot())
    forged = dataclasses.replace(result)
    assert forged == result and forged is not result
    assert binding.verify_exact_result(forged) is False
    assert binding.verify_exact_result(result) is True


def test_binding_verify_rejects_tampered_scope_identity() -> None:
    """A rebuilt scope snapshot is not the exact fresh-observer observation."""
    snapshot = _snapshot()
    binding = build_evidence_binding(acquire_build_token(), _result(), snapshot)
    tampered = make_task90_scope_snapshot(
        counts=dict(snapshot.counts),
        digests={**dict(snapshot.digests), "relations": "tampered-scope-digest"},
        denylist=dict(snapshot.denylist),
        cache_invalidation=dict(snapshot.cache_invalidation),
    )
    assert binding.verify_exact_scope(tampered) is False
    assert binding.verify_exact_scope(snapshot) is True
    assert _scope_snapshot_digest(tampered) != _scope_snapshot_digest(snapshot)


def test_binding_rejects_missing_invocation() -> None:
    """There is no producer-less route to a binding: a token is always required."""
    result = _result()
    with pytest.raises(TypeError, match="task90_binding_token_required"):
        Task90EvidenceBinding(
            token=None,  # type: ignore[arg-type]
            result=result,
            scope_snapshot=_snapshot(),
            route=TASK90_CANONICAL_ROUTE,
        )


def test_binding_rejects_stale_invocation() -> None:
    """A token is single-use; a second build is a stale-invocation error."""
    token = acquire_build_token()
    first = build_evidence_binding(token, _result(), _snapshot())
    assert first.verify() is None
    assert token.consumed is True
    with pytest.raises(ValueError, match="task90_invocation_stale"):
        build_evidence_binding(token, _result(), _snapshot())


def test_binding_rejects_wrong_scope_type() -> None:
    """A non-Task90ScopeSnapshot scope is rejected."""
    with pytest.raises(TypeError, match="task90_binding_scope_must_be_exact"):
        build_evidence_binding(
            acquire_build_token(),
            _result(),
            scope_snapshot={"counts": {}},  # type: ignore[arg-type]
        )


def test_binding_error_reason_is_bounded_class_type_only() -> None:
    """The failure diagnostic never echoes exception text."""
    reason = _error_reason("task90_cell_failed", RuntimeError("sensitive secret"))
    assert reason == "task90_cell_failed:RuntimeError"
    assert "sensitive secret" not in reason


# =============================================================================
# Scope snapshot full-collection requirements (constraint I)
# =============================================================================


def test_scope_snapshot_requires_full_primary_collection() -> None:
    """Every scope snapshot must cover the exact 15 primary tables."""
    full = _snapshot()
    assert set(full.counts) == TASK90_PRIMARY_TABLES
    assert len(full.counts) == 15
    missing = dict(full.counts)
    missing.pop("relations")
    with pytest.raises(ValueError, match="task90_snapshot_primary_tables_invalid"):
        make_task90_scope_snapshot(
            counts=missing,
            digests=dict(full.digests),
            denylist=dict(full.denylist),
            cache_invalidation=dict(full.cache_invalidation),
        )


def test_scope_snapshot_requires_full_denylist_collection() -> None:
    """Every scope snapshot must cover the exact 10 denylist tables."""
    full = _snapshot()
    missing = dict(full.denylist)
    missing.pop("fusion_state")
    with pytest.raises(ValueError, match="task90_snapshot_denylist_invalid"):
        make_task90_scope_snapshot(
            counts=dict(full.counts),
            digests=dict(full.digests),
            denylist=missing,
            cache_invalidation=dict(full.cache_invalidation),
        )


def test_scope_snapshot_rejects_bool_and_negative_counts() -> None:
    """Counts must be exact built-in nonnegative ints (bool rejected)."""
    full = _snapshot()
    with pytest.raises(ValueError):
        make_task90_scope_snapshot(
            counts={**dict(full.counts), "relations": True},
            digests=dict(full.digests),
            denylist=dict(full.denylist),
            cache_invalidation=dict(full.cache_invalidation),
        )
    with pytest.raises(ValueError):
        make_task90_scope_snapshot(
            counts={**dict(full.counts), "relations": -1},
            digests=dict(full.digests),
            denylist=dict(full.denylist),
            cache_invalidation=dict(full.cache_invalidation),
        )


def test_scope_snapshot_digest_changes_when_count_tampered() -> None:
    """A tampered primary count changes the scope digest."""
    snapshot = _snapshot()
    baseline = _scope_snapshot_digest(snapshot)
    tampered = make_task90_scope_snapshot(
        counts={**dict(snapshot.counts), "relations": 2},
        digests=dict(snapshot.digests),
        denylist=dict(snapshot.denylist),
        cache_invalidation=dict(snapshot.cache_invalidation),
    )
    assert _scope_snapshot_digest(tampered) != baseline


def test_scope_snapshot_is_defensive_against_mutable_input() -> None:
    """The snapshot freezes its inputs; later mutation cannot alter it."""
    counts = {table: 0 for table in TASK90_PRIMARY_TABLES}
    snapshot = make_task90_scope_snapshot(
        counts=counts,
        digests={table: "d" for table in TASK90_PRIMARY_TABLES},
        denylist={table: 0 for table in TASK90_DENYLIST_TABLES},
        cache_invalidation={table: 0 for table in TASK90_CACHE_TABLES},
    )
    counts["relations"] = 99
    assert snapshot.counts["relations"] == 0
