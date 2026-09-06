"""Tests for E2A verification result consumer and evidence emission.

Phase 15-04: Measured-result evidence and no-fabrication contract tests.

These tests verify behavior through public APIs and module-level aliases loaded
from the hyphenated verification directory. No source inspection, no placeholders.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult

_RUN_E2A_MODULE_NAME = "_track_c_e2a_verification_result_module"


def _load_run_e2a_verification():
    """Load run_e2a_verification module from hyphenated verification directory.

    Hyphenated directory names are not valid Python identifiers, so importlib
    loads the module directly from its file path under a UNIQUE sys.modules key
    to avoid cross-test collision with the isolation test file.
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


# Load module once at import time; alias all needed symbols directly.
_run_e2a_verification = _load_run_e2a_verification()
serialize_evidence = _run_e2a_verification.serialize_evidence
run_verification = _run_e2a_verification.run_verification
validate_quality_claim = _run_e2a_verification.validate_quality_claim
validate_evidence_authenticity = _run_e2a_verification.validate_evidence_authenticity
Phase15AcceptanceBlockedError = _run_e2a_verification.Phase15AcceptanceBlockedError
admit_evidence_for_acceptance = _run_e2a_verification.admit_evidence_for_acceptance
_redact_value = _run_e2a_verification._redact_value


class TestEvidenceSerialization:
    """Tests for evidence serialization of E2aReconciliationResult."""

    def test_accepts_typed_reconciliation_result_and_serializes_canonically(
        self,
    ) -> None:
        """Evidence emission accepts typed E2aReconciliationResult and serializes it."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 10, "tree_nodes": 5},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
            reconciliation_required=True,
        )

        evidence = serialize_evidence(result)

        assert isinstance(evidence, dict)
        assert evidence.get("manifest_sha256") == "a" * 64
        assert evidence.get("outcome") == "changed"
        assert "primary_dml_by_table" in evidence
        assert evidence["primary_dml_by_table"]["canonical_spans"] == 10

    def test_serialized_output_excludes_connection_strings(self) -> None:
        """Serialized output EXCLUDES connection strings."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "postgres://" not in evidence_str
        assert "postgresql://" not in evidence_str
        assert "@localhost:" not in evidence_str
        assert "DATABASE_URL" not in evidence_str

    def test_serialized_output_excludes_environment_values(self) -> None:
        """Serialized output EXCLUDES environment values."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "OPENAI_API_KEY" not in evidence_str
        assert "ANTHROPIC_API_KEY" not in evidence_str

    def test_serialized_output_excludes_invented_authorization_receipts(self) -> None:
        """Serialized output EXCLUDES invented authorization receipt metadata."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "authorization_receipt" not in evidence_str.lower()
        assert "authorized_by" not in evidence_str.lower()


class TestDatabaseSelectorGate:
    """Tests for database selector gate and blocked_not_executed status.

    Honest behavioral proof: the default selector returns blocked_not_executed.
    No fake psycopg.connect seam is monkeypatched, because run_verification never
    calls psycopg - asserting an uncalled function proves nothing about DB safety.
    """

    def test_unavailable_disposable_selector_blocked_not_executed(self) -> None:
        """Unavailable disposable DB selector emits exactly blocked_not_executed."""
        result = run_verification(enable_disposable_db=False)

        assert result.get("disposable_db_status") == "blocked_not_executed"
        assert result.get("outcome") != "pass"
        assert result.get("outcome") == "acceptance_blocked"


