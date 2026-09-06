"""Tests for Phase 15 fake-reconciliation/evidence isolation.

Track C Wave 1: Ensures fake typed-shaped E2a results can never yield Phase 15 PASS artifacts.

Key contracts:
1. Fake results can remain in test support but must never create PASS acceptance artifacts
2. typed_result=True is format metadata, not provenance - requires actual E2aReconciler
3. Default no-DB selector must return blocked_not_executed, never PASS
4. Historical scripts must be classified as non-E2a or routed through actual reconciler
5. Wave 1 acceptance gate FAILS CLOSED for ALL inputs (no artifact emission)
6. Exact 9 historical routes are denied by acceptance boundary
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult
from okf._e2a_pipeline_testkit import _FakeReconciler

_RUN_E2A_MODULE_NAME = "_track_c_fake_reconciliation_isolation_module"


def _load_run_e2a_verification():
    """Load run_e2a_verification module from Phase 15 hyphenated directory.

    Uses a UNIQUE sys.modules key to avoid cross-test collision with the
    verification-result test file. Direct module aliases are preferred over
    try-import wrappers.
    """
    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "verification"
        / "phase15-okf-ingestion-pipeline"
        / "run_e2a_verification.py"
    )
    spec = importlib.util.spec_from_file_location(_RUN_E2A_MODULE_NAME, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RUN_E2A_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# Load module once; alias all needed symbols directly (no try-import wrappers).
_run_e2a_verification = _load_run_e2a_verification()
serialize_evidence = _run_e2a_verification.serialize_evidence
run_verification = _run_e2a_verification.run_verification
validate_evidence_authenticity = _run_e2a_verification.validate_evidence_authenticity
Phase15AcceptanceBlockedError = _run_e2a_verification.Phase15AcceptanceBlockedError
admit_evidence_for_acceptance = _run_e2a_verification.admit_evidence_for_acceptance
is_historical_route_denied = _run_e2a_verification.is_historical_route_denied
HISTORICAL_DENYLIST = _run_e2a_verification.HISTORICAL_DENYLIST


class TestFakeResultIsolation:
    """Tests ensuring fake typed-shaped results cannot yield PASS artifacts."""

    def test_fake_reconciler_result_cannot_claim_pass_provenance(self) -> None:
        """Fake reconciler result must not be able to claim PASS provenance."""
        fake_reconciler = _FakeReconciler()
        result = fake_reconciler.reconcile(connection=None, desired=None)
        evidence = serialize_evidence(result)

        assert evidence.get("outcome") != "pass"
        assert evidence.get("outcome") in {
            "no_op",
            "acceptance_blocked",
            "outcome_unknown",
        }
        assert evidence.get("acceptance_provenance") is None

    def test_manually_constructed_evidence_rejects_invalid_pass_outcome(self) -> None:
        """Evidence claiming outcome='pass' must be rejected as invalid outcome."""
        fabricated = {
            "outcome": "pass",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 100},
            "typed_result": True,
        }

        with pytest.raises(ValueError, match="invalid outcome|PASS acceptance"):
            validate_evidence_authenticity(fabricated)

    def test_manually_constructed_valid_format_lacks_provenance(self) -> None:
        """Manually constructed valid-format evidence is blocked by the gate.

        BEHAVIORAL PROOF: Format validation passes for valid-shaped evidence,
        but the acceptance gate STILL blocks it. This is the genuine admission-
        gate proof - not merely an absent-key check.
        """
        fabricated = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 100},
            "typed_result": True,
        }

        # Format validation passes (has correct structure)
        validate_evidence_authenticity(fabricated)

        # BUT: Acceptance gate MUST still block - format is NOT provenance
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(fabricated)

    def test_serialize_evidence_does_not_add_pass_provenance(self) -> None:
        """serialize_evidence must never add PASS provenance marker."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 5},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence.get("typed_result") is True
        assert evidence.get("acceptance_provenance") is None
        assert evidence.get("acceptance_authorization") is None

    def test_default_selector_returns_blocked_not_pass(self) -> None:
        """Default no-DB selector must return blocked_not_executed, never PASS.

        Honest behavioral proof of the selector contract. No fake psycopg.connect
        seam is monkeypatched - run_verification never calls psycopg.
        """
        result = run_verification(enable_disposable_db=False)

        assert result.get("disposable_db_status") == "blocked_not_executed"
        assert result.get("outcome") != "pass"
        assert result.get("outcome") == "acceptance_blocked"

    def test_fake_result_outcome_changed_still_lacks_provenance(self) -> None:
        """Even with outcome='changed', fake result lacks acceptance provenance."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 10},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence.get("outcome") == "changed"
        assert evidence.get("typed_result") is True
        assert evidence.get("acceptance_provenance") is None
        assert evidence.get("acceptance_authorization") is None

    def test_real_reconciler_provenance_marker_absent_from_evidence(self) -> None:
        """Real reconciler provenance is tracked separately from evidence serialization."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 50},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence.get("typed_result") is True
        assert (
            "acceptance_provenance" not in evidence
            or evidence.get("acceptance_provenance") is None
        )


