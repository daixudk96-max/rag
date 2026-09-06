"""Phase 8 integrity gate wrapper for matched validation artifacts.

The wrapper gates human judgment collection and metric calculation. It is
Phase 8-scoped, fail-closed, and does not create completed judgments itself.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import inspect
import json
from pathlib import Path
from types import ModuleType

PHASE8_DIR = Path(__file__).parent
PHASE5_GATE_PATH = (
    PHASE8_DIR.parent
    / "phase5-evidence-chain-verification"
    / "validation_integrity_gate.py"
)
RETRIEVAL_FILE = PHASE8_DIR / "retrieval_results.json"
JUDGMENT_TEMPLATE_FILE = PHASE8_DIR / "judgment_template.csv"
JUDGMENT_COMPLETED_FILE = PHASE8_DIR / "judgment_completed.csv"
EVIDENCE_COUNTS_FILE = (
    PHASE8_DIR.parent
    / "phase7-db-backed-evidence-chain-rerun"
    / "active_version_counts.after.json"
)
VALIDATION_STATUS_FILE = PHASE8_DIR / "validation_status.json"
OUTPUT_FILE = PHASE8_DIR / "validation_integrity_report.json"
JUDGMENT_STATUS_FILE = PHASE8_DIR / "judgment_collection_status.json"

PLACEHOLDERS = {"True/False", "0.00", "<category>", "<notes>", ""}
REQUIRED_PHASE5_GATE_FUNCTIONS = (
    "build_validation_integrity_report",
    "validate_retrieval_judgment_integrity",
    "validate_evidence_chain_gate",
)
BUILD_REPORT_PARAMETERS = {
    "retrieval_path",
    "judgment_path",
    "counts_path",
    "allow_partial",
    "allow_evidence_chain_gap",
}


def _validate_phase5_gate_signature(module: ModuleType) -> None:
    """Raise when the Phase 5 gate API is not compatible with Phase 8."""
    build_report = getattr(module, "build_validation_integrity_report", None)
    if not callable(build_report):
        raise ImportError("phase5_gate_incompatible")
    parameters = set(inspect.signature(build_report).parameters)
    if not BUILD_REPORT_PARAMETERS.issubset(parameters):
        raise ImportError("phase5_gate_incompatible_signature")


def load_phase5_gate_module() -> ModuleType:
    """Load the existing Phase 5 validation gate module and verify its API."""
    spec = importlib.util.spec_from_file_location(
        "phase5_validation_integrity_gate", PHASE5_GATE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError("phase5_gate_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [
        name
        for name in REQUIRED_PHASE5_GATE_FUNCTIONS
        if not callable(getattr(module, name, None))
    ]
    if missing:
        raise ImportError("phase5_gate_incompatible")
    _validate_phase5_gate_signature(module)
    return module


def _load_json(path: Path) -> dict[str, object]:
    """Load a JSON object or return an empty object when missing."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    """Load judgment CSV rows."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _retrieval_is_ready() -> bool:
    """Return whether matched retrieval completed successfully."""
    status = _load_json(VALIDATION_STATUS_FILE)
    return status.get("status") == "MATCHED_RETRIEVAL_READY"


def _retrieval_payload_is_valid() -> bool:
    """Return whether retrieval results have the expected Phase 8 JSON shape."""
    retrieval = _load_json(RETRIEVAL_FILE)
    results = retrieval.get("results")
    if not isinstance(results, list):
        return False
    for result in results:
        if not isinstance(result, dict):
            return False
        if not isinstance(result.get("query_id"), str):
            return False
        hits = result.get("hits")
        if not isinstance(hits, list):
            return False
        for hit in hits:
            if not isinstance(hit, dict):
                return False
            if "rank" not in hit or "node_id" not in hit:
                return False
    return True


def _rows_have_placeholders(rows: list[dict[str, str]]) -> bool:
    """Return true if any completed judgment field still has placeholders."""
    required_fields = (
        "is_relevant",
        "relevance_score",
        "judgment_category",
        "judgment_notes",
    )
    for row in rows:
        for field in required_fields:
            if str(row.get(field, "")).strip() in PLACEHOLDERS:
                return True
    return False


