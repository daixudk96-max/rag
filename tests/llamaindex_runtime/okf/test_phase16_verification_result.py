"""Tests for Phase 16 verification result consumer and evidence emission.

Plan 16-18: Measured typed-result evidence, no-fabrication, zero-generative-LLM
proof, and C1/C2 aggregate attribution contract tests.

These tests verify behavior through public APIs and module-level aliases loaded
from the hyphenated verification directory. No source inspection, no
placeholders, no DB/model/network access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from typing import Any

from llamaindex_runtime.entity.materialization_repository import (
    E2bReconciliationResult,
)

_RUN_PHASE16_MODULE_NAME = "_track_c_phase16_verification_result_module"


def _load_run_phase16_verification():
    """Load run_phase16_verification module from hyphenated verification directory.

    Hyphenated directory names are not valid Python identifiers, so importlib
    loads the module directly from its file path under a UNIQUE sys.modules key
    to avoid cross-test collision. A missing module raises ImportError (RED).
    """
    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "verification"
        / "phase16-raw-corpus-entity-layer"
        / "run_phase16_verification.py"
    )
    if not module_path.is_file():
        raise ImportError(f"Cannot load module from {module_path}")
    spec = importlib.util.spec_from_file_location(_RUN_PHASE16_MODULE_NAME, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RUN_PHASE16_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# Load module once at import time; alias all needed symbols directly.
_run_phase16_verification = _load_run_phase16_verification()
serialize_evidence = _run_phase16_verification.serialize_evidence
run_verification = _run_phase16_verification.run_verification
validate_evidence_authenticity = (
    _run_phase16_verification.validate_evidence_authenticity
)
consume_typed_result = _run_phase16_verification.consume_typed_result
build_aggregate_record = _run_phase16_verification.build_aggregate_record
prove_zero_generative_llm = _run_phase16_verification.prove_zero_generative_llm
_redact_value = _run_phase16_verification._redact_value
BLOCKED_STATUS = _run_phase16_verification.BLOCKED_STATUS
SKIPPED_STATUS = _run_phase16_verification.SKIPPED_STATUS
LIVE_SELECTORS = _run_phase16_verification.LIVE_SELECTORS

# ---------------------------------------------------------------------------
# Measured typed fixtures: the REAL archived evidence values (16-15 C1 full
# corpus acceptance, 16-14 migration gate, Gate 5 C2 entry). These are typed
# measured results consumed read-only; they are never rewritten or forged.
# ---------------------------------------------------------------------------

C1_EVIDENCE: dict[str, Any] = {
    "candidate_path": "fixture_candidates",
    "matrix": {
        "first_materialization": {
            "bridge_count": 2,
            "chunk_entity_links_count": 0,
            "chunk_entity_links_dml": 0,
            "entity_mentions_dml": 2,
            "ledger_count": 2,
            "mention_count": 2,
            "node_entity_links_dml": 2,
            "okf_e2b_node_link_ownership_dml": 2,
            "outcome": "changed",
        },
        "equivalent_rerun": {
            "dml_total": 0,
            "outcome": "no_op",
            "timestamp_churn": False,
        },
        "changed_set_convergence": {
            "bridge_count": 1,
            "bridge_deletion_dml": 1,
            "fail_closed_preserved_bridges": 0,
            "mention_count": 1,
            "outcome": "changed",
            "stale_link_ownership_deletions": 1,
            "stale_mention_deletions": 1,
        },
        "changed_set_failure_rollback": {
            "failure_audit_outcome": "written",
            "old_state_restored": True,
            "outcome": "rolled_back_failure",
            "rollback_confirmed": True,
        },
        "invalid_document_isolation": {
            "continued_to_next": True,
            "failure_audit_outcome": "written",
            "outcome": "rolled_back_failure",
            "scope_writes": 0,
        },
        "manual_legacy_preservation": {
            "claimed": 0,
            "deleted": 0,
            "manual_bridges_preserved": 1,
            "manual_mentions_preserved": 1,
            "new_bridge_count": 1,
            "new_mention_count": 0,
            "outcome": "changed",
        },
        "e2b_vs_e2b_serialization": {
            "duplicate_rows": 0,
            "lock_key_is_e2a": True,
            "lock_key_is_e2b": False,
            "overlap_blocked_on_lock": True,
            "pre_converge_outcome": "changed",
            "second_outcome": "no_op",
            "serialized": True,
        },
        "e2a_vs_e2b_serialization": {
            "duplicate_rows": 0,
            "lock_key_is_e2a": True,
            "lock_key_is_e2b": False,
            "overlap_blocked_on_lock": True,
            "pre_converge_outcome": "no_op",
            "second_outcome": "no_op",
            "serialized": True,
        },
    },
    "schema_version": 1,
    "status": "executed",
}

C2_ENTERED: dict[str, Any] = {
    "c1_closure": {
        "evidence_name": "e2b_full_corpus_acceptance_evidence_executed_SUCCESS_2026-08-31.md",
        "hash_matched": True,
        "matrix_keys": 8,
        "status": "executed",
    },
    "candidate_path": "fixture_candidates",
    "proof": {
        "catalog_applied": {
            "migrations": 21,
            "outcome": "applied",
            "tail_includes_021": True,
        },
        "default_off_parity": {
            "c2_dml_total": 0,
            "cluster_count": 0,
            "membership_count": 0,
            "outcome": "no_op",
        },
        "rules_materialization": {
            "cluster_count": 1,
            "deterministic_ids_verified": True,
            "membership_count": 2,
            "outcome": "materialized",
        },
        "tombstone": {
            "cluster_count_tombstoned": 1,
            "membership_preserved": 2,
            "outcome": "tombstoned",
        },
    },
    "schema_version": 1,
    "status": "executed",
}

C2_SKIPPED: dict[str, Any] = {
    "schema_version": 1,
    "status": "skipped_not_entered",
    "reason": "default-off; C2 not entered without OKF_E2B_C2_ENTRY_AUTHORIZED",
}

MIGRATION_GATE_EVIDENCE: dict[str, Any] = {
    "catalog_apply_count": 1,
    "catalog_tail": [
        "019_e2a_materialization_contract.sql",
        "020_ner_entity_mentions.sql",
    ],
    "constraint_inventory": [
        "chk_okf_e2b_mentions_input_kind",
        "chk_okf_e2b_mentions_confidence_kind",
        "chk_okf_e2b_mentions_artifact_digest",
        "chk_okf_e2b_mentions_label_map_digest",
        "chk_okf_e2b_mentions_document_coordinates",
        "chk_okf_e2b_mentions_owner_scope",
    ],
    "idempotence_ddl_count": 0,
    "idempotence_reapply_count": 1,
    "index_inventory": [
        "idx_okf_e2b_failure_audit_occurred_at",
        "idx_okf_e2b_failure_audit_scope",
        "idx_okf_e2b_node_link_ownership_node",
        "idx_okf_e2b_node_link_ownership_version",
    ],
    "ownership_ledger_unique": "uq_okf_e2b_node_link_ownership",
    "ownership_ledger_unique_columns": ["node_id", "entity_id", "version_id"],
    "provenance_column_count": 20,
    "schema_version": 1,
    "status": "executed",
    "tables": ["okf_e2b_failure_audit", "okf_e2b_node_link_ownership"],
}

_EXTRACTOR_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "llamaindex_runtime"
    / "entity"
    / "extractor.py"
)


class TestEvidenceSerialization:
    """Tests for evidence serialization of typed E2bReconciliationResult."""

    def test_accepts_typed_reconciliation_result_and_serializes_canonically(
        self,
    ) -> None:
        """Evidence emission accepts typed E2bReconciliationResult and serializes it."""
        result = E2bReconciliationResult(
            outcome="changed",
            primary_dml_by_table={
                "entity_mentions": 2,
                "okf_e2b_node_link_ownership": 2,
                "node_entity_links": 2,
            },
            stale_deletion_counts={
                "entity_mentions": 1,
                "okf_e2b_node_link_ownership": 1,
                "node_entity_links": 1,
            },
            failure_audit_outcome=None,
            reconciliation_required=False,
        )

        evidence = serialize_evidence(result)

        assert isinstance(evidence, dict)
        assert evidence.get("outcome") == "changed"
        assert evidence["primary_dml_by_table"]["entity_mentions"] == 2
        assert evidence["stale_deletion_counts"]["node_entity_links"] == 1
        assert evidence.get("typed_result") is True

    def test_serialized_output_is_whitelisted_fields_only(self) -> None:
        """Serialized output contains ONLY whitelisted typed fields (T-16-65)."""
        result = E2bReconciliationResult(
            outcome="no_op",
            primary_dml_by_table={},
            stale_deletion_counts={},
            failure_audit_outcome=None,
            reconciliation_required=False,
        )

        evidence = serialize_evidence(result)

        assert set(evidence) == {
            "outcome",
            "primary_dml_by_table",
            "stale_deletion_counts",
            "failure_audit_outcome",
            "reconciliation_required",
            "typed_result",
        }

    def test_serialized_output_excludes_connection_strings(self) -> None:
        """Serialized output EXCLUDES connection strings."""
        result = E2bReconciliationResult(
            outcome="changed",
            primary_dml_by_table={},
            stale_deletion_counts={},
            failure_audit_outcome=None,
            reconciliation_required=False,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "postgres://" not in evidence_str
        assert "postgresql://" not in evidence_str
        assert "@localhost:" not in evidence_str
        assert "DATABASE_URL" not in evidence_str

    def test_serialized_output_excludes_environment_values(self) -> None:
        """Serialized output EXCLUDES environment values."""
        result = E2bReconciliationResult(
            outcome="changed",
            primary_dml_by_table={},
            stale_deletion_counts={},
            failure_audit_outcome=None,
            reconciliation_required=False,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "OPENAI_API_KEY" not in evidence_str
        assert "ANTHROPIC_API_KEY" not in evidence_str

    def test_serialized_output_excludes_invented_authorization_receipts(self) -> None:
        """Serialized output EXCLUDES invented authorization receipt metadata."""
        result = E2bReconciliationResult(
            outcome="changed",
            primary_dml_by_table={},
            stale_deletion_counts={},
            failure_audit_outcome=None,
            reconciliation_required=False,
        )

        evidence = serialize_evidence(result)
        evidence_str = str(evidence)

        assert "authorization_receipt" not in evidence_str.lower()
        assert "authorized_by" not in evidence_str.lower()


class TestRedactionDefensiveCoverage:
    """Tests that redaction defensively covers all container types."""

    def test_set_members_are_redacted(self) -> None:
        """Sensitive values inside sets are redacted."""
        sensitive = "postgres://secret:password@localhost:5432"
        safe = "benign_value"
        redacted = _redact_value({sensitive, safe})

        assert isinstance(redacted, list)
        redacted_str = str(redacted)
        assert sensitive not in redacted_str
        assert "[REDACTED]" in redacted_str
        assert safe in redacted

    def test_frozenset_members_are_redacted(self) -> None:
        """Sensitive values inside frozensets are redacted."""
        sensitive = "postgres://secret:password@localhost:5432"
        safe = "benign_value"
        redacted = _redact_value(frozenset({sensitive, safe}))

        assert isinstance(redacted, list)
        redacted_str = str(redacted)
        assert sensitive not in redacted_str
        assert "[REDACTED]" in redacted_str
        assert safe in redacted

    def test_dict_keys_are_redacted(self) -> None:
        """Sensitive connection-string keys in dicts are redacted."""
        sensitive_key = "postgres://secret:password@localhost:5432"
        safe_key = "benign_table"
        input_dict = {sensitive_key: 10, safe_key: 20}
        redacted = _redact_value(input_dict)

        assert isinstance(redacted, dict)
        redacted_str = str(redacted)
        assert sensitive_key not in redacted_str
        assert "[REDACTED_KEY_" in redacted_str
        assert safe_key in redacted


class TestDatabaseSelectorGate:
    """Tests for live-selector gate and blocked/skipped status preservation."""

    def test_default_selector_lists_every_live_gate_separately(self) -> None:
        """Every live gate is listed separately and default denied."""
        result = run_verification()

        selectors = result.get("selectors")
        assert isinstance(selectors, dict)
        for selector in LIVE_SELECTORS:
            assert selector in selectors

    def test_unexecuted_live_selectors_never_pass(self) -> None:
        """Unexecuted live selectors serialize as blocked/skipped, never pass."""
        result = run_verification()

        selectors = result["selectors"]
        for selector in LIVE_SELECTORS:
            status = selectors[selector]["status"]
            assert status in (BLOCKED_STATUS, SKIPPED_STATUS)
        assert result.get("outcome") != "pass"
        assert result.get("outcome") == "acceptance_blocked"

    def test_raner_smoke_never_claims_executed(self) -> None:
        """RaNER live smoke is blocked_not_executed; never claims it ran."""
        result = run_verification()

        raner = result["selectors"]["raner_smoke"]
        assert raner["status"] == BLOCKED_STATUS
        assert raner["status"] != "executed"
        assert "WSL" in raner["reason"]

    def test_c2_skipped_not_entered_with_reason_recorded(self) -> None:
        """C2 default-off branch records skipped_not_entered plus a reason."""
        result = run_verification()

        c2 = result["selectors"]["c2_entry"]
        assert c2["status"] == SKIPPED_STATUS
        assert c2["reason"]

    def test_enable_live_gates_still_fail_closed(self) -> None:
        """Even with live gates requested, the consumer cannot authorize them."""
        result = run_verification(enable_live_gates=True)

        for selector in LIVE_SELECTORS:
            status = result["selectors"][selector]["status"]
            assert status in (BLOCKED_STATUS, SKIPPED_STATUS)
        assert result.get("outcome") == "acceptance_blocked"


class TestC2BranchStates:
    """Tests for BOTH C2 branches (T-16-68)."""

    def test_entered_and_passed_branch_from_typed_record(self) -> None:
        """C2 entered and passed readiness gate derives from typed executed record."""
        record = consume_typed_result(C2_ENTERED, kind="c2_entry")

        assert record["status"] == "executed"
        assert record["typed_result"] is True
        assert record["c1_closure"]["hash_matched"] is True

    def test_skipped_branch_never_labeled_r_okf_09_tested(self) -> None:
        """Skipped C2 is never described as R-OKF-09 tested."""
        record = build_aggregate_record(C1_EVIDENCE, C2_SKIPPED)

        c2_branch = record["c2_branch"]
        assert c2_branch["branch"] == "not_entered_default_off"
        assert c2_branch["r_okf_09_tested"] is False
        assert c2_branch["reason"]

    def test_entered_branch_labels_r_okf_09_tested(self) -> None:
        """Entered-and-passed C2 branch is the only R-OKF-09 tested label."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        c2_branch = record["c2_branch"]
        assert c2_branch["branch"] == "entered_and_passed_readiness_gate"
        assert c2_branch["r_okf_09_tested"] is True


