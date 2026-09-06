"""
Phase 3 Real Quality Validation: Level Metrics Calculator

This script calculates real quality metrics from manual relevance judgments:
- hit_rate: ≥80% threshold
- top1_relevance: ≥90% threshold
- stability: ≥85% threshold
- Real Level determination: Level 2/3/4

Usage:
    1. User fills judgment_template.csv → saves as judgment_completed.csv
    2. Run: python verification/phase3-real-validation/calculate_metrics.py
    3. Output: level_assessment.json

Phase 3 Requirement: Real Level assessment based on manual human judgment
"""

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from datetime import datetime
from types import ModuleType
from typing import NamedTuple

# Frozen thresholds from Phase 2
MIN_HIT_RATE = 0.80
MIN_TOP1_RELEVANCE = 0.90
MIN_STABILITY = 0.85

PHASE3_DIR = Path(__file__).parent
PHASE5_DIR = PHASE3_DIR.parent / "phase5-evidence-chain-verification"
VALIDATION_GATE_PATH = PHASE5_DIR / "validation_integrity_gate.py"
ACTIVE_VERSION_COUNTS_PATH = PHASE5_DIR / "active_version_counts.json"


def _load_validation_integrity_gate_module() -> ModuleType:
    """Load Phase 5 validation gate from its script path."""
    spec = importlib.util.spec_from_file_location(
        "phase5_validation_integrity_gate",
        VALIDATION_GATE_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {VALIDATION_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_validation_integrity_gate(
    *,
    validation_dir: Path,
    skip_integrity_gate: bool,
) -> dict | None:
    """Run the Phase 5 fail-closed integrity gate before metric calculation."""
    if skip_integrity_gate:
        return None
    if not ACTIVE_VERSION_COUNTS_PATH.exists():
        print(
            "[ERROR] active_version_counts.json missing; run Phase 5 evidence-chain verification first"
        )
        sys.exit(2)

    gate_module = _load_validation_integrity_gate_module()
    report = gate_module.build_validation_integrity_report(
        retrieval_path=validation_dir / "retrieval_results.json",
        judgment_path=validation_dir / "judgment_completed.csv",
        counts_path=ACTIVE_VERSION_COUNTS_PATH,
    )
    if not report.get("passed", False):
        print("[ERROR] Validation integrity gate failed")
        for reason in report.get("blocking_reasons", []):
            print(f"  - {reason}")
        sys.exit(2)
    return report


class Judgment(NamedTuple):
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


def load_completed_judgments(csv_path: Path) -> list[Judgment]:
    """Load manual relevance judgments from CSV."""
    judgments = []

    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse judgment fields
            is_relevant = row['is_relevant'].strip().lower() == 'true'
            relevance_score = float(row['relevance_score'])
            judgment_category = row['judgment_category'].strip()

            judgment = Judgment(
                query_id=row['query_id'],
                hit_rank=int(row['hit_rank']),
                node_id=row['node_id'],
                heading_path=row['heading_path'],
                page_no=int(row['page_no']) if row['page_no'] != 'N/A' else None,
                text_preview=row['text_preview'],
                is_relevant=is_relevant,
                relevance_score=relevance_score,
                judgment_category=judgment_category,
                judgment_notes=row.get('judgment_notes', ''),
            )
            judgments.append(judgment)

    return judgments


def calculate_hit_rate(judgments: list[Judgment], retrieval_results: dict) -> float:
    """Calculate hit_rate: queries with at least 1 relevant hit / total queries."""
    queries_with_results = set(j.query_id for j in judgments)
    total_queries = retrieval_results['query_count']

    # Queries with at least 1 relevant hit
    queries_with_relevant_hits = set()
    for j in judgments:
        if j.is_relevant:
            queries_with_relevant_hits.add(j.query_id)

    hit_rate = len(queries_with_relevant_hits) / total_queries if total_queries > 0 else 0.0
    return hit_rate


def calculate_top1_relevance(judgments: list[Judgment]) -> float:
    """Calculate top1_relevance: avg relevance_score of rank-1 hits."""
    top1_judgments = [j for j in judgments if j.hit_rank == 1]

    if not top1_judgments:
        return 0.0

    avg_relevance = sum(j.relevance_score for j in top1_judgments) / len(top1_judgments)
    return avg_relevance


def calculate_stability(judgments: list[Judgment], retrieval_results: dict) -> float:
    """Calculate stability: queries where top-1 hit is relevant / queries with hits."""
    # Queries with hits (from retrieval results)
    queries_with_hits = set(
        r['query_id'] for r in retrieval_results['results']
        if r['hit_count'] > 0
    )

    if not queries_with_hits:
        return 0.0

    # Queries where top-1 hit is relevant
    queries_with_stable_top1 = set()
    for j in judgments:
        if j.hit_rank == 1 and j.is_relevant:
            queries_with_stable_top1.add(j.query_id)

    stability = len(queries_with_stable_top1) / len(queries_with_hits)
    return stability


def assess_level(hit_rate: float, top1_relevance: float, stability: float) -> dict:
    """Determine Level based on frozen thresholds.

    Level progression (Phase 2 criteria):
    - Level 2: 能查但质量未验证 (retrieval works, quality not verified)
    - Level 3: 查得基本对 (hit_rate passing)
    - Level 4: 查得稳定好 (all thresholds passing)
    """
    thresholds = {
        'hit_rate': MIN_HIT_RATE,
        'top1_relevance': MIN_TOP1_RELEVANCE,
        'stability': MIN_STABILITY,
    }

    results = {
        'hit_rate': hit_rate,
        'top1_relevance': top1_relevance,
        'stability': stability,
    }

    # Check which thresholds pass
    passed = {
        metric: value >= threshold
        for metric, (value, threshold) in zip(
            ['hit_rate', 'top1_relevance', 'stability'],
            [(hit_rate, MIN_HIT_RATE), (top1_relevance, MIN_TOP1_RELEVANCE), (stability, MIN_STABILITY)]
        )
    }

    # Determine Level
    if all(passed.values()):
        level = "Level_4"
        level_description = "查得稳定好 - all thresholds passing"
    elif passed['hit_rate']:
        level = "Level_3"
        level_description = "查得基本对 - hit_rate passing, other thresholds failing"
    else:
        level = "Level_2"
        level_description = "能查但质量未验证 - retrieval works, quality not verified"

    # Identify blocking factors
    blocking_factors = []
    for metric, is_passed in passed.items():
        if not is_passed:
            value = results[metric]
            threshold = thresholds[metric]
            blocking_factors.append(
                f"{metric}: {value:.2%} (need ≥ {threshold:.2%})"
            )

    return {
        'level': level,
        'level_description': level_description,
        'passed_thresholds': passed,
        'blocking_factors': blocking_factors,
    }


def identify_bottlenecks(judgments: list[Judgment], retrieval_results: dict) -> dict:
    """Identify quality bottlenecks: query quality vs tree quality vs evidence chain."""

    # Query quality bottleneck: queries with no relevant hits
    queries_no_relevant = set()
    for j in judgments:
        if not j.is_relevant:
            queries_no_relevant.add(j.query_id)

    # Tree quality bottleneck: from retrieval results (tree_max_level)
    db_stats = None  # Will be loaded from validation_status.json

    # Evidence chain bottleneck: queries with low relevance scores
    low_relevance_judgments = [j for j in judgments if j.relevance_score < 0.5]

    return {
        'query_quality': {
            'queries_with_no_relevant_hits': len(queries_no_relevant),
            'percentage': len(queries_no_relevant) / retrieval_results['query_count'] * 100,
            'affected_queries': sorted(list(queries_no_relevant)),
        },
        'judgment_quality': {
            'low_relevance_count': len(low_relevance_judgments),
            'avg_relevance': sum(j.relevance_score for j in judgments) / len(judgments) if judgments else 0.0,
        },
    }


def main():
    """Calculate real Level metrics from manual judgments."""
    parser = argparse.ArgumentParser(
        description="Calculate real Level metrics from manual judgments."
    )
    parser.add_argument(
        "--skip-integrity-gate",
        action="store_true",
        help="Skip Phase 5 integrity gate for local debugging only.",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Phase 3 Real Quality Validation - Level Metrics Calculator")
    print("=" * 80)

    # Load files
    validation_dir = Path(__file__).parent
    integrity_report = run_validation_integrity_gate(
        validation_dir=validation_dir,
        skip_integrity_gate=args.skip_integrity_gate,
    )

    judgment_file = validation_dir / "judgment_completed.csv"
    if not judgment_file.exists():
        print(f"\n[ERROR] judgment_completed.csv not found")
        print(f"Expected location: {judgment_file}")
        print(f"\nUser action required:")
        print(f"  1. Fill judgment_template.csv manually")
        print(f"  2. Save as judgment_completed.csv")
        print(f"  3. Re-run this script")
        sys.exit(1)

    retrieval_file = validation_dir / "retrieval_results.json"
    if not retrieval_file.exists():
        print(f"\n[ERROR] retrieval_results.json not found")
        print(f"Expected location: {retrieval_file}")
        print(f"\nRun: python verification/phase3-real-validation/run_validation.py")
        sys.exit(1)

    print(f"\nStep 1: Loading manual judgments...")
    judgments = load_completed_judgments(judgment_file)
    print(f"  Loaded: {len(judgments)} judgments")

    print(f"\nStep 2: Loading retrieval results...")
    retrieval_data = json.loads(retrieval_file.read_text(encoding='utf-8'))
    print(f"  Queries: {retrieval_data['query_count']}")
    print(f"  Total hits: {sum(r['hit_count'] for r in retrieval_data['results'])}")

    # Calculate metrics
    print(f"\nStep 3: Calculating quality metrics...")

    hit_rate = calculate_hit_rate(judgments, retrieval_data)
    print(f"  hit_rate: {hit_rate:.2%} (threshold: ≥{MIN_HIT_RATE:.2%})")

    top1_relevance = calculate_top1_relevance(judgments)
    print(f"  top1_relevance: {top1_relevance:.2%} (threshold: ≥{MIN_TOP1_RELEVANCE:.2%})")

    stability = calculate_stability(judgments, retrieval_data)
    print(f"  stability: {stability:.2%} (threshold: ≥{MIN_STABILITY:.2%})")

    # Determine Level
    print(f"\nStep 4: Assessing Level...")
    level_assessment = assess_level(hit_rate, top1_relevance, stability)

    print(f"  Level: {level_assessment['level']}")
    print(f"  Description: {level_assessment['level_description']}")

    if level_assessment['blocking_factors']:
        print(f"  Blocking factors:")
        for factor in level_assessment['blocking_factors']:
            print(f"    - {factor}")
    else:
        print(f"  ✅ All thresholds passed - Level 4 achieved!")

    # Identify bottlenecks
    print(f"\nStep 5: Identifying bottlenecks...")
    bottlenecks = identify_bottlenecks(judgments, retrieval_data)

    print(f"  Query quality:")
    print(f"    Queries with no relevant hits: {bottlenecks['query_quality']['queries_with_no_relevant_hits']}")
    print(f"    Percentage: {bottlenecks['query_quality']['percentage']:.1f}%")

    print(f"  Judgment quality:")
    print(f"    Low relevance (<0.5): {bottlenecks['judgment_quality']['low_relevance_count']}")
    print(f"    Average relevance: {bottlenecks['judgment_quality']['avg_relevance']:.2%}")

    # Save level assessment
    output = {
        'assessment_date': datetime.utcnow().isoformat(),
        'validation_date': retrieval_data['validation_date'],
        'version_id': retrieval_data['version_id'],
        'query_count': retrieval_data['query_count'],
        'judgment_count': len(judgments),
        'metrics': {
            'hit_rate': hit_rate,
            'top1_relevance': top1_relevance,
            'stability': stability,
        },
        'thresholds': {
            'hit_rate': MIN_HIT_RATE,
            'top1_relevance': MIN_TOP1_RELEVANCE,
            'stability': MIN_STABILITY,
        },
        'level': level_assessment,
        'bottlenecks': bottlenecks,
        'integrity_gate_passed': integrity_report is not None,
        'integrity_gate_skipped': args.skip_integrity_gate,
    }

    output_file = validation_dir / "level_assessment.json"
    with output_file.open('w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nStep 6: Saving level assessment...")
    print(f"  Saved to: {output_file}")

    print(f"\n" + "=" * 80)
    print(f"Phase 3 Level Assessment Complete")
    print(f"=" * 80)
    print(f"\nFinal Level: {level_assessment['level']}")
    print(f"\nRecommendation:")

    if level_assessment['level'] == 'Level_4':
        print(f"  ✅ Phase 3 SUCCESS - PageIndex main-function quality verified")
        print(f"  All quality thresholds met, system ready for production use")
    elif level_assessment['level'] == 'Level_3':
        print(f"  ⚠️ Phase 3 PARTIAL - hit_rate passing, other metrics failing")
        print(f"  Focus on improving: top1_relevance, stability")
        print(f"  Bottleneck likely: LLM judgment accuracy or tree structure")
    else:
        print(f"  ❌ Phase 3 FAILED - hit_rate below threshold")
        print(f"  Major bottleneck: query formulation or retrieval logic")
        print(f"  Need to fix: LLM reasoning, tree structure, or evidence chain")


if __name__ == "__main__":
    main()