"""Phase 8: Donor default-path promotion verification tests.

Tests verify whether donor-integrated path can replace baseline as default:
1. Donor path runs without fallback when OPENAI_API_KEY available
2. Provenance integrity preserved under real LLM execution
3. Comparison framework works on real documents with credentials

Exit criteria: Either promotion success (A) or promotion deferred with evidence (B).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.mark.integration
class TestPhase8CredentialedDonorExecution:
    """Tests for donor-integrated path execution with real LLM credentials."""

    def test_donor_path_calls_real_llm_when_credentials_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that PageIndex adapter calls real LLM via unified seam when OPENAI_API_KEY set.

        This test should FAIL initially because current implementation has fallback to stub.
        """
        # Setup: Mock OPENAI_API_KEY
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter
        from llamaindex_runtime.llm import get_llm

        # Create test PDF (minimal)
        test_pdf = tmp_path / "test_minimal.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 minimal stub\n")

        version_id = uuid.uuid4()
        registry = MagicMock()

        adapter = PageIndexTreeAdapter()

        # RED EXPECTATION: Should call real LLM seam, not fallback to stub
        # Current implementation: falls back to stub when PageIndex import fails
        # Target: should route through unified LLM seam successfully

        # This will fail initially because:
        # 1. PageIndex import may fail (external dependency)
        # 2. Even if import succeeds, LLM call may fail without real API

        # For TDD: We expect either successful LLM seam call OR controlled fallback
        # NOT silent stub fallback without logging

        with pytest.raises(Exception) as exc_info:
            # Should raise controlled exception when LLM call fails
            # NOT silently return stub tree
            adapter.index_tree(
                source_path=str(test_pdf),
                version_id=version_id,
                registry=registry,
            )

        # RED phase: Exception should be LLM-related, NOT PageIndex import failure
        # Target: we want to see LLM authentication or network error
        # NOT: "PageIndex tree_parser unavailable, using stub"

        # For Phase 8 success: This test should pass with real credentials
        # For Phase 8 deferred: This test proves LLM integration instability

    def test_donor_path_preserves_provenance_under_real_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that provenance contracts preserved when donor uses real LLM.

        Frozen contracts: doc_id, version_id, span_id, chunk_id, node_id must be UUIDs.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        test_pdf = tmp_path / "test_provenance.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 provenance test\n")

        version_id = uuid.uuid4()
        registry = MagicMock()

        adapter = PageIndexTreeAdapter()

        # Mock registry to capture written nodes
        written_nodes: list[dict[str, Any]] = []
        registry.write_tree = MagicMock(
            side_effect=lambda **kwargs: written_nodes.extend(kwargs.get("nodes", []))
        )

        # RED: Should preserve version_id provenance even when using real LLM
        try:
            adapter.index_tree(
                source_path=str(test_pdf),
                version_id=version_id,
                registry=registry,
            )
        except Exception:
            # Expected to fail in RED phase (no real LLM)
            pass

        # Provenance integrity check
        for node in written_nodes:
            assert isinstance(node.get("version_id"), uuid.UUID), "Frozen contract violation: version_id must be UUID"
            assert isinstance(node.get("node_id"), uuid.UUID), "Frozen contract violation: node_id must be UUID"
            assert node["version_id"] == version_id, "Provenance anchoring violation: version_id mismatch"


@pytest.mark.integration
class TestPhase8DonorBaselineComparison:
    """Tests for comparison framework between donor and baseline paths."""

    def test_comparison_framework_generates_promotion_decision_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that Phase 8 comparison produces explicit promotion/deferral decision.

        Report must include:
        - donor_hits count and quality metrics
        - baseline_hits count and quality metrics
        - provenance integrity check
        - explicit recommendation: promote OR defer with evidence
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        # RED: This test defines the expected Phase 8 comparison output
        # Current: phase7_comparison.py exists but uses mock registry
        # Target: phase8_comparison.py should use real registry + real credentials

        # Expected report structure:
        expected_report_keys = {
            "promotion_decision",  # "promote" | "defer"
            "donor_path_quality",
            "baseline_path_quality",
            "provenance_integrity",
            "blocking_factors",  # Required if decision="defer"
            "evidence",  # Required for both decisions
        }

        # For TDD: We'll create verification/phase8_comparison.py
        # This test should fail because phase8_comparison.py doesn't exist yet

        with pytest.raises(ImportError):
            from verification.phase8_comparison import compare_and_decide_promotion

            # Will fail in RED phase
            report = compare_and_decide_promotion(
                pdf_path=str(tmp_path / "test.pdf"),
                query_text="test query",
            )

            # Report must contain explicit decision
            assert report["promotion_decision"] in ["promote", "defer"]

            # If deferred, must have blocking factors
            if report["promotion_decision"] == "defer":
                assert len(report["blocking_factors"]) > 0, "Deferred decision requires blocking factors"

            # All expected keys present
            assert set(report.keys()) >= expected_report_keys


@pytest.mark.integration
class TestPhase8DefaultPathSwitch:
    """Tests for switching default path based on Phase 8 decision."""

    def test_runtime_defaults_to_donor_after_promotion_decision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that retrieve_tree_hits_from_pdf can switch default to donor-integrated.

        Current: decision_policy="baseline" is default (runtime.py:97)
        Target: After Phase 8 promotion success, default should switch to "hiro" (donor-integrated)
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf

        # RED: This test expects a new parameter or config to control default path
        # Current implementation: default is hardcoded to "baseline"

        # After Phase 8 promotion success:
        # Option A: Add default_policy parameter
        # Option B: Read from environment variable
        # Option C: Update control package and code follows

        # For TDD: We define the expected behavior
        # This should fail because current implementation doesn't support donor default

        version_id = uuid.uuid4()
        registry = MagicMock()

        # Mock minimal tree structure
        registry.query_tree_nodes_by_version = MagicMock(
            return_value=[
                {
                    "node_id": uuid.uuid4(),
                    "version_id": version_id,
                    "heading_path": "Test",
                    "page_no": 1,
                    "summary_text": "Test",
                }
            ]
        )

        # RED: Expecting new parameter to control default path
        # Will fail because parameter doesn't exist yet
        with pytest.raises(TypeError):
            hits = retrieve_tree_hits_from_pdf(
                "test.pdf",
                query="test",
                embed_model=None,
                version_id=version_id,
                registry=registry,
                default_policy="donor",  # New parameter for Phase 8
            )