# Phase 10-02 Summary — Evidence-Chain Integrity and Navigation Metadata

**Date:** 2026-06-12
**Plan:** 10-02
**Status:** PASS_DB_BACKED_AND_PHASE8_ALIGNED

## Objective

Verify hotspot semantic retrieval returns final evidence-bearing hits only, while parent nodes remain hotspot/navigation metadata.

## Test Results

### Hotspot fixture suite

Command:

```text
rtk python -m pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q
```

Result:

```text
10 passed, 2 warnings
```

Warnings were dependency warnings only:

- `torch.cuda` / `pynvml` deprecation warning
- `PyPDF2` deprecation warning

### Related traversal regression suite

Command:

```text
rtk python -m pytest tests/llamaindex_runtime/test_hiro_traversal_integration.py tests/llamaindex_runtime/test_psi_rag_prototype_embedding.py tests/llamaindex_runtime/test_tree_runtime_hiro_selection.py -q
```

Result:

```text
5 passed, 2 warnings
```

## Code Inspection Findings

### Direct evidence only

`llamaindex_runtime/tree/semantic_distribution.py` now preserves the core contract:

- `_build_node_stats` keeps `chunk_ids` limited to direct chunk evidence.
- Descendant chunks are aggregated into subtree statistics only.
- Route nodes are identified with `is_route_node` when they have descendant evidence but no direct chunks.
- `_build_hits_from_node` builds final `QueryHit` objects only from `node_stats["chunk_ids"]`.

This confirms: parent nodes can route, but they do not inherit descendant content as final hits.

### Runtime provenance schema

`llamaindex_runtime/tree/runtime.py` now maps every semantic `QueryHit` with a consistent schema:

- `chunk_id`
- `chunk_id_missing`
- `hotspot_node_id`
- `navigation_node_ids`
- `navigation_path`
- `drill_depth`
- `backend_source`
- `retrieval_path`

Both hotspot-scoped traversal and root semantic traversal expose the same provenance keys.

### Defensive robustness fixes

The following defensive checks were added and tested:

| Area | Status | Evidence |
|---|---:|---|
| Query/tree embedding dimension mismatch | PASS | `SubtreeHotspotSelector` raises `ValueError` when `embedding_dimension` is a positive int and dimensions differ. |
| Corrupt tree cycle | PASS | `_collect_subtree_values` raises `ValueError` on active-path cycle detection. |
| Excessive subtree recursion depth | PASS | `_collect_subtree_values` raises if depth exceeds `_MAX_TRAVERSAL_DEPTH`. |
| Route-only parent semantics | PASS | Tests assert route-only parent drills to evidence children. |
| Final hit evidence chain | PASS | Tests assert valid `chunk_id` and `span_id`, not all-zero sentinels. |

## Result

Fixture-based and code-inspection evidence confirms the semantic contract:

```text
parent node = hotspot/navigation metadata
final hit = evidence-bearing chunk/span/node only
```

DB-backed confirmation has also passed through Phase 10-01 and Phase 10-03 validation: `zero_chunk_hits=0`, `parent_only_hits=0`, and Phase 8 aligned hotspot retrieval returned 80 evidence-bearing hits with hotspot metadata.
