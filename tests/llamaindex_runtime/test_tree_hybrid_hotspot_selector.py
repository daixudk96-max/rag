"""Tests for Phase 11 11-07 HybridClusterHotspotSelector.

RED phase tests for generic hybrid hotspot selector using:
- Vector candidates
- Keyword/BM25 span hits
- Optional in-memory rerank_scores
- Child distribution scoring

Strategy name: hybrid_cluster (fixed, no aliases)
Rollback paths: route_subtree, cluster (must be preserved)
Anti-hardcode: No expected_keywords/forbidden_keywords in production scoring
"""

from __future__ import annotations

import uuid
import pytest


class TestHybridClusterHotspotSelectorRegistration:
    """Selector registration and strategy name tests."""

    def test_get_hotspot_selector_routes_to_hybrid_cluster_selector(self) -> None:
        """get_hotspot_selector('hybrid_cluster') must return HybridClusterHotspotSelector."""
        # NOTE: HybridClusterHotspotSelector does not exist yet - RED phase
        from llamaindex_runtime.tree.semantic_distribution import (
            get_hotspot_selector,
            HybridClusterHotspotSelector,
        )

        selector = get_hotspot_selector("hybrid_cluster")
        assert isinstance(selector, HybridClusterHotspotSelector)

    def test_get_hotspot_selector_preserves_route_subtree_rollback(self) -> None:
        """route_subtree rollback path must still return SubtreeHotspotSelector."""
        from llamaindex_runtime.tree.semantic_distribution import (
            get_hotspot_selector,
            SubtreeHotspotSelector,
        )

        selector = get_hotspot_selector("route_subtree")
        assert isinstance(selector, SubtreeHotspotSelector)

    def test_get_hotspot_selector_preserves_cluster_rollback(self) -> None:
        """cluster rollback path must still return ClusterHotspotSelector."""
        from llamaindex_runtime.tree.semantic_distribution import (
            get_hotspot_selector,
            ClusterHotspotSelector,
        )

        selector = get_hotspot_selector("cluster")
        assert isinstance(selector, ClusterHotspotSelector)

    def test_invalid_selector_strategy_raises_value_error(self) -> None:
        """Invalid strategy name must raise ValueError with clear message."""
        from llamaindex_runtime.tree.semantic_distribution import get_hotspot_selector

        with pytest.raises(ValueError, match="Unknown hotspot selector strategy"):
            get_hotspot_selector("invalid_strategy")


class TestHotspotSelectionContextContract:
    """V2 selection context dataclass tests."""

    def test_hotspot_selection_context_accepts_vector_candidates(self) -> None:
        """HotspotSelectionContext must accept vector_candidates."""
        # NOTE: HotspotSelectionContext does not exist yet - RED phase
        from llamaindex_runtime.tree.semantic_distribution import (
            HotspotSelectionContext,
            NodeSemanticHit,
        )

        node_id = uuid.uuid4()
        context = HotspotSelectionContext(
            query_text="test query",
            query_embedding=[1.0, 0.0],
            node_stats={},
            tree_signals={},
            vector_candidates=[
                NodeSemanticHit(
                    node_id=node_id,
                    similarity=0.85,
                    heading_path="Test",
                    parent_node_id=None,
                    path_to_root=(node_id,),
                ),
            ],
            keyword_hits=[],
            rerank_scores=None,
        )
        assert context.vector_candidates
        assert context.vector_candidates[0].node_id == node_id

    def test_hotspot_selection_context_accepts_keyword_span_hits(self) -> None:
        """HotspotSelectionContext must accept keyword_hits with span->node mapping."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HotspotSelectionContext,
            KeywordSpanHit,
        )

        span_id = uuid.uuid4()
        node_id = uuid.uuid4()
        context = HotspotSelectionContext(
            query_text="test query",
            query_embedding=[1.0, 0.0],
            node_stats={},
            tree_signals={},
            vector_candidates=[],
            keyword_hits=[
                KeywordSpanHit(
                    span_id=span_id,
                    node_id=node_id,
                    score=0.6,
                    matched_terms=("test", "query"),
                    source="bm25",
                ),
            ],
            rerank_scores=None,
        )
        assert context.keyword_hits
        assert context.keyword_hits[0].node_id == node_id

    def test_hotspot_selection_context_optional_rerank_scores(self) -> None:
        """Context must work when rerank_scores is None (default-off behavior)."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HotspotSelectionContext,
        )

        context = HotspotSelectionContext(
            query_text="test query",
            query_embedding=[1.0, 0.0],
            node_stats={},
            tree_signals={},
            vector_candidates=[],
            keyword_hits=[],
            rerank_scores=None,
        )
        assert context.rerank_scores is None


