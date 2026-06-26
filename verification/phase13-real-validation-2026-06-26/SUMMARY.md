# Phase 13 Real Validation Summary — Q18 Chunk Evidence Fix

**Date:** 2026-06-26
**Validation directory:** `verification/phase13-real-validation-2026-06-26/`
**Baseline directory:** `verification/real-document-validation-2026-06-23/`
**Target issue:** Q18 returned `chunk_id=null` empty-evidence hits before Phase 13.

## Execution

1. Created an isolated validation workspace so pre-fix baseline artifacts remain untouched.
2. Ran `run_validation.py --phase retrieve` on the latest Phase 13 code.
3. Initial real run exposed an additional true-path gap:
   - Q18 selected a `hybrid_cluster` `leaf_fallback` hotspot.
   - The selected hotspot had direct chunks but no children.
   - `_traverse_hotspot_with_children` returned only the waypoint.
   - `_map_query_hits_to_backend_hits` skipped the waypoint, produced `backend_hits=[]`, and runtime fallback returned zero/placeholder chunk hits.
4. Added a RED regression test for leaf hotspots with direct chunks.
5. Fixed `_traverse_hotspot_with_children` so leaf hotspots with direct chunks return waypoint + own evidence chunks.
6. Reran focused tests and real retrieve validation.

## Test Results

```text
pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotNoChildren -q
2 passed

pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q
28 passed
```

## Real Retrieval Results

### Evidence-chain report after fix

```json
{
  "total_hits": 92,
  "queries_with_hits": 20,
  "zero_hit_queries": 0,
  "zero_hit_query_rate": 0.0,
  "zero_chunk_hits": 0,
  "parent_only_hits": 0,
  "missing_node_hits": 0,
  "missing_chunk_hits": 0,
  "placeholder_chunk_hits": 0,
  "evidence_chunk_hits": 92,
  "chunk_id_present_rate": 1.0,
  "evidence_chunk_rate": 1.0,
  "heading_path_rate": 1.0
}
```

### Q18 before vs after

| Metric | Pre-fix baseline | Post-fix Phase 13 |
|---|---:|---:|
| Total queries | 20 | 20 |
| Queries with hits | 10 | 20 |
| Total hits | 18 | 92 |
| Missing chunk hits | 5 | 0 |
| Evidence chunk hits | 13 | 92 |
| Q18 hit count | 5 | 5 |
| Q18 real chunk IDs | 0/5 | 5/5 |

### Q18 post-fix hits

Query: `embedding 模型的选择依据是什么？文档中使用了哪些模型？`

All top-5 hits now come from `tree_semantic` / `subtree_hotspot_traversal` and have real chunk IDs:

1. `ac2a6c57-ca9c-5285-9dcc-88dd935ec78d`
2. `da6f4f28-f343-5ef6-b42a-7616e004c83d`
3. `67e0d3a7-7b47-5cb6-886c-fb9f7329f6f5`
4. `8ecdaebe-a19c-5f62-a63d-6b025861215f`
5. `d5123fb5-851f-537c-ae0a-a19cb932a672`

## Root Cause Closed

The original Phase 13 design handled route/summary hotspots that need one-level child evidence. Real Q18 additionally used `hybrid_cluster` leaf fallback, where the hotspot is already an evidence-bearing leaf with direct chunks. The final fix covers both cases:

- Route/summary hotspot with children: returns waypoint + child evidence chunks.
- Leaf fallback hotspot with direct chunks and no children: returns waypoint + own evidence chunks.
- Empty/no-evidence hotspot: still returns waypoint only.

## Verdict

**PASS for the targeted real issue.** Q18 no longer returns `chunk_id=null` or placeholder/zero chunk hits after the leaf-hotspot direct-evidence fix.

## Remaining Work

`--phase score` is still pending because it requires filling `judgment_completed.csv` for the new 92 retrieved hits. Retrieval/evidence-chain integrity is now ready for scoring.