def _base_report_for_missing_artifacts(reason: str) -> dict[str, object]:
    """Create a fail-closed report for missing or blocked Phase 8 artifacts."""
    return {
        "passed": False,
        "retrieval_file": str(RETRIEVAL_FILE),
        "judgment_file": str(JUDGMENT_TEMPLATE_FILE),
        "counts_file": str(EVIDENCE_COUNTS_FILE),
        "blocking_reasons": [reason],
        "next_allowed_action": (
            "rerun_retrieval"
            if reason
            in {
                "matched_retrieval_missing",
                "matched_retrieval_blocked",
                "retrieval_results_invalid",
            }
            else "fix_evidence_chain"
        ),
    }


def build_phase8_integrity_report(
    judgment_file: Path, *, completed: bool = False
) -> dict[str, object]:
    """Build the Phase 8 integrity report for template or completed judgments."""
    if not RETRIEVAL_FILE.exists():
        return _base_report_for_missing_artifacts("matched_retrieval_missing")
    if not _retrieval_payload_is_valid():
        return _base_report_for_missing_artifacts("retrieval_results_invalid")
    if not _retrieval_is_ready():
        return _base_report_for_missing_artifacts("matched_retrieval_blocked")
    counts = _load_json(EVIDENCE_COUNTS_FILE)
    if counts.get("classification") != "evidence_chain_ready":
        return _base_report_for_missing_artifacts("evidence_chain_not_ready")

    gate = load_phase5_gate_module()
    report = gate.build_validation_integrity_report(
        retrieval_path=RETRIEVAL_FILE,
        judgment_path=judgment_file,
        counts_path=EVIDENCE_COUNTS_FILE,
        allow_partial=False,
        allow_evidence_chain_gap=False,
    )
    rows = _load_csv_rows(judgment_file)
    reasons = [str(reason) for reason in report.get("blocking_reasons", [])]

    if not completed:
        if not rows:
            reasons.append("judgment_template_empty")
        if not _rows_have_placeholders(rows):
            reasons.append("judgment_template_has_no_placeholders")
        return {
            **report,
            "passed": False,
            "blocking_reasons": list(dict.fromkeys(reasons)),
            "next_allowed_action": "collect_judgments",
        }

    if not judgment_file.exists():
        reasons.append("completed_judgment_file_missing")
    elif not rows:
        reasons.append("judgment_file_empty")
    elif _rows_have_placeholders(rows):
        reasons.append("placeholder_judgment_values")

    unique_reasons = list(dict.fromkeys(reasons))
    passed = not unique_reasons
    return {
        **report,
        "passed": passed,
        "blocking_reasons": unique_reasons,
        "next_allowed_action": "calculate_metrics" if passed else "collect_judgments",
    }


def build_judgment_collection_status(report: dict[str, object]) -> dict[str, object]:
    """Build the manual-judgment checkpoint status from an integrity report."""
    next_action = str(report.get("next_allowed_action", ""))
    reasons = report.get("blocking_reasons", [])
    if report.get("passed") is True and next_action == "calculate_metrics":
        status = "JUDGMENTS_COMPLETE"
        human_action_required = False
    elif next_action == "collect_judgments":
        status = "READY_FOR_HUMAN_JUDGMENT"
        human_action_required = True
    else:
        status = "BLOCKED"
        human_action_required = False

    return {
        "status": status,
        "next_allowed_action": next_action,
        "blocking_reasons": reasons if isinstance(reasons, list) else [],
        "template_file": str(JUDGMENT_TEMPLATE_FILE),
        "completed_file": str(JUDGMENT_COMPLETED_FILE),
        "human_action_required": human_action_required,
        "level_baseline": "Level 2 remains authoritative",
    }


def write_reports(report: dict[str, object], status: dict[str, object]) -> None:
    """Write Phase 8 integrity and judgment checkpoint artifacts."""
    PHASE8_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    JUDGMENT_STATUS_FILE.write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 8 integrity gate.")
    parser.add_argument("--completed", action="store_true")
    return parser


def main() -> int:
    """CLI entry point for Phase 8 integrity gate."""
    args = _build_arg_parser().parse_args()
    judgment_file = (
        JUDGMENT_COMPLETED_FILE if args.completed else JUDGMENT_TEMPLATE_FILE
    )
    report = build_phase8_integrity_report(judgment_file, completed=args.completed)
    status = build_judgment_collection_status(report)
    write_reports(report, status)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return (
        0
        if status.get("status") in {"READY_FOR_HUMAN_JUDGMENT", "JUDGMENTS_COMPLETE"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
