"""
Phase 3 Quick Start Guide - For User Manual Judgment

This script helps user understand how to fill judgment_template.csv quickly.
"""

from pathlib import Path

print("=" * 80)
print("Phase 3 Manual Judgment Quick Start Guide")
print("=" * 80)

template_file = Path("verification/phase3-real-validation/judgment_template.csv")
print(f"\nTemplate file location: {template_file}")
print(f"Total hits to judge: 28")

print(f"\nJudgment CSV columns:")
print(f"  - query_id: Query identifier (Q01-Q20)")
print(f"  - hit_rank: Hit rank (1, 2, 3, ...)")
print(f"  - node_id: Retrieved node UUID")
print(f"  - heading_path: Node heading path")
print(f"  - page_no: Page number")
print(f"  - text_preview: Text preview (100 chars)")
print(f"  - is_relevant: YOUR JUDGMENT - True/False")
print(f"  - relevance_score: YOUR JUDGMENT - 0.0-1.0")
print(f"  - judgment_category: YOUR JUDGMENT - fully_relevant/partially_relevant/not_relevant")
print(f"  - judgment_notes: YOUR NOTES - optional")

print(f"\nJudgment categories:")
print(f"  - fully_relevant (0.8-1.0): Hit directly answers the query")
print(f"  - partially_relevant (0.3-0.7): Hit contains some relevant information")
print(f"  - not_relevant (0.0-0.2): Hit does not answer the query")

print(f"\nExample judgment:")
print(f"  For query Q01: '文档的主要章节结构是什么？'")
print(f"  Hit: heading_path='第二阶段-竞品分析-代旭'")
print(f"  Judgment:")
print(f"    - is_relevant: True (contains document structure info)")
print(f"    - relevance_score: 0.7 (partially answers, but incomplete)")
print(f"    - judgment_category: partially_relevant")
print(f"    - judgment_notes: 'Shows one section, but not full structure'")

print(f"\nQuick workflow:")
print(f"  1. Open: verification/phase3-real-validation/judgment_template.csv")
print(f"  2. Read each hit's query_text (from retrieval_results.json)")
print(f"  3. Judge: is_relevant, relevance_score, judgment_category")
print(f"  4. Save: verification/phase3-real-validation/judgment_completed.csv")
print(f"  5. Run: python verification/phase3-real-validation/calculate_metrics.py")

print(f"\nTips for fast judgment:")
print(f"  - Focus on heading_path first (does it match query intent?)")
print(f"  - Check text_preview if heading_path unclear")
print(f"  - Don't overthink - quick judgment is OK")
print(f"  - Trust your intuition - human judgment is the goal")

print(f"\nEstimated time:")
print(f"  - 28 hits × 1-2 minutes/hit = 30-60 minutes total")

print(f"\nAfter judgment:")
print(f"  Run calculate_metrics.py to get:")
print(f"    - Real Level (Level 2/3/4)")
print(f"    - Quality metrics (hit_rate, top1_relevance, stability)")
print(f"    - Bottleneck analysis")

print(f"\n" + "=" * 80)
print(f"Ready to start? Open judgment_template.csv now!")
print(f"=" * 80)