class TestSmokeComparatorQualityLabel:
    """Tests for smoke/comparator record quality labeling."""

    def test_comparator_record_has_no_quality_label(self) -> None:
        """Smoke/comparator record carries explicit no-quality label."""
        result = E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert "quality_level" in evidence or "quality" not in str(evidence).lower()
        if "quality_level" in evidence:
            assert evidence["quality_level"] in (
                None,
                "not_measured",
                "no_quality",
                "smoke",
            )

    def test_smoke_record_overclaim_rejection(self) -> None:
        """Asserting a Level/quality claim on a smoke record must fail."""
        smoke_with_level_claim = {
            "record_type": "smoke",
            "claimed_level": "L1",
        }

        with pytest.raises(ValueError, match="(?i)(smoke|quality|level)"):
            validate_quality_claim(smoke_with_level_claim)

    def test_claimed_level_value_not_interpolated_into_error(self) -> None:
        """Caller-supplied claimed_level must NEVER appear in exception text.

        BEHAVIORAL PROOF: A sensitive value in claimed_level is rejected, but
        the exception message does NOT echo that value back. This prevents
        information leakage through error messages.
        """
        sensitive_claim = "postgres://secret:password@localhost:5432/db"
        smoke_record = {
            "record_type": "smoke",
            "claimed_level": sensitive_claim,
        }

        with pytest.raises(ValueError) as exc_info:
            validate_quality_claim(smoke_record)

        error_msg = str(exc_info.value)
        assert sensitive_claim not in error_msg
        assert "postgres://" not in error_msg
        assert "secret" not in error_msg
        assert "password" not in error_msg


