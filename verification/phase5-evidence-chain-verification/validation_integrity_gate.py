"""Validation integrity gate for Phase 5 rerun readiness.

Blocks metric calculation and human judgment collection when retrieval results,
judgment rows, and evidence-chain diagnostics are internally inconsistent.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3_DIR = REPO_ROOT / "verification" / "phase3-real-validation"
PHASE5_DIR = Path(__file__).parent
DEFAULT_RETRIEVAL_FILE = PHASE3_DIR / "retrieval_results.json"
DEFAULT_JUDGMENT_FILE = PHASE3_DIR / "judgment_completed.csv"
DEFAULT_COUNTS_FILE = PHASE5_DIR / "active_version_counts.json"
OUTPUT_FILE = PHASE5_DIR / "validation_integrity_report.json"
NEW_CORPUS_MARKER = "PageIndex完整功能分析与集成方案"
OLD_CORPUS_MARKERS = ("竞品分析", "第二阶段-竞品分析-代旭")
BLOCKING_CLASSIFICATIONS = {
    "missing_vector_materialization",
    "missing_node_chunk_mapping",
    "missing_heading_paths",
    "missing_canonical_spans",
}


def load_retrieval_results(path: Path) -> dict[str, object]:
    """Load retrieval results JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_judgment_rows(path: Path) -> list[dict[str, str]]:
    """Load judgment CSV rows as dictionaries."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _retrieval_hit_rows(retrieval: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    results = retrieval.get("results", [])
    if not isinstance(results, list):
        return rows

    for query_result in results:
        if not isinstance(query_result, dict):
            continue
        query_id = str(query_result.get("query_id", ""))
        hits = query_result.get("hits", [])
        if not isinstance(hits, list):
            continue
        for index, hit in enumerate(hits):
            if not isinstance(hit, dict):
                continue
            rows.append(
                {
                    "query_id": query_id,
                    "hit_rank": str(hit.get("rank", index + 1)),
                    "node_id": str(hit.get("node_id", "")),
                    "heading_path": str(hit.get("heading_path", "")),
                    "text_preview": str(hit.get("text_preview", "")),
                }
            )
    return rows


def validate_retrieval_judgment_integrity(
    retrieval: dict[str, object],
    judgments: list[dict[str, str]],
    *,
    allow_partial: bool = False,
) -> dict[str, object]:
    """Validate that judgment rows match the retrieval result corpus and hits."""
    hit_rows = _retrieval_hit_rows(retrieval)
    query_ids = {str(row["query_id"]) for row in hit_rows}
    hit_keys = {
        (str(row["query_id"]), str(row["hit_rank"]), str(row["node_id"]))
        for row in hit_rows
    }
    reasons: list[str] = []

    if not judgments:
        reasons.append("judgment_file_empty")

    for judgment in judgments:
        query_id = str(judgment.get("query_id", ""))
        hit_rank = str(judgment.get("hit_rank", ""))
        node_id = str(judgment.get("node_id", ""))
        if query_id not in query_ids:
            reasons.append("unknown_query_id")
            break
        if (query_id, hit_rank, node_id) not in hit_keys:
            reasons.append("unknown_hit")
            break

    if len(judgments) < len(hit_rows) and not allow_partial:
        reasons.append("missing_judgment_rows")

    retrieval_text = "\n".join(
        f"{row.get('heading_path', '')} {row.get('text_preview', '')}" for row in hit_rows
    )
    judgment_text = "\n".join(
        f"{row.get('heading_path', '')} {row.get('text_preview', '')}" for row in judgments
    )
    if NEW_CORPUS_MARKER in retrieval_text and any(
        marker in judgment_text for marker in OLD_CORPUS_MARKERS
    ):
        reasons.append("corpus_mismatch")

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "passed": not unique_reasons,
        "retrieval_hit_rows": len(hit_rows),
        "judgment_rows": len(judgments),
        "blocking_reasons": unique_reasons,
    }


def validate_evidence_chain_gate(
    counts: dict[str, object],
    *,
    allow_evidence_chain_gap: bool = False,
) -> dict[str, object]:
    """Validate evidence-chain readiness classification."""
    classification = str(counts.get("classification", ""))
    passed = classification == "evidence_chain_ready" or (
        allow_evidence_chain_gap and classification in BLOCKING_CLASSIFICATIONS
    )
    reasons = [] if passed else [classification or "missing_evidence_chain_classification"]
    return {
        "passed": passed,
        "classification": classification,
        "blocking_reasons": reasons,
    }


def _next_allowed_action(
    retrieval_gate: dict[str, object],
    evidence_gate: dict[str, object],
) -> str:
    if not evidence_gate.get("passed", False):
        return "fix_evidence_chain"
    reasons = set(retrieval_gate.get("blocking_reasons", []))
    if "corpus_mismatch" in reasons or "unknown_query_id" in reasons or "unknown_hit" in reasons:
        return "rerun_retrieval"
    if "missing_judgment_rows" in reasons or "judgment_file_empty" in reasons:
        return "fix_judgment_file"
    return "collect_judgments"


def build_validation_integrity_report(
    *,
    retrieval_path: Path,
    judgment_path: Path,
    counts_path: Path,
    allow_partial: bool = False,
    allow_evidence_chain_gap: bool = False,
) -> dict[str, object]:
    """Build a fail-closed integrity report from artifact paths."""
    blocking_reasons: list[str] = []

    if not retrieval_path.exists():
        blocking_reasons.append("retrieval_file_missing")
        retrieval: dict[str, object] = {"results": []}
    else:
        retrieval = load_retrieval_results(retrieval_path)

    if not judgment_path.exists():
        blocking_reasons.append("judgment_file_missing")
        judgments: list[dict[str, str]] = []
    else:
        judgments = load_judgment_rows(judgment_path)

    if not counts_path.exists():
        blocking_reasons.append("active_version_counts_missing")
        counts: dict[str, object] = {"classification": "missing_canonical_spans"}
    else:
        counts = json.loads(counts_path.read_text(encoding="utf-8"))

    retrieval_gate = validate_retrieval_judgment_integrity(
        retrieval,
        judgments,
        allow_partial=allow_partial,
    )
    evidence_gate = validate_evidence_chain_gate(
        counts,
        allow_evidence_chain_gap=allow_evidence_chain_gap,
    )
    blocking_reasons.extend(retrieval_gate.get("blocking_reasons", []))
    blocking_reasons.extend(evidence_gate.get("blocking_reasons", []))
    unique_reasons = list(dict.fromkeys(str(reason) for reason in blocking_reasons))
    passed = not unique_reasons
    return {
        "passed": passed,
        "retrieval_file": str(retrieval_path),
        "judgment_file": str(judgment_path),
        "counts_file": str(counts_path),
        "retrieval_judgment_integrity": retrieval_gate,
        "evidence_chain_gate": evidence_gate,
        "blocking_reasons": unique_reasons,
        "next_allowed_action": (
            "collect_judgments"
            if passed
            else _next_allowed_action(retrieval_gate, evidence_gate)
        ),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 5 validation integrity gates.")
    parser.add_argument("--retrieval-file", type=Path, default=DEFAULT_RETRIEVAL_FILE)
    parser.add_argument("--judgment-file", type=Path, default=DEFAULT_JUDGMENT_FILE)
    parser.add_argument("--counts-file", type=Path, default=DEFAULT_COUNTS_FILE)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--allow-evidence-chain-gap", action="store_true")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    report = build_validation_integrity_report(
        retrieval_path=args.retrieval_file,
        judgment_path=args.judgment_file,
        counts_path=args.counts_file,
        allow_partial=args.allow_partial,
        allow_evidence_chain_gap=args.allow_evidence_chain_gap,
    )
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