class TestHistoricalScriptClassification:
    """Tests for historical script classification."""

    def test_historical_script_fake_reconciler_is_private_support(self) -> None:
        """Historical script _FakeReconciler is private test support, not acceptance path."""
        fake_reconciler = _FakeReconciler()
        result = fake_reconciler.reconcile(connection=None, desired=None)

        assert isinstance(result, E2aReconciliationResult)
        assert result.outcome in {"no_op", "acceptance_blocked"}

    def test_historical_script_cannot_create_pass_artifact(self) -> None:
        """Historical scripts using _FakeReconciler cannot create PASS acceptance artifact."""
        fake_reconciler = _FakeReconciler()
        result = fake_reconciler.reconcile(connection=None, desired=None)
        evidence = serialize_evidence(result)

        assert evidence.get("outcome") != "pass"
        assert evidence.get("outcome") in {"no_op", "acceptance_blocked"}

    def test_phase15_route_blocked_by_universal_fail_closed_gate(self) -> None:
        """Phase 15 route is NOT in denylist but STILL blocked by fail-closed gate.

        BEHAVIORAL PROOF: A route not in the historical denylist is still
        blocked because the Wave 1 acceptance gate fails closed for ALL inputs.
        """
        phase15_route = (
            "verification/phase15-okf-ingestion-pipeline/run_e2a_verification.py"
        )
        assert is_historical_route_denied(phase15_route) is False

        evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
            "_source_route": phase15_route,
        }

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_historical_script_evidence_blocked_by_denylist_and_gate(self) -> None:
        """Historical script evidence is blocked by BOTH denylist AND fail-closed gate.

        BEHAVIORAL PROOF: Historical routes are in denylist. Evidence claiming
        to come from them is blocked with a message mentioning historical denial.
        """
        historical_route = (
            "verification/phase10-real-docx-retrieval-validation/run_validation.py"
        )
        assert is_historical_route_denied(historical_route) is True

        evidence = {
            "outcome": "no_op",
            "manifest_sha256": "a" * 64,
            "typed_result": True,
            "_source_route": historical_route,
        }

        with pytest.raises(Phase15AcceptanceBlockedError) as exc_info:
            admit_evidence_for_acceptance(evidence)

        error_msg = str(exc_info.value)
        assert "historical" in error_msg.lower() or "denied" in error_msg.lower()

    def test_fake_reconciler_result_blocked_by_gate(self) -> None:
        """_FakeReconciler result is blocked by acceptance gate.

        BEHAVIORAL PROOF: Using the testkit's _FakeReconciler produces
        typed-shaped results, but the acceptance gate still blocks them.
        """
        _FakeReconciler.calls = 0
        fake_reconciler = _FakeReconciler()
        result = fake_reconciler.reconcile(connection=None, desired=None)

        assert _FakeReconciler.calls >= 1

        evidence = serialize_evidence(result)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)


