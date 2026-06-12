# Phase 10-01 Summary — DB-Backed Whitebox Demo

**Date:** 2026-06-12
**Plan:** 10-01
**Status:** PASS

## Objective

Execute `scripts/demo_hotspot_semantic_retrieval.py` against real PostgreSQL data to validate:

```text
SubtreeHotspotSelector
→ RecursiveTreeTraversalRunner(start_node_id=hotspot_head)
→ EvidenceContentResolver
→ final evidence-bearing hits only
```

## Environment Gate

| Check | Result | Notes |
|---|---:|---|
| `.env` contains `DATABASE_URL` | PASS | Existence/non-placeholder checked without printing the value. |
| Raw `DATABASE_URL` exposed | PASS | No raw connection string was printed or written. |
| Docker Desktop / Linux engine | PASS | Docker Desktop was started and `docker ps` succeeded. |
| PostgreSQL container | PASS | `rag_registry_postgres` started from `verification/docker-compose.yml` and reported healthy. |
| PostgreSQL reachable | PASS | Demo connected through the configured `DATABASE_URL`; raw value was not exposed. |

## Demo Execution

Command:

```text
rtk python scripts/demo_hotspot_semantic_retrieval.py
```

Result:

```text
Exit code: 0
[OK] parent hotspots were used as navigation; final hits are evidence-bearing chunks
```

Key observed output:

```text
[1] registered doc_id=... version_id=...
[2] canonical_spans=3
[3] tree_nodes=5 tree_node_spans=3
[4] vector_loader={... 'count': 3} vector_chunks=3
[6] selected hotspots:
    reason=subtree_similarity ... path=PageIndex 完整功能分析与集成方案 > PageIndex vs 当前实现对比
[7] final hits (evidence-bearing only):
    retrieval_path=subtree_hotspot_traversal
    hotspot_node_id=...
    navigation_path=[...]
[8] assertions:
    zero_chunk_hits=0
    parent_only_hits=0
    total_hits=3
```

The demo created a temporary source file under `verification/hotspot-semantic-demo/`, printed no secret values, and completed DB-backed ingestion/retrieval.

## Evidence-Chain Result

DB-backed evidence-chain validation **passed**.

| Requirement | Status |
|---|---:|
| Demo exit code 0 | PASS |
| `[OK] parent hotspots were used as navigation` | PASS |
| `zero_chunk_hits == 0` | PASS |
| `parent_only_hits == 0` | PASS |
| Navigation metadata in DB-backed hits | PASS |
| Final hits evidence-bearing chunks/spans/nodes only | PASS |

## Semantic Contract Verified

- Parent/route nodes were selected as hotspots.
- Hotspot parent nodes were preserved as navigation metadata via `hotspot_node_id`, `navigation_node_ids`, and `navigation_path`.
- Final returned hits were evidence-bearing content nodes with normal `chunk_id` values.
- No all-zero `MISSING_CHUNK_ID` hit was returned.
- No route-only parent was returned as final content.

## Next Action

Proceed to Phase 10-03 quality impact assessment using DB-backed hotspot output over the Phase 8 aligned corpus/query set.
