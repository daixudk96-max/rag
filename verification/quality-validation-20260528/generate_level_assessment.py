"""Phase 2 level assessment generator.

Consumes prior validation artifacts (query quality, tree diagnosis,
evidence chain) and produces final readiness decision.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path("verification/quality-validation-20260528")

LEVEL_2 = "Level_2"
LEVEL_3 = "Level_3"
LEVEL_4 = "Level_4"

THRESHOLDS = {
    "hit_rate": 0.80,
    "top1_relevance": 0.90,
    "stability": 0.85,
    "tree_depth": 3,
    "node_chunk_mapping_rate": 0.80,
    "heading_path_completeness": 0.95,
    "min_test_queries": 10,
}


def load_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load the three prior validation artifacts."""
    query_report = json.loads(
        (ARTIFACT_DIR / "query_quality_report.json").read_text(encoding="utf-8")
    )
    tree_report = json.loads(
        (ARTIFACT_DIR / "tree_structure_diagnosis.json").read_text(encoding="utf-8")
    )
    evidence_report = json.loads(
        (ARTIFACT_DIR / "evidence_chain_report.json").read_text(encoding="utf-8")
    )
    return query_report, tree_report, evidence_report


def assess_level(
    query_quality: dict[str, Any],
    tree_diagnosis: dict[str, Any],
    evidence_chain: dict[str, Any],
) -> dict[str, Any]:
    """Assess readiness level from measured artifact outputs.

    Rules:
    - Level 4 requires ALL thresholds to pass.
    - Level 3 requires query quality basically passing but may have gaps.
    - Level 2 is the default when quality is unverified.
    """
    blocking: list[str] = []
    passing: list[str] = []

    # Query quality checks
    metrics = query_quality.get("metrics", {})
    hit_rate = metrics.get("hit_rate", 0.0)
    if hit_rate >= THRESHOLDS["hit_rate"]:
        passing.append(f"hit_rate: {hit_rate:.2%}")
    else:
        blocking.append(f"hit_rate: {hit_rate:.2%} (need >= {THRESHOLDS['hit_rate']:.2%})")

    top1 = metrics.get("top1_relevance", 0.0)
    if top1 >= THRESHOLDS["top1_relevance"]:
        passing.append(f"top1_relevance: {top1:.2%}")
    else:
        blocking.append(f"top1_relevance: {top1:.2%} (need >= {THRESHOLDS['top1_relevance']:.2%})")

    stability = metrics.get("stability", 0.0)
    if stability >= THRESHOLDS["stability"]:
        passing.append(f"stability: {stability:.2%}")
    else:
        blocking.append(f"stability: {stability:.2%} (need >= {THRESHOLDS['stability']:.2%})")

    test_count = metrics.get("test_count", 0)
    if test_count >= THRESHOLDS["min_test_queries"]:
        passing.append(f"test_count: {test_count}")
    else:
        blocking.append(f"test_count: {test_count} (need >= {THRESHOLDS['min_test_queries']})")

    # Tree quality checks
    tree_depth = tree_diagnosis.get("evidence", {}).get("flat_max_level", 0)
    if tree_depth >= THRESHOLDS["tree_depth"]:
        passing.append(f"tree_depth: {tree_depth}")
    else:
        blocking.append(f"tree_depth: {tree_depth} (need >= {THRESHOLDS['tree_depth']})")

    # Evidence chain checks
    mapping_rate = evidence_chain.get("node_chunk_mapping", {}).get("rate", 0.0)
    if mapping_rate >= THRESHOLDS["node_chunk_mapping_rate"]:
        passing.append(f"node_chunk_mapping: {mapping_rate:.2%}")
    else:
        blocking.append(f"node_chunk_mapping: {mapping_rate:.2%} (need >= {THRESHOLDS['node_chunk_mapping_rate']:.2%})")

    heading_rate = evidence_chain.get("heading_path_completeness", {}).get("rate", 0.0)
    if heading_rate >= THRESHOLDS["heading_path_completeness"]:
        passing.append(f"heading_path: {heading_rate:.2%}")
    else:
        blocking.append(f"heading_path: {heading_rate:.2%} (need >= {THRESHOLDS['heading_path_completeness']:.2%})")

    # Level determination: strict rules
    if not blocking:
        level = LEVEL_4
    elif hit_rate >= THRESHOLDS["hit_rate"]:
        level = LEVEL_3
    else:
        level = LEVEL_2

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "level_meaning": {
            LEVEL_2: "Technically connected, quality unverified (能查但质量未验证)",
            LEVEL_3: "Query quality basically correct but not stable enough (查得基本对)",
            LEVEL_4: "All thresholds pass, ready for closeout (查得稳定好)",
        }.get(level, ""),
        "blocking_factors": blocking,
        "passing_factors": passing,
        "thresholds": THRESHOLDS,
        "sources": {
            "query_quality": query_quality.get("timestamp", ""),
            "tree_diagnosis": tree_diagnosis.get("timestamp", ""),
            "evidence_chain": evidence_chain.get("timestamp", ""),
        },
    }


def write_level_assessment(assessment: dict[str, Any]) -> None:
    """Write level assessment artifact."""
    (ARTIFACT_DIR / "level_assessment.json").write_text(
        json.dumps(assessment, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def main() -> None:
    """Generate level assessment from prior artifacts."""
    query_quality, tree_diagnosis, evidence_chain = load_artifacts()
    assessment = assess_level(query_quality, tree_diagnosis, evidence_chain)
    write_level_assessment(assessment)
    print(f"Level assessment written to {ARTIFACT_DIR / 'level_assessment.json'}")
    print(f"Level: {assessment['level']}")
    print(f"Meaning: {assessment['level_meaning']}")
    if assessment["blocking_factors"]:
        print("Blocking factors:")
        for f in assessment["blocking_factors"]:
            print(f"  - {f}")
    if assessment["passing_factors"]:
        print("Passing factors:")
        for f in assessment["passing_factors"]:
            print(f"  - {f}")


if __name__ == "__main__":
    main()