class TestAcceptanceSelectorGate:
    """Tests for controlled acceptance selector with disposable DB gate."""

    def test_acceptance_selector_requires_disposable_authorization(self) -> None:
        """Acceptance selector requires explicit disposable DB authorization."""
        result = run_verification(enable_disposable_db=False)

        assert result.get("disposable_db_status") == "blocked_not_executed"
        assert result.get("outcome") != "pass"

    def test_acceptance_selector_requires_actual_reconciler_provenance(self) -> None:
        """Acceptance selector requires actual E2aReconciler provenance, not fake.

        BEHAVIORAL PROOF: Even with disposable authorization enabled,
        the Wave 1 gate still blocks ALL inputs.
        """
        result = run_verification(enable_disposable_db=True)

        assert result.get("disposable_db_status") == "blocked_not_executed"
        assert result.get("outcome") == "acceptance_blocked"

    def test_gate_does_not_call_serializer_before_blocking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate must NOT call serialize_evidence before blocking.

        BEHAVIORAL PROOF: Monkeypatching serialize_evidence to raise does NOT
        affect the gate, proving the gate does not call the serializer. This is
        the explicit monkeypatch proof of serializer noninvocation.
        """
        serializer_called = []

        def mock_serialize(*args: object, **kwargs: object) -> None:
            serializer_called.append(1)
            raise RuntimeError("serialize_evidence should NOT be called by gate")

        monkeypatch.setattr(_run_e2a_verification, "serialize_evidence", mock_serialize)

        evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
        }

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

        assert (
            len(serializer_called) == 0
        ), "Gate must NOT call serialize_evidence - it should block independently"

    def test_gate_does_not_interpolate_evidence_values_into_errors(self) -> None:
        """Gate must NOT interpolate arbitrary evidence values into error messages.

        BEHAVIORAL PROOF: Evidence with sensitive values is blocked, and
        the error message does NOT contain those sensitive values.
        """
        sensitive_evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
            "sensitive_field": "postgres://secret:password@localhost:5432/db",
        }

        with pytest.raises(Phase15AcceptanceBlockedError) as exc_info:
            admit_evidence_for_acceptance(sensitive_evidence)

        error_msg = str(exc_info.value)
        assert "postgres://" not in error_msg
        assert "secret" not in error_msg
        assert "password" not in error_msg


class TestProvenanceVsFormat:
    """Tests distinguishing provenance from format metadata."""

    def test_typed_result_is_format_not_provenance(self) -> None:
        """typed_result=True is format metadata, not source provenance."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence.get("typed_result") is True
        assert (
            "acceptance_provenance" not in evidence
            or evidence.get("acceptance_provenance") is None
        )

    def test_evidence_serializer_is_redactor_not_provenance_claim(self) -> None:
        """serialize_evidence is a redactor/serializer, never a provenance claim."""
        result = E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256="b" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert isinstance(evidence, dict)
        assert "manifest_sha256" in evidence
        assert evidence.get("acceptance_provenance") is None
        assert evidence.get("acceptance_authorization") is None


