"""
Phase 3 Real Quality Validation: Business Query Dataset

This file defines 15-20 real business queries for PageIndex quality validation.
Queries are designed to test realistic RAG scenarios.

Categories:
1. Structure queries (文档结构理解)
2. Content retrieval (内容检索)
3. Cross-section synthesis (跨章节综合)
4. Entity/relation queries (实体关系查询) - if KG available
5. Edge cases (边界情况)

Phase 3 Requirement: Real LLM-based retrieval + manual relevance judgment
"""

from typing import NamedTuple


class BusinessQuery(NamedTuple):
    """Real business query for quality validation."""
    query_id: str
    query_text: str
    category: str
    expected_answer_type: str  # "single_section", "cross_section", "structure", "entity"
    difficulty: str  # "easy", "medium", "hard"


# ===== Category 1: Structure Queries (文档结构理解) =====

STRUCTURE_QUERIES = [
    BusinessQuery(
        query_id="Q01",
        query_text="文档的主要章节结构是什么？列出所有一级标题。",
        category="structure",
        expected_answer_type="structure",
        difficulty="easy",
    ),
    BusinessQuery(
        query_id="Q02",
        query_text="哪个章节讨论了核心算法原理？",
        category="structure",
        expected_answer_type="single_section",
        difficulty="easy",
    ),
    BusinessQuery(
        query_id="Q03",
        query_text="文档中是否有案例研究章节？如果有，在哪些页？",
        category="structure",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
]


# ===== Category 2: Content Retrieval (内容检索) =====

CONTENT_QUERIES = [
    BusinessQuery(
        query_id="Q04",
        query_text="文档中提到的关键技术指标有哪些？",
        category="content",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q05",
        query_text="如何使用这个系统进行数据处理？",
        category="content",
        expected_answer_type="single_section",
        difficulty="easy",
    ),
    BusinessQuery(
        query_id="Q06",
        query_text="文档中列举了哪些性能优化方法？",
        category="content",
        expected_answer_type="cross_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q07",
        query_text="系统的架构设计原则是什么？",
        category="content",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q08",
        query_text="文档中提到了哪些错误处理机制？",
        category="content",
        expected_answer_type="cross_section",
        difficulty="medium",
    ),
]


# ===== Category 3: Cross-Section Synthesis (跨章节综合) =====

SYNTHESIS_QUERIES = [
    BusinessQuery(
        query_id="Q09",
        query_text="文档中前后章节如何描述数据流程的完整链路？",
        category="synthesis",
        expected_answer_type="cross_section",
        difficulty="hard",
    ),
    BusinessQuery(
        query_id="Q10",
        query_text="系统设计中如何平衡性能和准确性？不同章节的观点是否一致？",
        category="synthesis",
        expected_answer_type="cross_section",
        difficulty="hard",
    ),
    BusinessQuery(
        query_id="Q11",
        query_text="文档中技术方案的选择理由是什么？是否在不同章节有对比分析？",
        category="synthesis",
        expected_answer_type="cross_section",
        difficulty="hard",
    ),
]


# ===== Category 4: Edge Cases (边界情况) =====

EDGE_CASE_QUERIES = [
    BusinessQuery(
        query_id="Q12",
        query_text="文档中是否有未解决的局限性或未来工作部分？",
        category="edge",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q13",
        query_text="如果输入数据格式不符合预期，系统会如何处理？",
        category="edge",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q14",
        query_text="文档中提到了哪些系统限制或约束？",
        category="edge",
        expected_answer_type="cross_section",
        difficulty="medium",
    ),
]


# ===== Category 5: Specific Technical Questions =====

TECHNICAL_QUERIES = [
    BusinessQuery(
        query_id="Q15",
        query_text="文档中描述的向量检索阈值是多少？",
        category="content",
        expected_answer_type="single_section",
        difficulty="easy",
    ),
    BusinessQuery(
        query_id="Q16",
        query_text="树结构构建的深度限制是什么？",
        category="content",
        expected_answer_type="single_section",
        difficulty="easy",
    ),
    BusinessQuery(
        query_id="Q17",
        query_text="文档中提到的 chunking 策略是什么？token 限制是多少？",
        category="content",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
    BusinessQuery(
        query_id="Q18",
        query_text="embedding 模型的选择依据是什么？文档中使用了哪些模型？",
        category="content",
        expected_answer_type="single_section",
        difficulty="medium",
    ),
]


# ===== Category 6: Comparison Queries =====

COMPARISON_QUERIES = [
    BusinessQuery(
        query_id="Q19",
        query_text="文档中对比了哪些技术方案？各自的优缺点是什么？",
        category="synthesis",
        expected_answer_type="cross_section",
        difficulty="hard",
    ),
    BusinessQuery(
        query_id="Q20",
        query_text="文档中是否提到与其他系统的集成方案？如果有，集成方式是什么？",
        category="synthesis",
        expected_answer_type="cross_section",
        difficulty="hard",
    ),
]


# ===== All Queries =====

ALL_BUSINESS_QUERIES = (
    STRUCTURE_QUERIES
    + CONTENT_QUERIES
    + SYNTHESIS_QUERIES
    + EDGE_CASE_QUERIES
    + TECHNICAL_QUERIES
    + COMPARISON_QUERIES
)

# Total: 20 queries


def get_queries_by_category(category: str) -> list[BusinessQuery]:
    """Filter queries by category."""
    return [q for q in ALL_BUSINESS_QUERIES if q.category == category]


def get_queries_by_difficulty(difficulty: str) -> list[BusinessQuery]:
    """Filter queries by difficulty."""
    return [q for q in ALL_BUSINESS_QUERIES if q.difficulty == difficulty]


if __name__ == "__main__":
    print(f"Total business queries: {len(ALL_BUSINESS_QUERIES)}")
    print("\nBy category:")
    for cat in ["structure", "content", "synthesis", "edge", "technical", "comparison"]:
        count = len(get_queries_by_category(cat))
        print(f"  {cat}: {count} queries")
    print("\nBy difficulty:")
    for diff in ["easy", "medium", "hard"]:
        count = len(get_queries_by_difficulty(diff))
        print(f"  {diff}: {count} queries")