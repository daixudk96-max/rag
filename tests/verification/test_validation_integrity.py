from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "verification"
    / "phase5-evidence-chain-verification"
    / "verify_active_version_counts.py"
)
HEADING_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "verification"
    / "phase5-evidence-chain-verification"
    / "verify_heading_path_contract.py"
)
VALIDATION_GATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "verification"
    / "phase5-evidence-chain-verification"
    / "validation_integrity_gate.py"
)
_SPEC = importlib.util.spec_from_file_location("verify_active_version_counts", MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
verify_active_version_counts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_active_version_counts)

_HEADING_SPEC = importlib.util.spec_from_file_location(
    "verify_heading_path_contract",
    HEADING_CONTRACT_PATH,
)
assert _HEADING_SPEC is not None
assert _HEADING_SPEC.loader is not None
verify_heading_path_contract = importlib.util.module_from_spec(_HEADING_SPEC)
_HEADING_SPEC.loader.exec_module(verify_heading_path_contract)

_GATE_SPEC = importlib.util.spec_from_file_location(
    "validation_integrity_gate",
    VALIDATION_GATE_PATH,
)
assert _GATE_SPEC is not None
assert _GATE_SPEC.loader is not None
validation_integrity_gate = importlib.util.module_from_spec(_GATE_SPEC)
_GATE_SPEC.loader.exec_module(validation_integrity_gate)


def test_heading_path_contract_uses_canonical_spans_as_authoritative_source() -> None:
    contract = verify_heading_path_contract.build_heading_path_contract()

    assert contract["authoritative_source"] == "canonical_spans.heading_path"
    assert "authoritative_source" in contract


def test_active_version_counts_classifies_missing_vector_materialization() -> None:
    counts = {
        "canonical_spans": 3,
        "canonical_spans_with_heading_path": 3,
        "heading_path_rate": 1.0,
        "vector_chunks": 0,
        "vector_chunks_with_node_id": 0,
        "vector_chunk_spans": 0,
        "tree_node_spans": 3,
    }

    assert (
        verify_active_version_counts.classify_evidence_chain_state(counts)
        == "missing_vector_materialization"
    )


def test_active_version_counts_classifies_missing_heading_paths() -> None:
    counts = {
        "canonical_spans": 3,
        "canonical_spans_with_heading_path": 0,
        "heading_path_rate": 0.0,
        "vector_chunks": 3,
        "vector_chunks_with_node_id": 3,
        "vector_chunk_spans": 3,
        "tree_node_spans": 3,
    }

    assert (
        verify_active_version_counts.classify_evidence_chain_state(counts)
        == "missing_heading_paths"
    )


def test_invalid_uuid_is_rejected() -> None:
    try:
        verify_active_version_counts.parse_version_id("not-a-uuid")
    except ValueError as exc:
        assert "Invalid version_id" in str(exc)
    else:
        raise AssertionError("invalid UUID should fail before any SQL executes")


def test_parse_version_id_accepts_uuid_string() -> None:
    version_id = uuid.uuid4()

    assert verify_active_version_counts.parse_version_id(str(version_id)) == version_id


def test_evidence_chain_gate_blocks_missing_vector_materialization() -> None:
    result = validation_integrity_gate.validate_evidence_chain_gate(
        {"classification": "missing_vector_materialization"}
    )

    assert result["passed"] is False
    assert "missing_vector_materialization" in result["blocking_reasons"]


def test_evidence_chain_gate_allows_ready_state() -> None:
    result = validation_integrity_gate.validate_evidence_chain_gate(
        {"classification": "evidence_chain_ready"}
    )

    assert result["passed"] is True
    assert result["blocking_reasons"] == []


def test_integrity_gate_blocks_old_corpus_judgments_for_new_corpus_retrieval() -> None:
    retrieval = {
        "results": [
            {
                "query_id": "Q1",
                "hits": [
                    {
                        "rank": 1,
                        "node_id": "node-1",
                        "heading_path": "PageIndex完整功能分析与集成方案/Reasoning 检索路径",
                        "text_preview": "PageIndex完整功能分析与集成方案 evidence",
                    }
                ],
            }
        ]
    }
    judgments = [
        {
            "query_id": "Q1",
            "hit_rank": "1",
            "node_id": "node-1",
            "heading_path": "第二阶段-竞品分析-代旭/SWOT",
            "text_preview": "竞品分析 old corpus evidence",
        }
    ]

    result = validation_integrity_gate.validate_retrieval_judgment_integrity(
        retrieval,
        judgments,
    )

    assert result["passed"] is False
    assert "corpus_mismatch" in result["blocking_reasons"]


def test_integrity_gate_blocks_when_judgment_rows_are_missing() -> None:
    retrieval = {
        "results": [
            {
                "query_id": "Q1",
                "hits": [
                    {"rank": 1, "node_id": "node-1"},
                    {"rank": 2, "node_id": "node-2"},
                ],
            }
        ]
    }
    judgments = [{"query_id": "Q1", "hit_rank": "1", "node_id": "node-1"}]

    blocked = validation_integrity_gate.validate_retrieval_judgment_integrity(
        retrieval,
        judgments,
    )
    allowed = validation_integrity_gate.validate_retrieval_judgment_integrity(
        retrieval,
        judgments,
        allow_partial=True,
    )

    assert blocked["passed"] is False
    assert "missing_judgment_rows" in blocked["blocking_reasons"]
    assert allowed["passed"] is True


# TODO(Phase 5 Plan 04): add corpus mismatch gate tests after validation_integrity_gate.py exists
