"""Phase 8: Donor default-path promotion verification tests (with Phase 15 boundary tests).

This module contains:
1. TestPageIndexForbiddenBoundaryOnPageIndex (Phase 15): Pure unit tests for the
   static forbidden-authoring boundary enforced by PageIndexTreeAdapter.index_tree().
   These tests verify that index_tree() raises FORBIDDEN before any LLM call or
   registry interaction. No credentials, no fixtures, no I/O.

2. TestPhase8DonorBaselineComparison (Phase 8): Integration tests for the comparison
   framework between donor and baseline paths. Requires comparison module and tests
   report generation with promotion/deferral decisions.

3. TestPhase8DefaultPathSwitch (Phase 8): Integration tests for switching default path
   based on Phase 8 decision. Requires runtime module and tests default policy behavior.

Exit criteria: Either promotion success (A) or promotion deferred with evidence (B).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestPageIndexForbiddenBoundaryOnPageIndex:
    """Phase 15: Verify index_tree() enforces static FORBIDDEN boundary.

    These are pure unit tests — no LLM call, no credentials, no fixture,
    no I/O. The boundary fires before any path read or registry interaction.
    """

    def test_index_tree_forbidden_boundary_without_llm_call(
        self,
    ) -> None:
        """Phase 15: Verify index_tree raises FORBIDDEN without LLM call.

        Ensures that index_tree() enforces the consumer-only boundary
        and raises FORBIDDEN RuntimeError. No live LLM invocation occurs;
        no credentials are required. The path value is irrelevant (never read).
        """
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()
        registry = MagicMock()
        version_id = uuid.uuid4()

        # Plain path string — value is irrelevant; index_tree() never reads it.
        source_path = "any/path/that/is/never/read.pdf"

        # MUST raise FORBIDDEN RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            adapter.index_tree(
                source_path=source_path,
                version_id=version_id,
                registry=registry,
            )

        # Verify FORBIDDEN error message (static consumer-boundary enforcement)
        error_msg = str(exc_info.value)
        assert "FORBIDDEN" in error_msg
        assert "cannot author canonical" in error_msg.lower()

        # Verify registry.write_tree was NEVER called
        registry.write_tree.assert_not_called()

    def test_index_tree_forbidden_prevents_provenance_violation(
        self,
    ) -> None:
        """Phase 15: Verify forbidden boundary prevents any provenance flow.

        Ensures that the FORBIDDEN RuntimeError is raised before any write_tree call,
        preventing any provenance data from reaching the registry. Zero registry
        writer calls.
        """
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()
        registry = MagicMock()
        version_id = uuid.uuid4()

        # Plain path string — value is irrelevant; index_tree() never reads it.
        source_path = "any/path/that/is/never/read.pdf"

        # MUST raise FORBIDDEN RuntimeError before any write attempt
        with pytest.raises(RuntimeError) as exc_info:
            adapter.index_tree(
                source_path=source_path,
                version_id=version_id,
                registry=registry,
            )

        # Verify FORBIDDEN error
        assert "FORBIDDEN" in str(exc_info.value)

        # Verify zero registry writer calls (no provenance data leaked)
        registry.write_tree.assert_not_called()


@pytest.mark.integration
class TestPhase8DonorBaselineComparison:
    """Tests for comparison framework between donor and baseline paths."""

    def test_comparison_framework_generates_promotion_decision_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GREEN: Test that Phase 8 comparison produces explicit promotion/deferral decision.

        Report must include:
        - donor_hits count and quality metrics
        - baseline_hits count and quality metrics
        - provenance integrity check
        - explicit recommendation: promote OR defer with evidence
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        # GREEN: phase8_comparison.py now exists
        from verification.phase8_comparison import compare_and_decide_promotion

        # Create minimal test PDF
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 minimal test\n")

        # GREEN: Run comparison framework
        report = compare_and_decide_promotion(
            pdf_path=str(test_pdf),
            query_text="test query",
        )

        # GREEN: Report must contain explicit decision
        assert report["promotion_decision"] in ["promote", "defer"]

        # If deferred, must have blocking factors
        if report["promotion_decision"] == "defer":
            assert (
                len(report["blocking_factors"]) > 0
            ), "Deferred decision requires blocking factors"

        # All expected keys present
        expected_report_keys = {
            "promotion_decision",
            "donor_path_quality",
            "baseline_path_quality",
            "provenance_integrity",
            "blocking_factors",
            "evidence",
        }
        assert set(report.keys()) >= expected_report_keys

        # GREEN: Provenance integrity must be True (both paths preserve frozen contracts)
        assert report["provenance_integrity"] is True


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

        # RED: Expecting environment variable or parameter to control default path
        # Will fail because current parameter is decision_policy, not default_policy
        # Phase 8 implementation: decision_policy parameter + RAG_TREE_DECISION_POLICY env

        # Option 1: Use environment variable
        monkeypatch.setenv("RAG_TREE_DECISION_POLICY", "hiro")

        hits_env = retrieve_tree_hits_from_pdf(
            "test.pdf",
            query="test",
            embed_model=None,
            version_id=version_id,
            registry=registry,
        )

        # Option 2: Use explicit parameter (should work)
        hits_param = retrieve_tree_hits_from_pdf(
            "test.pdf",
            query="test",
            embed_model=None,
            version_id=version_id,
            registry=registry,
            decision_policy="hiro",
        )

        # GREEN: Both options should work
        assert isinstance(hits_env, list)
        assert isinstance(hits_param, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
