"""
Phase 3 Real Quality Validation: Manual Relevance Judgment Template

This template defines the structure for manual relevance judgment.
Human evaluators will use this to assess retrieval quality.

Phase 3 Requirement: Manual relevance judgment for top-k hits
"""

from typing import NamedTuple


class RelevanceJudgment(NamedTuple):
    """Manual relevance judgment for a retrieval hit."""
    query_id: str
    hit_rank: int  # 1, 2, 3, ... (top-k)
    node_id: str
    heading_path: str
    page_no: int | None
    text_preview: str

    # Human judgment fields
    is_relevant: bool  # True/False - does this hit answer the query?
    relevance_score: float  # 0.0-1.0 - how well does it answer?
    judgment_notes: str  # Optional notes from evaluator

    # Judgment categories
    judgment_category: str  # "fully_relevant", "partially_relevant", "not_relevant"


# ===== Relevance Judgment Categories =====

RELEVANCE_CATEGORIES = {
    "fully_relevant": {
        "score_range": (0.8, 1.0),
        "description": "Hit directly answers the query with complete information",
    },
    "partially_relevant": {
        "score_range": (0.3, 0.7),
        "description": "Hit contains some relevant information but incomplete",
    },
    "not_relevant": {
        "score_range": (0.0, 0.2),
        "description": "Hit does not answer the query or is completely off-topic",
    },
}


def get_judgment_category_from_score(score: float) -> str:
    """Determine relevance category from score."""
    for category, bounds in RELEVANCE_CATEGORIES.items():
        min_score, max_score = bounds["score_range"]
        if min_score <= score <= max_score:
            return category
    return "not_relevant"


# ===== Judgment CSV Template =====

JUDgment_CSV_TEMPLATE = """query_id,hit_rank,node_id,heading_path,page_no,text_preview,is_relevant,relevance_score,judgment_category,judgment_notes
Q01,1,<node_id>,<heading>,<page>,<preview>,True/False,0.0-1.0,<category>,<notes>
Q01,2,<node_id>,<heading>,<page>,<preview>,True/False,0.0-1.0,<category>,<notes>
...
"""


def format_judgment_row(judgment: RelevanceJudgment) -> str:
    """Format judgment as CSV row."""
    return (
        f"{judgment.query_id},{judgment.hit_rank},{judgment.node_id},"
        f"{judgment.heading_path},{judgment.page_no or 'N/A'},"
        f'"{judgment.text_preview[:100]}...",'  # Truncate preview
        f"{judgment.is_relevant},{judgment.relevance_score:.2f},"
        f"{judgment.judgment_category},{judgment.judgment_notes}"
    )


if __name__ == "__main__":
    print("Relevance Judgment Template")
    print("=" * 80)
    print("\nCategories:")
    for cat, bounds in RELEVANCE_CATEGORIES.items():
        print(f"  {cat}: score {bounds['score_range']}, {bounds['description']}")
    print("\nCSV Template:")
    print(JUDgment_CSV_TEMPLATE)