class TestZeroGenerativeLlmProof:
    """Tests for R-OKF-04 static AST/import + runtime LLM spy proof (T-16-67)."""

    def test_static_ast_import_proof_no_generative_llm_imports(self) -> None:
        """Static proof: extractor.py imports no generative-LLM module."""
        proof = prove_zero_generative_llm(_EXTRACTOR_PATH)

        static = proof["static_import_proof"]
        assert static["verified"] is True
        assert static["generative_llm_imports"] == []

    def test_runtime_llm_spy_zero_calls(self) -> None:
        """Runtime proof: enabled baseline makes zero .complete()/.acomplete() calls."""
        proof = prove_zero_generative_llm(_EXTRACTOR_PATH)

        runtime = proof["runtime_llm_spy"]
        assert runtime["complete_calls"] == 0
        assert runtime["acomplete_calls"] == 0
        assert runtime["verified"] is True

    def test_combined_proof_label(self) -> None:
        """Combined proof carries the static+runtime label."""
        proof = prove_zero_generative_llm(_EXTRACTOR_PATH)

        assert proof["proof"] == "static_ast_import_and_runtime_llm_spy"
        assert proof["verified"] is True

    def test_static_proof_detects_generative_llm_import(self, tmp_path: Path) -> None:
        """Static proof is not vacuous: a generative-LLM import is detected."""
        fake_module = tmp_path / "fake_extractor.py"
        fake_module.write_text(
            "import openai\nfrom llamaindex.llm import LLM\n",
            encoding="utf-8",
        )

        proof = prove_zero_generative_llm(fake_module)

        static = proof["static_import_proof"]
        assert static["verified"] is False
        assert "openai" in static["generative_llm_imports"]
        assert "llamaindex.llm" in static["generative_llm_imports"]