class TestKeywordSpanHitContract:
    """KeywordSpanHit dataclass tests."""

    def test_keyword_span_hit_has_required_fields(self) -> None:
        """KeywordSpanHit must have span_id, node_id, score, matched_terms, source."""
        from llamaindex_runtime.tree.semantic_distribution import KeywordSpanHit

        span_id = uuid.uuid4()
        node_id = uuid.uuid4()
        hit = KeywordSpanHit(
            span_id=span_id,
            node_id=node_id,
            score=0.75,
            matched_terms=("keyword", "search"),
            source="bm25",
        )
        assert hit.span_id == span_id
        assert hit.node_id == node_id
        assert hit.score == 0.75
        assert hit.matched_terms == ("keyword", "search")
        assert hit.source == "bm25"


class TestScoreNormalization:
    """Score normalization tests for vector/keyword/rerank fusion."""

    def test_normalize_vector_scores_to_comparable_scale(self) -> None:
        """Vector scores must be normalized to [0.0, 1.0]."""
        # NOTE: normalization helper does not exist yet - RED phase
        from llamaindex_runtime.tree.semantic_distribution import _normalize_scores

        raw_scores = [0.99, 0.85, 0.70]
        normalized = _normalize_scores(raw_scores)
        assert all(0.0 <= s <= 1.0 for s in normalized)
        # Normalization preserves ranking
        assert normalized[0] > normalized[1] > normalized[2]

    def test_normalize_bm25_scores_to_comparable_scale(self) -> None:
        """BM25 scores [0-20+] must be normalized to [0.0, 1.0]."""
        from llamaindex_runtime.tree.semantic_distribution import _normalize_scores

        bm25_raw_scores = [15.3, 8.2, 3.1, 0.0]
        normalized = _normalize_scores(bm25_raw_scores)
        assert all(0.0 <= s <= 1.0 for s in normalized)
        assert normalized[0] > normalized[1] > normalized[2] > normalized[3]

    def test_normalize_empty_scores_returns_empty(self) -> None:
        """Empty score list must return empty normalized list."""
        from llamaindex_runtime.tree.semantic_distribution import _normalize_scores

        normalized = _normalize_scores([])
        assert normalized == []


