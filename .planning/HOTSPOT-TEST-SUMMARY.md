# Tree Semantic Retrieval Hotspot Behavior Tests

## Test File
`tests/llamaindex_runtime/test_tree_semantic_hotspot.py`

## Purpose
Minimal pytest tests documenting expected hotspot behavior for tree semantic retrieval.

## Test Results
- **4 PASSED**: Document current behavior and gaps
- **3 SKIPPED**: Document future features not yet implemented

## Tests by Category

### 1. SubtreeHotspotSelector (SKIPPED - not implemented)
**Test**: `test_selector_returns_parent_when_child_has_evidence`

**Expected Behavior**: Hotspot selector should identify parent node as hotspot when descendant has evidence in subtree.

**Status**: `SubtreeHotspotSelector` class does not exist. Test documents expected semantic aggregation behavior.

---

### 2. RecursiveTreeTraversalRunner.start_node_id (SKIPPED - not implemented)
**Test**: `test_start_node_id_limits_traversal_scope`

**Expected Behavior**: Traversal should accept `start_node_id` parameter to begin from specific subtree (hotspot drill-down).

**Status**: Parameter not in current signature. Test documents subtree-scoped traversal requirement.

---

### 3. Hotspot Drill-Down with Evidence (PASSED - documents current behavior gap)
**Test**: `test_parent_without_stats_drills_to_child_with_evidence`

**Expected Behavior**: Parent without chunks but with children evidence should aggregate stats and trigger drill_down.

**Current Behavior**: Parent nodes without chunks are filtered out in `_build_node_stats` (line 208-209), preventing hotspot navigation.

**Gap**: Semantic aggregation missing - parent should aggregate children stats for hotspot selection.

---

### 4. Hotspot Drill-Down Working Case (PASSED - current behavior)
**Test**: `test_parent_with_chunks_and_dispersion_drills_to_children`

**Current Behavior**: Parent node WITH dispersed chunks triggers drill_down correctly.

**Validates**: Existing traversal works when parent has evidence. This is baseline working behavior.

---

### 5. Runtime Hotspot Metadata (SKIPPED - not implemented)
**Test**: `test_runtime_preserves_hotspot_provenance_in_hit_metadata`

**Expected Behavior**: `QueryHit` should include hotspot metadata fields (hotspot_node_id, drill_depth).

**Status**: `QueryHit` is frozen dataclass without hotspot fields. Test documents metadata preservation requirement.

---

### 6. Evidence-Bearing Final Hits (PASSED - documents current behavior gap)
**Test**: `test_final_hits_contain_actual_chunk_evidence`

**Expected Behavior**: Hotspot navigation should produce hits from evidence-bearing children.

**Current Behavior**: Waypoint parent without chunks blocks traversal, no hits produced.

**Gap**: Parent aggregation needed to guide descent to evidence children.

---

### 7. Hotspot Integration Flow (PASSED - documents current behavior gap)
**Test**: `test_full_hotspot_flow_selects_parent_then_drills`

**Expected Behavior**: Complete flow:
1. Parent aggregates children stats (hotspot)
2. Policy decides drill_down (high dispersion)
3. Traversal descends to children
4. Runtime maps hits

**Current Behavior**: Parent filtered out, no hits.

**Gap**: Integration test documenting complete hotspot navigation requirement.

---

## Implementation Gaps

### Gap 1: Parent Node Aggregation
**Location**: `llamaindex_runtime/tree/semantic_distribution.py::_build_node_stats` (line 208-209)

**Issue**: Nodes without vectors/chunks are skipped.

**Fix Required**: Aggregate children stats for parent nodes without direct chunks. Enable "route-only parents" that guide navigation.

### Gap 2: SubtreeHotspotSelector
**Missing Class**: Need semantic aggregation logic to select parent hotspot from descendant evidence.

### Gap 3: start_node_id Parameter
**Missing Parameter**: `RecursiveTreeTraversalRunner.traverse_tree_for_query` needs `start_node_id` for subtree-scoped traversal.

### Gap 4: Hotspot Metadata
**Missing Fields**: `QueryHit` needs hotspot provenance fields:
- `hotspot_node_id`: Parent hotspot that guided navigation
- `drill_depth`: How many levels descended from hotspot

---

## Minimal Test Design

Tests follow TDD principles:
1. **Document expected behavior** (skipped tests for missing features)
2. **Validate current working behavior** (passing tests for existing functionality)
3. **Expose gaps without changing production code** (assert on current behavior)
4. **Minimal diffs** (no changes to production code)

## Running Tests

```bash
python -m pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -v
```

**Expected**: 4 passed, 3 skipped

---

## Next Steps (Implementation Phase)

1. Implement `_build_node_stats` aggregation for parents without chunks
2. Add `SubtreeHotspotSelector` class
3. Add `start_node_id` parameter to traversal runner
4. Add hotspot metadata fields to `QueryHit`
5. Update runtime mapping to preserve hotspot provenance

Tests will guide implementation validation.