class TestNoFabricatedEvidence:
    """Tests for prohibiting fabricated/unattributed JSON as measured evidence."""

    def test_rejects_standalone_fabricated_json(self) -> None:
        """Standalone fabricated JSON claiming pass is rejected."""
        fabricated = {"status": "pass", "matrix": {}}

        with pytest.raises(ValueError, match="fabricated|typed|measured|provenance"):
            consume_typed_result(fabricated, kind="e2b_full_corpus")

    def test_rejects_json_without_typed_provenance(self) -> None:
        """JSON without schema_version typed provenance is rejected."""
        unattributed = {"status": "executed", "matrix": C1_EVIDENCE["matrix"]}

        with pytest.raises(ValueError, match="schema_version|provenance|fabricated"):
            consume_typed_result(unattributed, kind="e2b_full_corpus")

    def test_rejects_unknown_kind(self) -> None:
        """Unknown result kinds are rejected with static wording."""
        with pytest.raises(ValueError, match="(?i)unsupported typed result kind"):
            consume_typed_result(C1_EVIDENCE, kind="bogus_kind")

    def test_raner_smoke_executed_claim_rejected(self) -> None:
        """RaNER smoke never accepts an executed claim (WSL gap, user decision)."""
        forged_raner = {"schema_version": 1, "status": "executed"}

        with pytest.raises(ValueError, match="raner_smoke|executed|WSL"):
            consume_typed_result(forged_raner, kind="raner_smoke")

    def test_validate_evidence_authenticity_rejects_pass_outcome(self) -> None:
        """outcome='pass' is rejected with the dedicated provenance message."""
        fabricated = {
            "outcome": "pass",
            "primary_dml_by_table": {"entity_mentions": 100},
            "typed_result": True,
        }

        with pytest.raises(ValueError) as exc_info:
            validate_evidence_authenticity(fabricated)

        assert "PASS acceptance requires actual measured typed provenance" in str(
            exc_info.value
        )

    def test_validate_evidence_authenticity_rejects_missing_typed_result(self) -> None:
        """Evidence without typed_result=True format metadata is rejected."""
        missing_typed = {"outcome": "changed"}

        with pytest.raises(ValueError, match="typed.*result"):
            validate_evidence_authenticity(missing_typed)

    def test_aggregate_rejects_fabricated_c1(self) -> None:
        """Aggregate record rejects fabricated C1 branch JSON."""
        fabricated_c1 = {"status": "pass", "matrix": {}}

        with pytest.raises(ValueError, match="fabricated|typed|measured|provenance"):
            build_aggregate_record(fabricated_c1, C2_ENTERED)

    def test_aggregate_rejects_fabricated_c2(self) -> None:
        """Aggregate record rejects fabricated C2 branch JSON."""
        fabricated_c2 = {"status": "pass"}

        with pytest.raises(ValueError, match="fabricated|typed|measured|provenance"):
            build_aggregate_record(C1_EVIDENCE, fabricated_c2)