class TestChildDistributionScoring:
    """Child-node hit distribution scoring tests."""

    def test_parent_with_multiple_child_hits_beats_isolated_high_score_node(
        self,
    ) -> None:
        """Distribution scoring must reward multi-child evidence over isolated high score."""
        # NOTE: distribution scoring helper does not exist yet - RED phase
        from llamaindex_runtime.tree.semantic_distribution import (
            _compute_child_distribution_score,
        )

        # Parent A: 3 children with moderate scores
        parent_a_id = uuid.uuid4()
        node_stats = {
            parent_a_id: {
                "node_id": parent_a_id,
                "parent_node_id": None,
                "level_no": 0,
            },
        }
        # Child hits under parent A
        child_hits = [
            {"node_id": uuid.uuid4(), "parent_node_id": parent_a_id, "score": 0.75},
            {"node_id": uuid.uuid4(), "parent_node_id": parent_a_id, "score": 0.70},
            {"node_id": uuid.uuid4(), "parent_node_id": parent_a_id, "score": 0.65},
        ]
        # Isolated node B with high score
        isolated_node_id = uuid.uuid4()
        isolated_hit = {
            "node_id": isolated_node_id,
            "parent_node_id": None,
            "score": 0.90,
        }

        # Compute distribution scores
        parent_a_dist = _compute_child_distribution_score(
            target_node_id=parent_a_id,
            hits=child_hits + [isolated_hit],
            node_stats=node_stats,
        )
        isolated_dist = _compute_child_distribution_score(
            target_node_id=isolated_node_id,
            hits=child_hits + [isolated_hit],
            node_stats=node_stats,
        )

        # Parent with distributed child hits should beat isolated high-score node
        assert parent_a_dist > isolated_dist

    def test_node_stats_requires_parent_node_id_for_distribution(self) -> None:
        """node_stats must include parent_node_id for distribution scoring."""
        # This test validates existing _build_node_stats output contract
        # We check that parent_node_id is already present or will be added
        from llamaindex_runtime.tree.semantic_distribution import _build_node_stats

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        tree_nodes = [
            {"node_id": root_id, "heading_path": "Root", "parent_node_id": None},
            {
                "node_id": child_id,
                "heading_path": "Root > Child",
                "parent_node_id": root_id,
            },
        ]
        # Mock minimal vectors
        node_to_vectors = {child_id: [[1.0, 0.0]]}
        node_to_span_ids = {child_id: [uuid.uuid4()]}
        node_to_chunk_ids = {child_id: [uuid.uuid4()]}

        stats = _build_node_stats(
            tree_nodes=tree_nodes,
            node_to_span_ids=node_to_span_ids,
            node_to_vectors=node_to_vectors,
            node_to_chunk_ids=node_to_chunk_ids,
        )

        # All node_stats entries must have parent_node_id field
        for entry in stats:
            assert "parent_node_id" in entry

    def test_node_stats_requires_level_no_for_depth_context(self) -> None:
        """node_stats must include level_no for depth-aware scoring."""
        from llamaindex_runtime.tree.semantic_distribution import _build_node_stats

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        tree_nodes = [
            {
                "node_id": root_id,
                "heading_path": "Root",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_id,
                "heading_path": "Root > Child",
                "level_no": 1,
                "parent_node_id": root_id,
            },
        ]
        node_to_vectors = {child_id: [[1.0, 0.0]]}
        node_to_span_ids = {child_id: [uuid.uuid4()]}
        node_to_chunk_ids = {child_id: [uuid.uuid4()]}

        stats = _build_node_stats(
            tree_nodes=tree_nodes,
            node_to_span_ids=node_to_span_ids,
            node_to_vectors=node_to_vectors,
            node_to_chunk_ids=node_to_chunk_ids,
        )

        for entry in stats:
            assert "level_no" in entry