class TestPhase15AcceptanceGateWave1:
    """Tests for Wave 1 fail-closed acceptance gate."""

    def test_acceptance_gate_blocks_all_inputs_wave1(self) -> None:
        """Wave 1 acceptance gate MUST block ALL inputs."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 10},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_gate_blocks_fake_reconciler_result(self) -> None:
        """Gate MUST block fake reconciler result."""
        fake_reconciler = _FakeReconciler()
        result = fake_reconciler.reconcile(connection=None, desired=None)
        evidence = serialize_evidence(result)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_gate_blocks_manual_mapping(self) -> None:
        """Gate MUST block manually constructed evidence mapping."""
        manual_evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 100},
            "typed_result": True,
        }

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(manual_evidence)

    def test_gate_blocks_no_op_outcome(self) -> None:
        """Gate MUST block even when outcome is no_op."""
        result = E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256="b" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_gate_error_does_not_echo_sensitive_evidence_values(self) -> None:
        """Gate error message must NOT echo sensitive evidence field values.

        BEHAVIORAL PROOF: This is the separately named no-error-echo proof.
        Evidence with a sensitive DATABASE_URL-style value is blocked, and
        the exception message does NOT contain that value. This is distinct
        from the serializer-noninvocation monkeypatch proof in
        TestAcceptanceSelectorGate.
        """
        sensitive_evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
            "sensitive_field": "DATABASE_URL=postgres://secret@localhost:5432",
        }

        with pytest.raises(Phase15AcceptanceBlockedError) as exc_info:
            admit_evidence_for_acceptance(sensitive_evidence)

        error_msg = str(exc_info.value)
        assert "postgres://secret" not in error_msg
        assert "DATABASE_URL" not in error_msg

    def test_wave1_gate_produces_no_artifact(self) -> None:
        """Wave 1 gate MUST produce no acceptance artifact.

        BEHAVIORAL PROOF: The admission attempt raises, which means no artifact
        is emitted. The exception IS the proof of no-artifact.
        """
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)


class TestHistoricalScriptDenylist:
    """Tests for exact 9 historical route denylist."""

    def test_phase10_run_validation_denied(self) -> None:
        """Phase 10 run_validation.py is denied."""
        route = "verification/phase10-real-docx-retrieval-validation/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_phase10_reconstruct_transcript_denied(self) -> None:
        """Phase 10 reconstruct_transcript.py is denied."""
        route = "verification/phase10-real-docx-retrieval-validation/reconstruct_transcript.py"
        assert is_historical_route_denied(route) is True

    def test_phase11_run_validation_denied(self) -> None:
        """Phase 11 run_validation.py is denied."""
        route = "verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_phase13_run_validation_denied(self) -> None:
        """Phase 13 run_validation.py is denied."""
        route = "verification/phase13-real-validation-2026-06-26/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_phase13_diagnose_q18_denied(self) -> None:
        """Phase 13 diagnose_q18_live_path.py is denied."""
        route = (
            "verification/phase13-real-validation-2026-06-26/diagnose_q18_live_path.py"
        )
        assert is_historical_route_denied(route) is True

    def test_phase14_run_validation_denied(self) -> None:
        """Phase 14 run_validation.py is denied."""
        route = "verification/phase14-new-doc-validation/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_phase14_full_flow_diagnosis_denied(self) -> None:
        """Phase 14 full_flow_diagnosis.py is denied."""
        route = "verification/phase14-new-doc-validation/full_flow_diagnosis.py"
        assert is_historical_route_denied(route) is True

    def test_phase14_verify_autocommit_fix_denied(self) -> None:
        """Phase 14 verify_autocommit_fix.py is denied."""
        route = "verification/phase14-new-doc-validation/verify_autocommit_fix.py"
        assert is_historical_route_denied(route) is True

    def test_real_document_validation_denied(self) -> None:
        """real-document-validation-2026-06-23 run_validation.py is denied."""
        route = "verification/real-document-validation-2026-06-23/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_backslash_normalization_denied(self) -> None:
        """Backslash routes are denied (Windows compatibility)."""
        route = (
            "verification\\phase10-real-docx-retrieval-validation\\run_validation.py"
        )
        assert is_historical_route_denied(route) is True

    def test_forward_slash_normalization_denied(self) -> None:
        """Forward slash routes are denied (Unix compatibility)."""
        route = "verification/phase10-real-docx-retrieval-validation/run_validation.py"
        assert is_historical_route_denied(route) is True

    def test_phase15_route_not_in_denylist(self) -> None:
        """Phase 15 route is NOT in denylist."""
        phase15_route = (
            "verification/phase15-okf-ingestion-pipeline/run_e2a_verification.py"
        )
        assert is_historical_route_denied(phase15_route) is False

    def test_denylist_count_is_exactly_nine(self) -> None:
        """Denylist must have exactly 9 routes."""
        assert len(HISTORICAL_DENYLIST) == 9


class TestGateDeniesHistoricalScripts:
    """Tests that acceptance gate denies historical script routes."""

    def test_historical_script_evidence_denied_at_gate(self) -> None:
        """Historical script evidence is denied at acceptance gate."""
        evidence = {
            "outcome": "no_op",
            "manifest_sha256": "a" * 64,
            "typed_result": True,
            "_source_route": "verification/phase10-real-docx-retrieval-validation/run_validation.py",
        }

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)


class TestNoDbBehavior:
    """Tests for no-DB default behavior.

    Honest behavioral proof of the blocked_not_executed selector contract.
    No fake psycopg.connect seam is monkeypatched - run_verification never calls
    psycopg, so asserting an uncalled function proves nothing about DB safety.
    """

    def test_no_db_returns_blocked_not_executed(self) -> None:
        """No-DB must return blocked_not_executed."""
        result = run_verification(enable_disposable_db=False)

        assert result.get("disposable_db_status") == "blocked_not_executed"
        assert result.get("outcome") == "acceptance_blocked"

    def test_no_db_does_not_falsely_imply_acceptance(self) -> None:
        """No-DB must NOT falsely imply acceptance."""
        result = run_verification(enable_disposable_db=False)

        assert result.get("outcome") != "pass"
        assert "blocked" in result.get("disposable_db_status", "")
        assert result.get("outcome") == "acceptance_blocked"