class TestAggregateAttribution:
    """Tests for the 4-item aggregate record attributed to typed C1/C2 branches."""

    def test_changed_set_convergence_attributed(self) -> None:
        """(a) Equivalent rerun zero DML AND selected-set-shrink deletion DML."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        item = record["items"]["changed_set_convergence"]
        assert item["equivalent_rerun_dml_total"] == 0
        assert item["selected_set_shrink_deletion_dml"] == 3
        assert item["outcome"] == "verified"
        assert item["source"] == "c1:matrix:equivalent_rerun+changed_set_convergence"

    def test_ownership_safe_bridge_deletion_attributed(self) -> None:
        """(b) Bridge deleted only with explicit ledger ownership, no other owner."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        item = record["items"]["ownership_safe_bridge_deletion"]
        assert item["bridge_deletion_dml"] == 1
        assert item["fail_closed_preserved_bridges"] == 0
        assert item["outcome"] == "deleted_with_ownership_proof"
        assert item["source"] == "c1:matrix:changed_set_convergence"

    def test_ownership_safe_fail_closed_preservation_recorded(self) -> None:
        """(b) Fail-closed preservation is recorded when another owner remains."""
        c1_fail_closed: dict[str, Any] = {
            "candidate_path": "fixture_candidates",
            "matrix": dict(C1_EVIDENCE["matrix"]),
            "schema_version": 1,
            "status": "executed",
        }
        c1_fail_closed["matrix"]["changed_set_convergence"] = dict(
            C1_EVIDENCE["matrix"]["changed_set_convergence"]
        )
        c1_fail_closed["matrix"]["changed_set_convergence"]["bridge_deletion_dml"] = 0
        c1_fail_closed["matrix"]["changed_set_convergence"][
            "fail_closed_preserved_bridges"
        ] = 1

        record = build_aggregate_record(c1_fail_closed, C2_ENTERED)

        item = record["items"]["ownership_safe_bridge_deletion"]
        assert item["bridge_deletion_dml"] == 0
        assert item["fail_closed_preserved_bridges"] == 1
        assert item["outcome"] == "fail_closed_preserved"

    def test_manual_legacy_preservation_attributed(self) -> None:
        """(c) Preloaded same-pair bridges and legacy mentions preserved, never claimed."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        item = record["items"]["manual_legacy_preservation"]
        assert item["claimed"] == 0
        assert item["deleted"] == 0
        assert item["manual_bridges_preserved"] == 1
        assert item["manual_mentions_preserved"] == 1
        assert item["outcome"] == "preserved_and_not_claimed"
        assert item["source"] == "c1:matrix:manual_legacy_preservation"

    def test_e2a_e2b_shared_lock_attributed(self) -> None:
        """(d) Same document/version serialized on okf:e2a:parent key."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        item = record["items"]["e2a_e2b_shared_lock"]
        assert item["lock_key_is_e2a"] is True
        assert item["serialized"] is True
        assert item["lock_key_pattern"] == "okf:e2a:parent:{document_id}:{version_id}"
        assert item["outcome"] == "serialized_on_e2a_parent_key"
        assert item["source"] == "c1:matrix:e2a_vs_e2b_serialization"

    def test_aggregate_never_claims_pass(self) -> None:
        """Aggregate record outcome is never 'pass'."""
        record = build_aggregate_record(C1_EVIDENCE, C2_ENTERED)

        assert record.get("outcome") != "pass"
        assert record.get("outcome") == "aggregate_record"
        assert record.get("typed_result") is True

    def test_migration_gate_typed_result_consumed(self) -> None:
        """Migration-gate outcome is consumed as a typed measured result."""
        record = consume_typed_result(MIGRATION_GATE_EVIDENCE, kind="migration_gate")

        assert record["status"] == "executed"
        assert record["catalog_apply_count"] == 1
        assert record["tables"] == [
            "okf_e2b_failure_audit",
            "okf_e2b_node_link_ownership",
        ]
        assert record["typed_result"] is True