class TestHybridFusionScoring:
    """Vector + keyword + rerank fusion scoring tests."""

    def test_fusion_weights_are_documented_not_magic(self) -> None:
        """HybridClusterHotspotSelector must have named weight constants."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
        )

        selector = HybridClusterHotspotSelector()
        # Weight constants must exist and be documented
        assert hasattr(selector, "_VECTOR_WEIGHT") or hasattr(selector, "VECTOR_WEIGHT")
        assert hasattr(selector, "_KEYWORD_WEIGHT") or hasattr(
            selector, "KEYWORD_WEIGHT"
        )
        # Optional rerank weight (default 0 when rerank_scores is None)
        assert (
            hasattr(selector, "_RERANK_WEIGHT")
            or hasattr(selector, "RERANK_WEIGHT")
            or hasattr(selector, "_DISTRIBUTION_WEIGHT")
        )

    def test_fusion_scores_sum_correctly(self) -> None:
        """Fusion score must correctly weight normalized components."""
        # NOTE: fusion helper does not exist yet - RED phase
        from llamaindex_runtime.tree.semantic_distribution import _compute_fusion_score

        vector_score = 0.85
        keyword_score = 0.6
        rerank_score = 0.7
        distribution_score = 0.5

        fusion = _compute_fusion_score(
            vector_score=vector_score,
            keyword_score=keyword_score,
            rerank_score=rerank_score,
            distribution_score=distribution_score,
            vector_weight=0.40,
            keyword_weight=0.30,
            rerank_weight=0.20,
            distribution_weight=0.10,
        )

        # Fusion must be weighted sum
        expected = 0.40 * 0.85 + 0.30 * 0.6 + 0.20 * 0.7 + 0.10 * 0.5
        assert abs(fusion - expected) < 0.001

    def test_selector_prefers_multi_term_heading_match_over_broad_single_term(
        self,
    ) -> None:
        """Multi-term heading matches must beat broad one-term heading matches."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
            HotspotSelectionContext,
            KeywordSpanHit,
            NodeSemanticHit,
        )

        strong_heading_id = uuid.uuid4()
        broad_heading_id = uuid.uuid4()
        baseline_id = uuid.uuid4()
        selector = HybridClusterHotspotSelector()
        context = HotspotSelectionContext(
            query_text="AI产品经理的核心DNA是什么？",
            query_embedding=[1.0, 0.0],
            node_stats={
                strong_heading_id: {
                    "node_id": strong_heading_id,
                    "heading_path": "Root > 产品特性对比 > AI产品经理核心DNA",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
                broad_heading_id: {
                    "node_id": broad_heading_id,
                    "heading_path": "Root > 抖音案例 > AI产品经理的思考方向",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
                baseline_id: {
                    "node_id": baseline_id,
                    "heading_path": "Root > Generic",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
            },
            tree_signals={"embedding_dimension": 2},
            vector_candidates=[
                NodeSemanticHit(
                    node_id=strong_heading_id,
                    similarity=0.70,
                    heading_path="Root > 产品特性对比 > AI产品经理核心DNA",
                    parent_node_id=None,
                    path_to_root=(strong_heading_id,),
                ),
                NodeSemanticHit(
                    node_id=broad_heading_id,
                    similarity=0.90,
                    heading_path="Root > 抖音案例 > AI产品经理的思考方向",
                    parent_node_id=None,
                    path_to_root=(broad_heading_id,),
                ),
                NodeSemanticHit(
                    node_id=baseline_id,
                    similarity=0.40,
                    heading_path="Root > Generic",
                    parent_node_id=None,
                    path_to_root=(baseline_id,),
                ),
            ],
            keyword_hits=[
                KeywordSpanHit(
                    span_id=uuid.uuid4(),
                    node_id=strong_heading_id,
                    score=0.6,
                    matched_terms=("AI产品经理", "核心DNA"),
                    source="heading_keyword_match",
                ),
                KeywordSpanHit(
                    span_id=uuid.uuid4(),
                    node_id=broad_heading_id,
                    score=0.6,
                    matched_terms=("AI产品经理",),
                    source="heading_keyword_match",
                ),
            ],
            rerank_scores=None,
        )

        hotspots = selector.select_hotspots(context=context, limit=1)

        assert hotspots[0].node_id == strong_heading_id

    def test_selector_prioritizes_exact_heading_match_over_high_vector_broad_match(
        self,
    ) -> None:
        """Full term coverage in a heading is stronger than a broad one-term vector hit."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
            HotspotSelectionContext,
            KeywordSpanHit,
            NodeSemanticHit,
        )

        exact_heading_id = uuid.uuid4()
        broad_heading_id = uuid.uuid4()
        baseline_id = uuid.uuid4()
        selector = HybridClusterHotspotSelector()
        context = HotspotSelectionContext(
            query_text="AI产品经理的核心DNA是什么？",
            query_embedding=[1.0, 0.0],
            node_stats={
                exact_heading_id: {
                    "node_id": exact_heading_id,
                    "heading_path": "Root > 产品特性对比 > AI产品经理核心DNA",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
                broad_heading_id: {
                    "node_id": broad_heading_id,
                    "heading_path": "Root > 抖音案例 > AI产品经理的思考方向",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
                baseline_id: {
                    "node_id": baseline_id,
                    "heading_path": "Root > Generic",
                    "parent_node_id": None,
                    "level_no": 2,
                    "support_count": 1,
                },
            },
            tree_signals={"embedding_dimension": 2},
            vector_candidates=[
                NodeSemanticHit(
                    node_id=exact_heading_id,
                    similarity=0.10,
                    heading_path="Root > 产品特性对比 > AI产品经理核心DNA",
                    parent_node_id=None,
                    path_to_root=(exact_heading_id,),
                ),
                NodeSemanticHit(
                    node_id=broad_heading_id,
                    similarity=0.99,
                    heading_path="Root > 抖音案例 > AI产品经理的思考方向",
                    parent_node_id=None,
                    path_to_root=(broad_heading_id,),
                ),
                NodeSemanticHit(
                    node_id=baseline_id,
                    similarity=0.01,
                    heading_path="Root > Generic",
                    parent_node_id=None,
                    path_to_root=(baseline_id,),
                ),
            ],
            keyword_hits=[
                KeywordSpanHit(
                    span_id=uuid.uuid4(),
                    node_id=exact_heading_id,
                    score=0.6,
                    matched_terms=("AI产品经理", "核心DNA"),
                    source="heading_keyword_match",
                ),
                KeywordSpanHit(
                    span_id=uuid.uuid4(),
                    node_id=broad_heading_id,
                    score=0.6,
                    matched_terms=("AI产品经理",),
                    source="heading_keyword_match",
                ),
            ],
            rerank_scores=None,
        )

        hotspots = selector.select_hotspots(context=context, limit=1)

        assert hotspots[0].node_id == exact_heading_id


class TestDefaultOffRerankerSeam:
    """Reranker seam default-off tests."""

    def test_selector_works_without_rerank_scores(self) -> None:
        """HybridClusterHotspotSelector must work when rerank_scores is None."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
            HotspotSelectionContext,
        )

        selector = HybridClusterHotspotSelector()
        node_id = uuid.uuid4()
        context = HotspotSelectionContext(
            query_text="test",
            query_embedding=[1.0, 0.0],
            node_stats={
                node_id: {
                    "node_id": node_id,
                    "centroid": [1.0, 0.0],
                    "prototype_embedding": [1.0, 0.0],
                    "support_count": 1,
                    "parent_node_id": None,
                    "level_no": 0,
                },
            },
            tree_signals={"embedding_dimension": 2},
            vector_candidates=[],
            keyword_hits=[],
            rerank_scores=None,
        )

        # Must not raise error when rerank_scores is None
        hotspots = selector.select_hotspots(context=context, limit=1)
        assert isinstance(hotspots, list)

    def test_no_external_rerank_service_required(self) -> None:
        """Selector must not have HTTP client or external rerank calls."""
        import inspect
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
        )

        # Check class source does not contain HTTP client imports
        source = inspect.getsource(HybridClusterHotspotSelector)
        forbidden_patterns = ["requests.", "httpx.", "urllib.", "aiohttp."]
        for pattern in forbidden_patterns:
            assert (
                pattern not in source
            ), f"HybridClusterHotspotSelector must not use {pattern}"


class TestCrossDomainAntiHardcode:
    """Cross-domain anti-hardcode validation tests."""

    def test_selector_no_p6_specific_keyword_constants(self) -> None:
        """HybridClusterHotspotSelector must not have p6-specific keyword constants."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
        )

        selector = HybridClusterHotspotSelector()
        forbidden_attrs = [
            "_DNA_KEYWORDS",
            "_PRODUCT_KEYWORDS",
            "_DNA_EVIDENCE_TERMS",
            "_P6_KEYWORDS",
            "DNA_TERMS",
            "PRODUCT_MANAGER_KEYWORDS",
        ]
        for attr in forbidden_attrs:
            assert not hasattr(selector, attr), f"Selector must not have {attr}"

    def test_selector_works_with_non_p6_domain(self) -> None:
        """Selector must work with generic medical/legal/tech domain."""
        from llamaindex_runtime.tree.semantic_distribution import (
            HybridClusterHotspotSelector,
            HotspotSelectionContext,
        )

        selector = HybridClusterHotspotSelector()
        # Medical domain tree (no p6 terms anywhere)
        node_id = uuid.uuid4()
        context = HotspotSelectionContext(
            query_text="cardiac arrhythmia diagnosis",
            query_embedding=[0.5, 0.5],
            node_stats={
                node_id: {
                    "node_id": node_id,
                    "heading_path": "Medical > Cardiology > Arrhythmia",
                    "centroid": [0.5, 0.5],
                    "prototype_embedding": [0.5, 0.5],
                    "support_count": 2,
                    "parent_node_id": None,
                    "level_no": 0,
                },
            },
            tree_signals={"embedding_dimension": 2},
            vector_candidates=[],
            keyword_hits=[],
            rerank_scores=None,
        )

        hotspots = selector.select_hotspots(context=context, limit=1)
        # Must return hotspots without requiring p6 terms
        assert isinstance(hotspots, list)


class TestHybridRuntimeKeywordExtraction:
    """Runtime keyword extraction tests for general jieba heading matching."""

    def test_extract_keywords_splits_mixed_cjk_latin_query(self) -> None:
        """CJK/Latin terms use jieba built-in general dictionary only."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("AI产品经理的核心DNA是什么？")

        assert "AI" in keywords
        assert "产品" in keywords
        assert "经理" in keywords
        assert "核心" in keywords
        assert "DNA" in keywords
        assert "AI产品经理" not in keywords
        assert "核心DNA" not in keywords
        assert "AI产品经理的核心DNA是什么" not in keywords

    def test_extract_keywords_match_expected_dna_heading(self) -> None:
        """Extracted Q01 jieba tokens must match the DNA heading path."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        heading_path = (
            "AI产品经理项目实战与深度思考架构分析 > "
            "00:31 - 产品特性对比 > AI产品经理核心DNA"
        )
        keywords = _extract_keywords_from_query("AI产品经理的核心DNA是什么？")
        matched_keywords = [
            kw for kw in keywords if kw.lower() in heading_path.lower()
        ]

        assert matched_keywords == ["AI", "产品", "经理", "核心", "DNA"]

    def test_extract_keywords_splits_glued_why_query(self) -> None:
        """为什么-query terms must not collapse into one glued token."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("为什么数据对AI产品如此重要？")

        assert "数据" in keywords
        assert "AI" in keywords
        assert "产品" in keywords
        assert "重要" in keywords
        assert "数据对AI产品如此重要" not in keywords
        assert "为什么数据对AI产品如此重要" not in keywords

    def test_extract_keywords_handles_pure_latin_unchanged(self) -> None:
        """Pure Latin query terms must keep existing token behavior."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("cardiac arrhythmia diagnosis")

        assert keywords == ["cardiac", "arrhythmia", "diagnosis"]

    def test_extract_keywords_uses_jieba_builtin_general_dictionary_only(self) -> None:
        """Generic CJK compounds must split without a custom user dictionary."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("什么是供应链飞轮？")

        assert "供应链" in keywords
        assert "飞轮" in keywords
        assert "供应链飞轮" not in keywords

    def test_extract_keywords_handles_empty_or_invalid_query(self) -> None:
        """Malformed empty query input must fail closed to no keywords."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        assert _extract_keywords_from_query("") == []
        assert _extract_keywords_from_query("   ") == []
        assert _extract_keywords_from_query(None) == []  # type: ignore[arg-type]

    def test_extract_keywords_filters_control_characters(self) -> None:
        """Control and zero-width characters must not survive as keyword text."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("数据​飞轮\x00重要")
        joined_keywords = "".join(keywords)

        assert "​" not in joined_keywords
        assert "\x00" not in joined_keywords
        assert "数据" in keywords
        assert "飞轮" in keywords
        assert "重要" in keywords

    def test_extract_keywords_bounds_extremely_long_query(self) -> None:
        """Very long query text must be bounded before jieba segmentation."""
        from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

        keywords = _extract_keywords_from_query("数据" * 5000)

        assert keywords == ["数据"]


class TestConfigRegistration:
    """RuntimeSettings config registration tests."""

    def test_valid_hotspot_selectors_includes_hybrid_cluster(self) -> None:
        """VALID_HOTSPOT_SELECTORS must include hybrid_cluster."""
        from llamaindex_runtime.config import RuntimeSettings

        assert "hybrid_cluster" in RuntimeSettings.VALID_HOTSPOT_SELECTORS

    def test_rag_tree_hotspot_selector_default_is_route_subtree(self) -> None:
        """Default selector must remain route_subtree for rollback safety."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(database_url="postgresql://test")
        assert settings.rag_tree_hotspot_selector == "route_subtree"

    def test_invalid_selector_in_runtime_settings_raises(self) -> None:
        """RuntimeSettings must reject invalid selector strategy."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="Unsupported hotspot selector"):
            RuntimeSettings(
                database_url="postgresql://test",
                rag_tree_hotspot_selector="invalid_strategy",
            )
