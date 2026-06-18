---
phase: 11-07
status: complete
commit: a13d874
date: 2026-06-19
---

# Phase 11 11-07 Implementation Summary

## Goal

Implement systematic hybrid hotspot selector using vector candidates + keyword/BM25 span hits + optional rerank_scores + child distribution scoring. Remove production expected_keywords/forbidden_keywords hardcoding. Preserve rollback paths.

## Implementation

### Files Changed

| File | Changes |
|------|---------|
| `llamaindex_runtime/config.py` | Added `"hybrid_cluster"` to VALID_HOTSPOT_SELECTORS |
| `llamaindex_runtime/tree/semantic_distribution.py` | +311 lines: dataclasses, helpers, selector class, factory |
| `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py` | +459 lines: 23 tests (new file) |

### New Components

1. **KeywordSpanHit** (dataclass) - Keyword/BM25 hit with span-to-node mapping
2. **HotspotSelectionContext** (dataclass) - V2 unified context for hybrid fusion
3. **HybridClusterHotspotSelector** (class) - Generic cross-domain selector
4. **Helper functions**:
   - `_normalize_scores()` - Min-max normalization preserving ranking
   - `_compute_child_distribution_score()` - Multi-child evidence bonus
   - `_compute_fusion_score()` - Weighted sum with optional rerank

### Fusion Weights (Documented)

```
_VECTOR_WEIGHT = 0.40    # Primary semantic similarity
_KEYWORD_WEIGHT = 0.30   # BM25/exact match evidence
_RERANK_WEIGHT = 0.20    # Optional reranker (default-off)
_DISTRIBUTION_WEIGHT = 0.10  # Child-node distribution
```

### Anti-Hardcode Fix

Removed from `_score_cluster`:
- `expected_keywords = ["产品特性对比", "核心DNA", "数据驱动", "非确定性", "持续性"]`
- `forbidden_keywords = ["抖音案例", "05:40", "数据工作重要性", "04:40"]`

### _build_node_stats Enhancement

Added fields:
- `parent_node_id` - Required for distribution scoring lineage
- `level_no` - Required for depth-aware context

## Testing

| Test Suite | Tests | Status |
|------------|-------|--------|
| test_tree_hybrid_hotspot_selector.py | 23 | ✅ passed |
| test_tree_semantic_cluster_hotspot.py | 19 | ✅ passed |
| test_tree_semantic_hotspot.py | - | (merged with cluster) |
| test_tree_semantic_distribution.py | 12 | ✅ passed |
| **Total** | **54** | ✅ |

### Test Categories

- Registration tests (4): hybrid_cluster routes, rollback paths preserved
- Context contract tests (3): vector_candidates, keyword_hits, rerank_scores
- KeywordSpanHit tests (1): required fields
- Normalization tests (3): vector, BM25, empty list
- Distribution scoring tests (3): parent beats isolated, parent_node_id, level_no
- Fusion scoring tests (2): weights documented, sum correctly
- Reranker seam tests (2): works without rerank, no HTTP client
- Anti-hardcode tests (2): no p6 keywords, works with medical domain
- Config tests (3): hybrid_cluster in VALID, default unchanged, invalid raises

## Reviews

| Reviewer | Issues | Status |
|----------|--------|--------|
| python-reviewer | 3 HIGH, 2 MEDIUM | Fixed duplicate code |
| code-reviewer | 2 HIGH, 2 MEDIUM, 1 LOW | Fixed duplicate code |
| security-reviewer | 0 CRITICAL | ✅ pass |

### Fixed Issues

- Removed duplicate code block (lines 1187-1190)
- Type annotations already present on all helpers

## GitNexus Impact

```
Changes: 3 files, 59 symbols
Affected processes: 5
Risk level: medium
```

Key affected symbols: `RuntimeSettings.VALID_HOTSPOT_SELECTORS`, `_build_node_stats`, `_score_cluster`, `get_hotspot_selector`

## Rollback Safety

- `route_subtree` → SubtreeHotspotSelector (Phase 10)
- `cluster` → ClusterHotspotSelector (Phase 11)
- Both selectors unchanged and available via config switch

## Commit

```
a13d874 feat(11-07): add HybridClusterHotspotSelector for generic cross-domain hotspot selection
```

## Next Steps

1. Runtime wiring: Update `_retrieve_tree_hits_from_backend` to build HotspotSelectionContext
2. Validation: Run Phase 11 DNA query validation with hybrid_cluster selector
3. Production switch: Change `rag_tree_hotspot_selector` default after validation