class TestNoFabricatedEvidence:
    """Tests for prohibiting standalone fabricated JSON as PASS proof."""

    def test_rejects_standalone_fabricated_json_as_pass_proof(self) -> None:
        """Standalone fabricated JSON must NOT be acceptable as PASS proof."""
        fabricated = {
            "status": "pass",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 100},
        }

        with pytest.raises(ValueError, match="fabricated|typed.*result|measured"):
            validate_evidence_authenticity(fabricated)

    def test_accepts_only_typed_measured_results(self) -> None:
        """Evidence must derive from typed E2aReconciliationResult."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={"canonical_spans": 5},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert "typed_result" in evidence or "outcome" in evidence
        assert evidence.get("outcome") in (
            "changed",
            "no_op",
            "rolled_back_failure",
            "acceptance_blocked",
            "outcome_unknown",
        )

    def test_json_without_typed_result_rejected(self) -> None:
        """JSON without typed result provenance must be rejected."""
        arbitrary_json = {
            "tables": {"canonical_spans": 10},
            "status": "pass",
        }

        with pytest.raises(ValueError, match="typed.*result|provenance|measured"):
            validate_evidence_authenticity(arbitrary_json)


class TestDmlAndOutcomeTracking:
    """Tests for DML and outcome tracking in evidence."""

    def test_primary_dml_serialized_correctly(self) -> None:
        """Primary DML counts must be serialized from typed result."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={
                "canonical_spans": 100,
                "tree_nodes": 50,
                "entities": 25,
            },
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence["primary_dml_by_table"]["canonical_spans"] == 100
        assert evidence["primary_dml_by_table"]["tree_nodes"] == 50
        assert evidence["primary_dml_by_table"]["entities"] == 25

    def test_denylist_dml_counts_serialized(self) -> None:
        """Denylist DML counts must be serialized from typed result."""
        result = E2aReconciliationResult(
            outcome="rolled_back_failure",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={"chunk_entity_links": 5},
            comparator_parity=False,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome="denylist_violation",
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence["denylist_dml_counts"]["chunk_entity_links"] == 5
        assert evidence["outcome"] == "rolled_back_failure"

    def test_stale_and_cache_effects_serialized(self) -> None:
        """Stale deletion and cache invalidation counts must be serialized."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={"vector_chunks": 10},
            cache_invalidation_counts={"summaries": 5},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

        evidence = serialize_evidence(result)

        assert evidence["stale_deletion_counts"]["vector_chunks"] == 10
        assert evidence["cache_invalidation_counts"]["summaries"] == 5

    def test_failure_audit_outcomes_serialized(self) -> None:
        """Failure audit outcomes must be serialized from typed result."""
        result = E2aReconciliationResult(
            outcome="rolled_back_failure",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=False,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome="integrity_violation",
            post_rollback_failure_audit_outcome="clean",
        )

        evidence = serialize_evidence(result)

        assert evidence["failure_audit_outcome"] == "integrity_violation"
        assert evidence["post_rollback_failure_audit_outcome"] == "clean"


class TestReconciliationRequired:
    """Tests for reconciliation_required flag."""

    def test_reconciliation_required_serialized(self) -> None:
        """reconciliation_required flag must be serialized."""
        result = E2aReconciliationResult(
            outcome="changed",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=True,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
            reconciliation_required=True,
        )

        evidence = serialize_evidence(result)

        assert evidence["reconciliation_required"] is True


class TestFormatVsAcceptance:
    """Tests distinguishing format validation from acceptance emission."""

    def test_format_validation_may_accept_shape(self) -> None:
        """Format validation may accept a shape, but cannot yield acceptance."""
        evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
        }

        validate_evidence_authenticity(evidence)

    def test_format_validation_rejects_invalid_outcome(self) -> None:
        """Format validation rejects invalid outcomes."""
        invalid_evidence = {
            "outcome": "invalid_outcome",
            "typed_result": True,
        }

        with pytest.raises(ValueError, match="invalid outcome"):
            validate_evidence_authenticity(invalid_evidence)

    def test_format_validation_rejects_missing_typed_result(self) -> None:
        """Format validation rejects missing typed_result."""
        missing_typed = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
        }

        with pytest.raises(ValueError, match="typed.*result"):
            validate_evidence_authenticity(missing_typed)

    def test_dedicated_pass_outcome_reaches_pass_rejection_message(self) -> None:
        """outcome='pass' hits the DEDICATED pass-rejection check, not generic.

        BEHAVIORAL PROOF: The dedicated outcome=='pass' check must be reachable
        BEFORE the generic allowed-outcome validation. The error message must
        contain the dedicated pass-rejection wording about PASS acceptance
        requiring actual E2aReconciler provenance.
        """
        fabricated = {
            "outcome": "pass",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 100},
            "typed_result": True,
        }

        with pytest.raises(ValueError) as exc_info:
            validate_evidence_authenticity(fabricated)

        error_msg = str(exc_info.value)
        # The dedicated pass-rejection message mentions provenance requirement
        assert "PASS acceptance requires actual E2aReconciler provenance" in error_msg

    def test_invalid_outcome_value_not_interpolated_into_error(self) -> None:
        """Arbitrary sensitive outcome value must NEVER appear in exception text.

        BEHAVIORAL PROOF: An attacker-supplied outcome containing a connection
        string is rejected, but the exception message does NOT echo that value.
        All validation error messages are static - no evidence-value interpolation.
        """
        sensitive_outcome = "postgres://secret:password@localhost:5432/db"
        evidence = {
            "outcome": sensitive_outcome,
            "typed_result": True,
        }

        with pytest.raises(ValueError) as exc_info:
            validate_evidence_authenticity(evidence)

        error_msg = str(exc_info.value)
        assert sensitive_outcome not in error_msg
        assert "postgres://" not in error_msg
        assert "secret" not in error_msg
        assert "password" not in error_msg

    def test_non_string_outcome_rejected_with_safe_wording(self) -> None:
        """Non-string outcomes are rejected with static generic wording.

        BEHAVIORAL PROOF: Non-string outcomes (int, list) must raise ValueError
        with a safe static message - NOT TypeError, and NOT interpolating the
        value into the message.
        """
        # Integer outcome (hashable but non-string)
        evidence_int = {
            "outcome": 12345,
            "typed_result": True,
        }
        with pytest.raises(ValueError) as exc_info:
            validate_evidence_authenticity(evidence_int)
        assert "12345" not in str(exc_info.value)

        # List outcome (unhashable - must not raise TypeError)
        evidence_list = {
            "outcome": ["sensitive", "values"],
            "typed_result": True,
        }
        with pytest.raises(ValueError) as exc_info:
            validate_evidence_authenticity(evidence_list)
        assert "sensitive" not in str(exc_info.value)

    def test_format_metadata_does_not_grant_acceptance(self) -> None:
        """typed_result=True is format metadata, NOT acceptance authorization.

        BEHAVIORAL PROOF: Evidence with typed_result=True and valid outcome
        is still blocked by the acceptance gate. Format validation passes,
        but this does NOT grant Phase 15 PASS artifacts.
        """
        evidence_with_format_metadata = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "primary_dml_by_table": {"canonical_spans": 10},
            "typed_result": True,
        }

        validate_evidence_authenticity(evidence_with_format_metadata)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence_with_format_metadata)

    def test_no_op_outcome_with_format_metadata_still_blocked(self) -> None:
        """Even no_op outcome with format metadata is blocked by acceptance gate."""
        evidence_with_no_op = {
            "outcome": "no_op",
            "manifest_sha256": "b" * 64,
            "primary_dml_by_table": {},
            "typed_result": True,
        }

        validate_evidence_authenticity(evidence_with_no_op)

        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence_with_no_op)


class TestSerializeEvidenceIsDiagnosticOnly:
    """Tests that serialize_evidence remains a diagnostic redactor, NOT acceptance."""

    def test_serialize_evidence_never_claims_acceptance(self) -> None:
        """serialize_evidence must never claim or emit acceptance."""
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

        assert "acceptance_authorized" not in evidence
        assert (
            "acceptance_provenance" not in evidence
            or evidence.get("acceptance_provenance") is None
        )

    def test_typed_result_is_format_metadata_not_provenance(self) -> None:
        """typed_result=True indicates format, NOT producer authenticity."""
        result = E2aReconciliationResult(
            outcome="no_op",
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


class TestRedactionDefensiveCoverage:
    """Tests that redaction defensively covers all container types."""

    def test_set_members_are_redacted(self) -> None:
        """Sensitive values inside sets are redacted.

        BEHAVIORAL PROOF: _redact_value must recurse into set members so
        that sensitive connection strings are replaced with [REDACTED].
        Output is a list (JSON-safe) instead of set (not JSON-serializable).
        """
        sensitive = "postgres://secret:password@localhost:5432"
        safe = "benign_value"
        redacted = _redact_value({sensitive, safe})

        # Set output is converted to list for JSON-safety and
        # cardinality preservation (distinct [REDACTED] entries)
        assert isinstance(redacted, list)
        redacted_str = str(redacted)
        assert sensitive not in redacted_str
        assert "[REDACTED]" in redacted_str
        assert safe in redacted

    def test_frozenset_members_are_redacted(self) -> None:
        """Sensitive values inside frozensets are redacted.

        BEHAVIORAL PROOF: _redact_value must recurse into frozenset members.
        Output is a list (JSON-safe) instead of frozenset (not JSON-serializable).
        """
        sensitive = "postgres://secret:password@localhost:5432"
        safe = "benign_value"
        redacted = _redact_value(frozenset({sensitive, safe}))

        # Frozenset output is converted to list for JSON-safety and
        # cardinality preservation (distinct [REDACTED] entries)
        assert isinstance(redacted, list)
        redacted_str = str(redacted)
        assert sensitive not in redacted_str
        assert "[REDACTED]" in redacted_str
        assert safe in redacted

    def test_dict_keys_are_redacted(self) -> None:
        """Sensitive connection-string keys in dicts are redacted.

        BEHAVIORAL PROOF: _redact_value must redact dict KEYS, not just
        values. A sensitive key like 'postgres://secret@localhost' in
        primary_dml_by_table would otherwise survive serialization.
        Uses unique placeholder to prevent collision.
        """
        sensitive_key = "postgres://secret:password@localhost:5432"
        safe_key = "benign_table"
        input_dict = {sensitive_key: 10, safe_key: 20}
        redacted = _redact_value(input_dict)

        assert isinstance(redacted, dict)
        redacted_str = str(redacted)
        assert sensitive_key not in redacted_str
        assert "[REDACTED_KEY_" in redacted_str
        assert safe_key in redacted
        assert redacted[safe_key] == 20

    def test_nested_dict_keys_are_redacted(self) -> None:
        """Sensitive keys in nested dicts are recursively redacted."""
        sensitive_key = "mysql://root:password@localhost:3306"
        input_dict = {"outer": {sensitive_key: "inner_value"}}
        redacted = _redact_value(input_dict)

        redacted_str = str(redacted)
        assert sensitive_key not in redacted_str
        assert "[REDACTED_KEY_" in redacted_str

    def test_generic_uri_schemes_are_redacted(self) -> None:
        """Generic URI connection schemes (mysql, redis, amqp) are redacted.

        BEHAVIORAL PROOF: _redact_sensitive must catch connection URIs
        beyond just PostgreSQL. MySQL, Redis, AMQP and other schemes
        containing credentials must not survive diagnostic serialization.
        """
        # MySQL connection string
        mysql_uri = "mysql://root:password@localhost:3306/database"
        redacted_mysql = _redact_value(mysql_uri)
        assert mysql_uri not in str(redacted_mysql)
        assert "[REDACTED]" in str(redacted_mysql)

        # Redis connection string
        redis_uri = "redis://:password@localhost:6379/0"
        redacted_redis = _redact_value(redis_uri)
        assert redis_uri not in str(redacted_redis)
        assert "[REDACTED]" in str(redacted_redis)

        # AMQP connection string
        amqp_uri = "amqp://user:password@localhost:5672/vhost"
        redacted_amqp = _redact_value(amqp_uri)
        assert amqp_uri not in str(redacted_amqp)
        assert "[REDACTED]" in str(redacted_amqp)

    def test_url_with_credentials_redacted(self) -> None:
        """URLs with obvious credential patterns are redacted.

        BEHAVIORAL PROOF: URLs containing user:password@host patterns
        are redacted regardless of scheme, preventing credential leaks
        in failure_audit_outcome and other string fields.
        """
        credential_url = "https://user:secret@example.com/path"
        redacted = _redact_value(credential_url)
        assert "user:secret" not in str(redacted)
        assert "[REDACTED]" in str(redacted)

    def test_existing_type_redaction_semantics_unchanged(self) -> None:
        """Redaction semantics for str, dict, list, tuple, primitives unchanged."""
        # String redaction
        assert "[REDACTED]" in _redact_value("postgres://user@localhost:5432")
        # Dict recursion
        redacted_dict = _redact_value({"key": "postgres://secret@localhost"})
        assert "postgres://secret@localhost" not in str(redacted_dict)
        # List recursion
        redacted_list = _redact_value(["postgres://secret@localhost", "safe"])
        assert "postgres://secret@localhost" not in str(redacted_list)
        # Tuple recursion
        redacted_tuple = _redact_value(("postgres://secret@localhost", "safe"))
        assert isinstance(redacted_tuple, tuple)
        assert "postgres://secret@localhost" not in str(redacted_tuple)
        # Primitives pass through
        assert _redact_value(42) == 42
        assert _redact_value(True) is True
        assert _redact_value(None) is None


class TestAcceptanceGateInputSafety:
    """Tests that admit_evidence_for_acceptance handles all input types safely."""

    def test_none_input_raises_blocked_not_attribute_error(self) -> None:
        """None input to admit_evidence_for_acceptance raises blocked error.

        BEHAVIORAL PROOF: Non-dict input must universally fail with the
        static Phase15AcceptanceBlockedError, never AttributeError. The
        gate must not leak implementation details through exception types.
        """
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(None)  # type: ignore[arg-type]

    def test_list_input_raises_blocked_not_attribute_error(self) -> None:
        """List input to admit_evidence_for_acceptance raises blocked error.

        BEHAVIORAL PROOF: A list does not have .get(), but the gate must
        still raise Phase15AcceptanceBlockedError, not AttributeError.
        """
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance([1, 2, 3])  # type: ignore[arg-type]

    def test_int_input_raises_blocked_not_attribute_error(self) -> None:
        """Integer input to admit_evidence_for_acceptance raises blocked error."""
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(42)  # type: ignore[arg-type]

    def test_dict_input_still_blocked(self) -> None:
        """Dict input still produces the standard blocked error (baseline)."""
        evidence = {
            "outcome": "changed",
            "typed_result": True,
            "_source_route": "some/path",
        }
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)


class TestAcceptanceGateHostileSourceRoute:
    """Tests that hostile _source_route values never escape as another exception.

    Wave 1 admission must consistently raise Phase15AcceptanceBlockedError
    without calling attacker-controlled bool/str conversions unnecessarily.
    """

    def test_hostile_bool_source_route_raises_blocked(self) -> None:
        """A _source_route with hostile __bool__ must not escape as another exception.

        BEHAVIORAL PROOF: An object whose __bool__ raises must yield
        Phase15AcceptanceBlockedError, not the hostile exception. The gate
        must not invoke attacker-controlled bool conversions.
        """

        class _HostileBool:
            def __bool__(self) -> bool:
                raise RuntimeError("hostile bool")

        evidence = {
            "outcome": "changed",
            "typed_result": True,
            "_source_route": _HostileBool(),
        }
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_hostile_str_source_route_raises_blocked(self) -> None:
        """A _source_route with hostile __str__ must not escape as another exception.

        BEHAVIORAL PROOF: str() must not be called on attacker-controlled
        _source_route values. An object whose __str__ raises must yield
        Phase15AcceptanceBlockedError, not the hostile exception.
        """

        class _HostileStr:
            def __str__(self) -> str:
                raise RuntimeError("hostile str")

        evidence = {
            "outcome": "changed",
            "typed_result": True,
            "_source_route": _HostileStr(),
        }
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_non_string_source_route_int_still_blocked(self) -> None:
        """A non-string (int) _source_route is blocked normally.

        BEHAVIORAL PROOF: Non-string _source_route values are blocked by the
        fail-closed gate without invoking attacker-controlled conversions.
        """
        evidence = {
            "outcome": "changed",
            "typed_result": True,
            "_source_route": 12345,
        }
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)

    def test_non_denylisted_normalized_route_still_blocked(self) -> None:
        """A non-denylisted route (even normalized) is still blocked by the gate.

        BEHAVIORAL PROOF: Path normalization only affects the denylist
        diagnostic message. The Wave 1 fail-closed gate blocks ALL routes,
        denylisted or not.
        """
        evidence = {
            "outcome": "changed",
            "typed_result": True,
            "_source_route": "some/./normalized/./path.py",
        }
        with pytest.raises(Phase15AcceptanceBlockedError):
            admit_evidence_for_acceptance(evidence)


class TestValidatorInputSafety:
    """Tests that non-dict validator inputs raise the documented fail-closed type.

    validate_evidence_authenticity documents ValueError. Non-dict inputs must
    raise ValueError, not incidental AttributeError/TypeError from .get calls.
    """

    def test_validate_none_raises_value_error_not_attribute_error(self) -> None:
        """None input raises ValueError, not AttributeError."""
        with pytest.raises(ValueError):
            validate_evidence_authenticity(None)  # type: ignore[arg-type]

    def test_validate_list_raises_value_error_not_attribute_error(self) -> None:
        """List input raises ValueError, not AttributeError."""
        with pytest.raises(ValueError):
            validate_evidence_authenticity([1, 2, 3])  # type: ignore[arg-type]

    def test_validate_int_raises_value_error_not_attribute_error(self) -> None:
        """Int input raises ValueError, not AttributeError."""
        with pytest.raises(ValueError):
            validate_evidence_authenticity(42)  # type: ignore[arg-type]

    def test_validate_tuple_raises_value_error_not_attribute_error(self) -> None:
        """Tuple input raises ValueError, not AttributeError."""
        with pytest.raises(ValueError):
            validate_evidence_authenticity((1, 2))  # type: ignore[arg-type]


class TestTypedResultStrictIdentity:
    """Tests that typed_result is valid only when it is True (not merely truthy)."""

    def test_typed_result_integer_one_rejected(self) -> None:
        """typed_result=1 (truthy but not True) is rejected.

        BEHAVIORAL PROOF: Only the boolean True is valid format metadata.
        Integer 1 is truthy but must be rejected to prevent forgery via
        truthy non-boolean values.
        """
        evidence = {"outcome": "changed", "typed_result": 1}
        with pytest.raises(ValueError, match="typed.*result"):
            validate_evidence_authenticity(evidence)

    def test_typed_result_string_rejected(self) -> None:
        """typed_result='yes' (truthy non-boolean) is rejected."""
        evidence = {"outcome": "changed", "typed_result": "yes"}
        with pytest.raises(ValueError, match="typed.*result"):
            validate_evidence_authenticity(evidence)

    def test_typed_result_list_rejected(self) -> None:
        """typed_result=[True] (truthy non-boolean) is rejected."""
        evidence = {"outcome": "changed", "typed_result": [True]}
        with pytest.raises(ValueError, match="typed.*result"):
            validate_evidence_authenticity(evidence)

    def test_typed_result_exact_true_accepted(self) -> None:
        """Only the exact boolean True is accepted as format metadata."""
        evidence = {
            "outcome": "changed",
            "manifest_sha256": "a" * 64,
            "typed_result": True,
        }
        validate_evidence_authenticity(evidence)  # should not raise
