"""Tests for Phase 8 matched validation fail-closed helpers."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


PHASE8_DIR = (
    Path(__file__).resolve().parents[2]
    / "verification"
    / "phase8-matched-validation-rerun"
)


def load_phase8_module(module_name: str) -> ModuleType:
    """Load a Phase 8 script from its hyphenated directory."""
    path = PHASE8_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write a JSON fixture."""
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_template_csv(path: Path, *, completed: bool = False) -> None:
    """Write a one-row Phase 8 judgment CSV."""
    values = {
        "query_id": "Q01",
        "hit_rank": "1",
        "node_id": "node-1",
        "heading_path": "Root/Section",
        "page_no": "1",
        "text_preview": "PageIndex完整功能分析与集成方案 evidence",
        "is_relevant": "true" if completed else "True/False",
        "relevance_score": "0.95" if completed else "0.00",
        "judgment_category": "direct" if completed else "<category>",
        "judgment_notes": "matched" if completed else "<notes>",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(values))
        writer.writeheader()
        writer.writerow(values)


def test_preflight_allows_ready_phase7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("phase8_preflight")
    evidence = tmp_path / "evidence_chain_delta.json"
    readiness = tmp_path / "db_readiness.json"
    output = tmp_path / "phase8_preflight_status.json"
    remediation = tmp_path / "remediation_required.json"
    write_json(
        evidence,
        {
            "final_classification": "DB_EVIDENCE_READY",
            "active_version_id": "version-1",
            "blocking_reasons": [],
        },
    )
    write_json(readiness, {"database_url_configured": True})
    monkeypatch.setattr(module, "EVIDENCE_DELTA_FILE", evidence)
    monkeypatch.setattr(module, "DB_READINESS_FILE", readiness)
    monkeypatch.setattr(module, "OUTPUT_FILE", output)
    monkeypatch.setattr(module, "REMEDIATION_FILE", remediation)

    status = module.build_preflight_status()
    module.write_outputs(status)

    assert status["status"] == "READY_FOR_MATCHED_VALIDATION"
    assert status["ready_for_matched_validation"] is True
    assert status["next_allowed_action"] == "run_matched_retrieval"
    assert (
        json.loads(output.read_text(encoding="utf-8"))["active_version_id"]
        == "version-1"
    )
    assert not remediation.exists()


def test_preflight_routes_blocked_phase7_to_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("phase8_preflight")
    evidence = tmp_path / "evidence_chain_delta.json"
    readiness = tmp_path / "db_readiness.json"
    output = tmp_path / "phase8_preflight_status.json"
    remediation = tmp_path / "remediation_required.json"
    write_json(
        evidence,
        {
            "final_classification": "DB_EVIDENCE_BLOCKED",
            "active_version_id": "version-1",
            "blocking_reasons": ["missing_canonical_spans"],
        },
    )
    write_json(readiness, {"database_url_configured": False})
    monkeypatch.setattr(module, "EVIDENCE_DELTA_FILE", evidence)
    monkeypatch.setattr(module, "DB_READINESS_FILE", readiness)
    monkeypatch.setattr(module, "OUTPUT_FILE", output)
    monkeypatch.setattr(module, "REMEDIATION_FILE", remediation)

    status = module.build_preflight_status()
    module.write_outputs(status)

    assert status["status"] == "EVIDENCE_CHAIN_REMEDIATION_REQUIRED"
    assert status["ready_for_matched_validation"] is False
    assert "missing_canonical_spans" in status["blocking_reasons"]
    assert remediation.exists()


def test_judgment_template_contains_placeholders_and_no_completed_reference() -> None:
    module = load_phase8_module("run_matched_validation")
    csv_text = module.generate_judgment_template(
        [
            {
                "query_id": "Q01",
                "hits": [
                    {
                        "rank": 1,
                        "node_id": "00000000-0000-0000-0000-000000000001",
                        "heading_path": "Root/Section",
                        "page_no": 1,
                        "text_preview": "preview",
                    }
                ],
            }
        ]
    )

    assert "query_id,hit_rank,node_id,heading_path,page_no,text_preview" in csv_text
    assert "True/False" in csv_text
    assert "<category>" in csv_text
    assert "judgment_completed.csv" not in (
        PHASE8_DIR / "run_matched_validation.py"
    ).read_text(encoding="utf-8")


def test_integrity_gate_allows_collect_judgments_for_ready_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("run_phase8_integrity_gate")
    retrieval = tmp_path / "retrieval_results.json"
    template = tmp_path / "judgment_template.csv"
    counts = tmp_path / "active_version_counts.after.json"
    validation_status = tmp_path / "validation_status.json"
    write_json(
        retrieval,
        {
            "query_count": 1,
            "results": [
                {
                    "query_id": "Q01",
                    "hits": [
                        {
                            "rank": 1,
                            "node_id": "node-1",
                            "heading_path": "Root/Section",
                            "text_preview": "PageIndex完整功能分析与集成方案 evidence",
                        }
                    ],
                }
            ],
        },
    )
    write_template_csv(template)
    write_json(counts, {"classification": "evidence_chain_ready"})
    write_json(validation_status, {"status": "MATCHED_RETRIEVAL_READY"})
    monkeypatch.setattr(module, "RETRIEVAL_FILE", retrieval)
    monkeypatch.setattr(module, "JUDGMENT_TEMPLATE_FILE", template)
    monkeypatch.setattr(module, "EVIDENCE_COUNTS_FILE", counts)
    monkeypatch.setattr(module, "VALIDATION_STATUS_FILE", validation_status)

    report = module.build_phase8_integrity_report(template)
    status = module.build_judgment_collection_status(report)

    assert report["passed"] is False
    assert report["next_allowed_action"] == "collect_judgments"
    assert status["status"] == "READY_FOR_HUMAN_JUDGMENT"


