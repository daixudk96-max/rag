"""Phase 8 metrics and Level assessment calculator.

Metrics are calculated only after the Phase 8 integrity gate explicitly allows
`calculate_metrics`. Until then, no Phase 8 level assessment is written.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

MIN_HIT_RATE = 0.80
MIN_TOP1_RELEVANCE = 0.90
MIN_STABILITY = 0.85
PHASE8_DIR = Path(__file__).parent
INTEGRITY_REPORT_FILE = PHASE8_DIR / "validation_integrity_report.json"
RETRIEVAL_FILE = PHASE8_DIR / "retrieval_results.json"
JUDGMENT_FILE = PHASE8_DIR / "judgment_completed.csv"
METRICS_FILE = PHASE8_DIR / "quality_metrics.json"
LEVEL_FILE = PHASE8_DIR / "level_assessment.json"
PLACEHOLDERS = {"True/False", "<category>", "<notes>"}
REQUIRED_JUDGMENT_FIELDS = (
    "query_id",
    "hit_rank",
    "node_id",
    "heading_path",
    "page_no",
    "text_preview",
    "is_relevant",
    "relevance_score",
    "judgment_category",
    "judgment_notes",
)


class Judgment(NamedTuple):
    """Completed Phase 8 judgment row."""

    query_id: str
    hit_rank: int
    node_id: str
    heading_path: str
    page_no: int | None
    text_preview: str
    is_relevant: bool
    relevance_score: float
    judgment_category: str
    judgment_notes: str


def load_integrity_report() -> dict[str, object]:
    """Load Phase 8 integrity report."""
    if not INTEGRITY_REPORT_FILE.exists():
        return {}
    payload = json.loads(INTEGRITY_REPORT_FILE.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def assert_metrics_allowed(report: dict[str, object]) -> None:
    """Require integrity gate authorization before metrics calculation."""
    if report.get("next_allowed_action") != "calculate_metrics":
        raise RuntimeError("Phase 8 integrity gate has not allowed metric calculation")
    if report.get("passed") is not True:
        raise RuntimeError("Phase 8 integrity gate has not allowed metric calculation")


def _parse_bool(value: str) -> bool:
    """Parse a judgment boolean value."""
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("invalid_boolean_judgment")


def _parse_page_no(value: str) -> int | None:
    """Parse page number from a judgment row."""
    if value in {"", "N/A", "None", "null"}:
        return None
    return int(value)


def _row_has_placeholder(row: dict[str, str]) -> bool:
    """Return whether a completed judgment row still contains placeholders."""
    if any(str(row.get(field, "")).strip() in PLACEHOLDERS for field in row):
        return True
    # In the generated template, the score placeholder is paired with an empty or
    # placeholder category. A real 0.00 score is valid only with a real category.
    return row.get("relevance_score", "").strip() == "0.00" and row.get(
        "judgment_category", ""
    ).strip() in {"", "<category>"}


def _validate_judgment_row(row: dict[str, str]) -> None:
    """Validate that a completed judgment row has the required CSV shape."""
    if any(field not in row for field in REQUIRED_JUDGMENT_FIELDS):
        raise ValueError("invalid_completed_judgment_row")
    if _row_has_placeholder(row):
        raise ValueError("placeholder_judgment_values")


def load_completed_judgments(csv_path: Path) -> list[Judgment]:
    """Load completed Phase 8 judgments and reject placeholders."""
    if not csv_path.exists():
        raise ValueError("judgment_completed_missing")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    judgments: list[Judgment] = []
    for row in rows:
        try:
            _validate_judgment_row(row)
            judgments.append(
                Judgment(
                    query_id=row["query_id"],
                    hit_rank=int(row["hit_rank"]),
                    node_id=row["node_id"],
                    heading_path=row["heading_path"],
                    page_no=_parse_page_no(row["page_no"]),
                    text_preview=row["text_preview"],
                    is_relevant=_parse_bool(row["is_relevant"]),
                    relevance_score=float(row["relevance_score"]),
                    judgment_category=row["judgment_category"].strip(),
                    judgment_notes=row.get("judgment_notes", ""),
                )
            )
        except KeyError as exc:
            raise ValueError("invalid_completed_judgment_row") from exc
        except ValueError as exc:
            if str(exc) == "placeholder_judgment_values":
                raise
            if str(exc) == "judgment_completed_missing":
                raise
            raise ValueError("invalid_completed_judgment_row") from exc
    return judgments


def calculate_hit_rate(
    judgments: list[Judgment], retrieval_results: dict[str, object]
) -> float:
    """Calculate queries with at least one relevant hit over total queries."""
    total_queries = int(retrieval_results.get("query_count") or 0)
    queries_with_relevant_hits = {
        judgment.query_id for judgment in judgments if judgment.is_relevant
    }
    return len(queries_with_relevant_hits) / total_queries if total_queries > 0 else 0.0


def calculate_top1_relevance(judgments: list[Judgment]) -> float:
    """Calculate average relevance score for rank-1 hits."""
    top1 = [judgment for judgment in judgments if judgment.hit_rank == 1]
    return (
        sum(judgment.relevance_score for judgment in top1) / len(top1) if top1 else 0.0
    )


def calculate_stability(
    judgments: list[Judgment], retrieval_results: dict[str, object]
) -> float:
    """Calculate query share whose top-1 hit is relevant among queries with hits."""
    result_rows = retrieval_results.get("results", [])
    if not isinstance(result_rows, list):
        return 0.0
    queries_with_hits = {
        str(row.get("query_id"))
        for row in result_rows
        if isinstance(row, dict) and int(row.get("hit_count") or 0) > 0
    }
    if not queries_with_hits:
        return 0.0
    stable_queries = {
        judgment.query_id
        for judgment in judgments
        if judgment.hit_rank == 1 and judgment.is_relevant
    }
    return len(stable_queries) / len(queries_with_hits)


def assess_level(
    hit_rate: float, top1_relevance: float, stability: float
) -> dict[str, object]:
    """Assess Level using frozen Phase 2/3 thresholds."""
    passed = {
        "hit_rate": hit_rate >= MIN_HIT_RATE,
        "top1_relevance": top1_relevance >= MIN_TOP1_RELEVANCE,
        "stability": stability >= MIN_STABILITY,
    }
    if all(passed.values()):
        level = "Level_4"
        description = "查得稳定好 - all thresholds passing"
    elif passed["hit_rate"]:
        level = "Level_3"
        description = "查得基本对 - hit_rate passing, other thresholds failing"
    else:
        level = "Level_2"
        description = "能查但质量未验证 - retrieval works, quality not verified"

    blocking_factors = []
    metrics = {
        "hit_rate": hit_rate,
        "top1_relevance": top1_relevance,
        "stability": stability,
    }
    thresholds = {
        "hit_rate": MIN_HIT_RATE,
        "top1_relevance": MIN_TOP1_RELEVANCE,
        "stability": MIN_STABILITY,
    }
    for metric, value in metrics.items():
        if not passed[metric]:
            blocking_factors.append(
                f"{metric}: {value:.2%} (need ≥ {thresholds[metric]:.2%})"
            )

    return {
        "level": level,
        "level_description": description,
        "passed_thresholds": passed,
        "blocking_factors": blocking_factors,
    }


def _load_retrieval_results() -> dict[str, object]:
    """Load Phase 8 retrieval results with fail-closed validation."""
    if not RETRIEVAL_FILE.exists():
        raise ValueError("retrieval_results_missing")
    try:
        payload = json.loads(RETRIEVAL_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("retrieval_results_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("retrieval_results_invalid")
    return payload


def _print_metrics_error(reason: str) -> None:
    """Print a sanitized metrics failure reason."""
    print(f"[ERROR] {reason}", file=sys.stderr)


def main() -> int:
    """CLI entry point for Phase 8 metrics calculation."""
    report = load_integrity_report()
    try:
        assert_metrics_allowed(report)
        retrieval_results = _load_retrieval_results()
        judgments = load_completed_judgments(JUDGMENT_FILE)
    except RuntimeError:
        _print_metrics_error(
            "Phase 8 integrity gate has not allowed metric calculation"
        )
        return 2
    except ValueError as exc:
        _print_metrics_error(str(exc))
        return 2

    hit_rate = calculate_hit_rate(judgments, retrieval_results)
    top1_relevance = calculate_top1_relevance(judgments)
    stability = calculate_stability(judgments, retrieval_results)
    thresholds = {
        "hit_rate": MIN_HIT_RATE,
        "top1_relevance": MIN_TOP1_RELEVANCE,
        "stability": MIN_STABILITY,
    }
    metrics = {
        "hit_rate": hit_rate,
        "top1_relevance": top1_relevance,
        "stability": stability,
    }
    quality_payload = {
        "metrics": metrics,
        "thresholds": thresholds,
        "judgment_count": len(judgments),
        "query_count": retrieval_results.get("query_count"),
        "integrity_gate_passed": True,
    }
    assessment = assess_level(hit_rate, top1_relevance, stability)
    level_payload = {
        "assessment_date": datetime.now(UTC).isoformat(),
        "validation_date": retrieval_results.get("validation_date"),
        "version_id": retrieval_results.get("version_id"),
        "query_count": retrieval_results.get("query_count"),
        "judgment_count": len(judgments),
        "metrics": metrics,
        "thresholds": thresholds,
        "level": assessment,
        "baseline_update_allowed": True,
        "source_artifacts": {
            "retrieval_results": str(RETRIEVAL_FILE),
            "judgment_completed": str(JUDGMENT_FILE),
            "validation_integrity_report": str(INTEGRITY_REPORT_FILE),
        },
    }
    METRICS_FILE.write_text(
        json.dumps(quality_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    LEVEL_FILE.write_text(
        json.dumps(level_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(level_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