def test_integrity_gate_rejects_completed_placeholder_judgments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("run_phase8_integrity_gate")
    retrieval = tmp_path / "retrieval_results.json"
    completed = tmp_path / "judgment_completed.csv"
    counts = tmp_path / "active_version_counts.after.json"
    validation_status = tmp_path / "validation_status.json"
    write_json(
        retrieval,
        {
            "query_count": 1,
            "results": [
                {
                    "query_id": "Q01",
                    "hits": [
                        {
                            "rank": 1,
                            "node_id": "node-1",
                            "heading_path": "Root/Section",
                            "text_preview": "PageIndex完整功能分析与集成方案 evidence",
                        }
                    ],
                }
            ],
        },
    )
    write_template_csv(completed, completed=False)
    write_json(counts, {"classification": "evidence_chain_ready"})
    write_json(validation_status, {"status": "MATCHED_RETRIEVAL_READY"})
    monkeypatch.setattr(module, "RETRIEVAL_FILE", retrieval)
    monkeypatch.setattr(module, "EVIDENCE_COUNTS_FILE", counts)
    monkeypatch.setattr(module, "VALIDATION_STATUS_FILE", validation_status)

    report = module.build_phase8_integrity_report(completed, completed=True)

    assert report["passed"] is False
    assert "placeholder_judgment_values" in report["blocking_reasons"]
    assert report["next_allowed_action"] == "collect_judgments"


def test_integrity_gate_rejects_invalid_retrieval_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("run_phase8_integrity_gate")
    retrieval = tmp_path / "retrieval_results.json"
    template = tmp_path / "judgment_template.csv"
    counts = tmp_path / "active_version_counts.after.json"
    validation_status = tmp_path / "validation_status.json"
    write_json(retrieval, {"query_count": 1, "results": "not-a-list"})
    write_template_csv(template)
    write_json(counts, {"classification": "evidence_chain_ready"})
    write_json(validation_status, {"status": "MATCHED_RETRIEVAL_READY"})
    monkeypatch.setattr(module, "RETRIEVAL_FILE", retrieval)
    monkeypatch.setattr(module, "JUDGMENT_TEMPLATE_FILE", template)
    monkeypatch.setattr(module, "EVIDENCE_COUNTS_FILE", counts)
    monkeypatch.setattr(module, "VALIDATION_STATUS_FILE", validation_status)

    report = module.build_phase8_integrity_report(template)

    assert report["passed"] is False
    assert report["blocking_reasons"] == ["retrieval_results_invalid"]
    assert report["next_allowed_action"] == "rerun_retrieval"


def test_metrics_refuses_without_calculate_metrics_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("calculate_phase8_metrics")
    integrity = tmp_path / "validation_integrity_report.json"
    level = tmp_path / "level_assessment.json"
    write_json(integrity, {"next_allowed_action": "collect_judgments"})
    monkeypatch.setattr(module, "INTEGRITY_REPORT_FILE", integrity)
    monkeypatch.setattr(module, "LEVEL_FILE", level)

    with pytest.raises(RuntimeError, match="Phase 8 integrity gate"):
        module.assert_metrics_allowed(module.load_integrity_report())
    assert not level.exists()


def test_metrics_main_fails_closed_when_retrieval_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_phase8_module("calculate_phase8_metrics")
    integrity = tmp_path / "validation_integrity_report.json"
    retrieval = tmp_path / "retrieval_results.json"
    judgment = tmp_path / "judgment_completed.csv"
    metrics = tmp_path / "quality_metrics.json"
    level = tmp_path / "level_assessment.json"
    write_json(integrity, {"passed": True, "next_allowed_action": "calculate_metrics"})
    write_template_csv(judgment, completed=True)
    monkeypatch.setattr(module, "INTEGRITY_REPORT_FILE", integrity)
    monkeypatch.setattr(module, "RETRIEVAL_FILE", retrieval)
    monkeypatch.setattr(module, "JUDGMENT_FILE", judgment)
    monkeypatch.setattr(module, "METRICS_FILE", metrics)
    monkeypatch.setattr(module, "LEVEL_FILE", level)

    assert module.main() == 2
    assert not metrics.exists()
    assert not level.exists()


def test_metrics_rejects_malformed_completed_judgments(tmp_path: Path) -> None:
    module = load_phase8_module("calculate_phase8_metrics")
    malformed = tmp_path / "judgment_completed.csv"
    malformed.write_text(
        "query_id,hit_rank,node_id\nQ01,not-a-rank,node-1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid_completed_judgment_row"):
        module.load_completed_judgments(malformed)
