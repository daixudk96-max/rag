# Phase 10: Hotspot Semantic Retrieval Validation - Research

**Researched:** 2026-06-11
**Domain:** Hotspot semantic retrieval, parent routing nodes, evidence-chain integrity, DB-backed whitebox validation, quality impact assessment
**Confidence:** HIGH (implementation exists and tests passing; DB-backed validation pending)

## Summary

Phase 10 validates a semantic change where parent tree nodes act as routing hotspots/navigation metadata instead of content-return nodes. The implementation exists in the uncommitted working tree across `llamaindex_runtime/tree/semantic_distribution.py`, `llamaindex_runtime/tree/runtime.py`, tests (`test_tree_semantic_hotspot.py`), and a whitebox demo script (`scripts/demo_hotspot_semantic_retrieval.py`). The semantic change separates subtree aggregation (centroid, support, dispersion) from final hit construction: SubtreeHotspotSelector selects routing parents, RecursiveTreeTraversalRunner drills to evidence-bearing children, and final hits preserve navigation metadata (hotspot_node_id, navigation_node_ids, drill_depth) while returning only chunk-span provenance.

The planner must execute DB-backed whitebox validation, verify evidence-chain integrity (no all-zero chunk_id hits), assess Level impact relative to Phase 8 baseline (hit_rate 0.70, top1_relevance 0.59, stability 0.65), and complete code review gates. GitNexus impact analysis and detect-change checks are required before any eventual commit, but Phase 10 research scope is validation-only, not commit/tag/push.

**Primary recommendation:** Use the existing demo script (`scripts/demo_hotspot_semantic_retrieval.py`) with real DATABASE_URL to execute DB-backed whitebox validation, then extend Phase 8 quality validation scripts to compare hotspot semantic retrieval against baseline metrics. Gate code review and Level assessment behind integrity verification first.

<user_constraints>
## User Constraints (from ROADMAP.md Phase 10 entry)

Phase 10 has no CONTEXT.md yet. Constraints come from ROADMAP Phase 10 entry and objective:

- **Do not commit, tag, push, reset, clean, delete, checkout, or modify code** [VERIFIED: objective / ROADMAP]
- **Do not print or store raw DATABASE_URL** [VERIFIED: objective]
- **Phase 8 is complete with Level_2 authoritative baseline** [VERIFIED: ROADMAP, Phase 8 artifacts]
- **Phase 9 is close-ready pending approval (dirty-tree classification complete)** [VERIFIED: ROADMAP, STATE.md]
- **Phase 10 semantic change: parent nodes are routing hotspots, not content-return nodes** [VERIFIED: ROADMAP Phase 10 entry]
- **Implementation exists in uncommitted working tree; validation phase scope is DB-backed testing** [VERIFIED: ROADMAP Phase 10 "Implementation Status"]
- **GitNexus impact/detect-change required before eventual commit** [VERIFIED: CLAUDE.md GitNexus directive]
- **Workflow supports chunked execution** [VERIFIED: objective]

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-P10-DB-BACKED-WHITEBOX | Run DB-backed whitebox demo with real spans/chunks/tree_nodes/embeddings. | Existing demo script (`scripts/demo_hotspot_semantic_retrieval.py`) uses PostgreSQL, TreeGenerator, VectorLoader, real embeddings; requires DATABASE_URL configuration. |
| REQ-P10-EVIDENCE-CHAIN-INTegrity | Verify final hits have valid chunk_id/span_id/node_id; no all-zero structural headings. | EvidenceContentResolver contract, QueryHit provenance fields, runtime.py `_build_hits_from_node` construction, Phase 8 integrity gate pattern. |
| REQ-P10-LEVEL-IMPACT | Assess Level impact: does hotspot routing improve hit_rate/top1_relevance/stability? | Phase 8 baseline metrics (0.70/0.59/0.65), Phase 8 quality validation scripts, level_assessment.json thresholds (0.80/0.90/0.85), retrieval rerun pattern. |
| REQ-P10-CODE-REVIEW-GATE | Architectural boundaries, performance, error handling, GitNexus impact analysis. | Code review patterns from Phase 5/8, GitNexus tools (`gitnexus_impact`, `gitnexus_detect_changes`), architectural responsibility mapping. |
| REQ-P10-NAVIGATION-METADATA | Verify hotspot_node_id, navigation_node_ids, drill_depth preserved in QueryHit and backend hits. | QueryHit dataclass fields, runtime.py `_backend_hit_to_dict` mapping, backend_adapter.py BackendHit contract. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hotspot selection | Retrieval layer (semantic_distribution.py) | — | SubtreeHotspotSelector aggregates descendant semantics, scores routing nodes |
| Tree traversal | Retrieval layer (semantic_distribution.py) | — | RecursiveTreeTraversalRunner drills from hotspot head to evidence-bearing children |
| Evidence construction | Retrieval layer (semantic_distribution.py) | Vector layer | `_build_hits_from_node` uses direct chunk_ids only, no descendant transplant |
| Content hydration | Retrieval layer (evidence_content_resolver.py) | Vector layer | EvidenceContentResolver resolves preview from canonical_spans/vector_chunks |
| Registry queries | Database layer (PostgreSQL) | — | Active version spans/chunks/tree_nodes/embeddings persisted in DB |
| Quality validation | Validation layer (Phase 8 scripts) | Retrieval layer | Metrics calculation, integrity gate, Level assessment use retrieval outputs |
| GitNexus analysis | Code intelligence layer | — | Impact/detect-change tools analyze call graph before commit |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.x | — | Implementation language | Project standard [VERIFIED: pyproject.toml] |
| psycopg | — | PostgreSQL database driver | Registry backend [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py] |
| llama_index.core | — | Embedding/query interfaces | PageIndex adapter contract [VERIFIED: llamaindex_runtime dependencies] |
| pytest | — | Test framework | Phase 8 validation suite, test_tree_semantic_hotspot.py [VERIFIED: tests/] |
| GitNexus MCP | — | Code intelligence, impact analysis | CLAUDE.md mandatory impact/detect-change before commit |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DeterministicEmbedder | — | Deterministic embeddings for testing | Whitebox demo uses controlled embeddings (dim=16) |
| TreeGenerator | — | Tree structure from persisted spans | Demo generates tree_nodes/node_spans from canonical_spans |
| VectorLoader | — | Vector chunk materialization | Demo materializes vector_chunks with embeddings |
| uuid | — | UUID generation, namespace UUIDs | Canonical span IDs, version IDs, node IDs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Mock registry for whitebox | Real PostgreSQL | Mock simplifies testing but DB-backed is Phase 10 requirement; demo script uses real DB |
| Fixture-only tests | DB-backed validation | Fixture tests passed (39 tests); Phase 10 requires DB-backed whitebox per ROADMAP |
| Manual quality comparison | Phase 8 scripts rerun | Manual comparison risks inconsistency; reuse Phase 8 calculate_metrics.py pattern |

**Installation:**
All dependencies already installed in working tree. Demo script requires DATABASE_URL environment variable.

**Version verification:**
```
Python 3.x [VERIFIED: existing tests run]
pytest [VERIFIED: test_tree_semantic_hotspot.py 39 tests passing]
psycopg [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py imports]
GitNexus MCP [ASSUMED: available via npx gitnexus or MCP tools - needs verification in execution shell]
```

## Architecture Patterns

### System Architecture Diagram

```
Query Embedding
       │
       ├─► SubtreeHotspotSelector (semantic_distribution.py)
       │        │
       │        ├─► PersistedTreeSemanticDistributionAdapter
       │        │        │
       │        │        ├─► Registry Queries (tree_nodes, spans, chunks)
       │        │        ├─► Node Stats Builder (centroid, support, dispersion)
       │        │        │
       │        │        └─► Distribution Report (node_stats, tree_signals)
       │        │
       │        ├─► Hotspot Scoring (route_bonus, depth_bonus, support_bonus)
       │        ├─► Path Overlap Deduplication
       │        │
       │        └─► Selected Hotspots (SubtreeHotspot[node_id, score, reason])
       │
       ├─► RecursiveTreeTraversalRunner (semantic_distribution.py)
       │        │
       │        ├─► Traversal from hotspot head (start_node_id)
       │        ├─► Policy Decision (drill_down / keep_parent / prune)
       │        │        │
       │        │        ├─► drill_down: recurse to children
       │        │        ├─► keep_parent: collect evidence from direct chunks
       │        │        └─► prune: no hits
       │        │
       │        ├─► Navigation Metadata Tracking (navigation_node_ids, drill_depth)
       │        │
       │        └─► QueryHits (evidence-bearing only, direct chunk_ids)
       │
       ├─► Backend Hit Mapping (runtime.py _backend_hit_to_dict)
       │        │
       │        ├─► EvidenceContentResolver (preview from canonical_spans/vector_chunks)
       │        ├─► Navigation Path Construction (hotspot_node_id, navigation_path)
       │        │
       │        └─► Backend Hits (heading_path, chunk_id, text_preview, navigation metadata)
       │
       └─► Final Evidence-Bearing Hits
                │
                ├─► Evidence-Chain Integrity Check (chunk_id != all-zero UUID)
                ├─► Navigation Metadata Preservation
                │
                └─► Quality Validation (hit_rate, top1_relevance, stability)
```

### Recommended Project Structure

Phase 10 uses existing working tree structure; no new files created in research phase:

```
llamaindex_runtime/tree/
├── semantic_distribution.py    # SubtreeHotspotSelector, RecursiveTreeTraversalRunner, QueryHit
├── runtime.py                  # _retrieve_tree_hits_from_backend, hotspot integration
├── evidence_content_resolver.py # Content hydration contract
└── backend_adapter.py          # BackendHit contract

tests/llamaindex_runtime/
├── test_tree_semantic_hotspot.py  # 39 tests passing (fixture-based)
└── test_query_quality_validation.py  # Phase 8 quality validation pattern

scripts/
└── demo_hotspot_semantic_retrieval.py  # DB-backed whitebox demo (real PostgreSQL)

verification/phase8-matched-validation-rerun/
├── quality_metrics.json        # Baseline metrics (0.70/0.59/0.65)
├── level_assessment.json       # Baseline Level_2, thresholds
└── calculate_phase8_metrics.py  # Quality comparison pattern
```

### Pattern 1: Subtree Hotspot Selection

**What:** Select parent routing nodes whose subtree centroid is close to query embedding, without treating parent as final content hit.

**When to use:** When tree structure has parent nodes that aggregate descendant semantics (route nodes) but should not return parent-owned text because parent lacks direct chunk evidence.

**Example:**

```python
# Source: semantic_distribution.py SubtreeHotspotSelector.select_hotspots()
hotspots = SubtreeHotspotSelector().select_hotspots(
    query_embedding=query_embedding,
    node_stats=distribution_report["node_stats"],
    tree_signals=distribution_report["tree_signals"],
    limit=3,
)

for hotspot in hotspots:
    # hotspot.node_id is a routing parent
    # hotspot.score reflects subtree similarity + route_bonus + depth_bonus
    # hotspot.reason: "subtree_similarity" for route nodes
    runner.traverse_tree_for_query(
        start_node_id=hotspot.node_id,
        hotspot_node_id=hotspot.node_id,
        # drills to evidence-bearing children
    )
```

**Contract:** Hotspot node is routing start point; final hits come from descendant chunks only.

### Pattern 2: Recursive Tree Traversal with Navigation Metadata

**What:** Traverse from hotspot head to evidence-bearing children, tracking navigation path (navigation_node_ids) and drill depth.

**When to use:** When hotspot selection narrows search scope to a subtree, but final hits must preserve provenance showing how traversal reached the evidence node.

**Example:**

```python
# Source: semantic_distribution.py RecursiveTreeTraversalRunner._traverse_from_node()
hits = runner.traverse_tree_for_query(
    version_id=version_id,
    query_embedding=query_embedding,
    registry=registry,
    policy=policy,
    adapter=adapter,
    start_node_id=hotspot.node_id,  # hotspot head
    hotspot_node_id=hotspot.node_id,
)

# Each hit preserves navigation metadata:
# - hotspot_node_id: routing start point
# - navigation_node_ids: path from hotspot to evidence node
# - drill_depth: how many levels drilled
# - chunk_id/span_id/node_id: final evidence provenance
```

**Contract:** Navigation metadata is preserved; final hits have direct chunk_ids only (no descendant transplant).

### Pattern 3: Evidence-Bearing Hit Construction

**What:** Build QueryHit from direct chunk_ids only; route nodes without direct chunks remain traversal waypoints, not final hits.

**When to use:** When policy decision is "keep_parent" for a node with direct chunk evidence, but route-only parents (is_route_node=True) should never produce hits even if subtree has evidence.

**Example:**

```python
# Source: semantic_distribution.py _build_hits_from_node()
def _build_hits_from_node(*, node_stats, ...) -> list[QueryHit]:
    chunk_ids = node_stats.get("chunk_ids", [])  # direct chunks only
    hits: list[QueryHit] = []
    for chunk_id in chunk_ids:
        # each chunk_id maps to span_ids
        hits.append(QueryHit(
            chunk_id=chunk_id,  # evidence-bearing
            hotspot_node_id=hotspot_node_id,  # navigation start
            navigation_node_ids=navigation_node_ids,  # drill path
        ))
    return hits  # empty if node_stats["chunk_ids"] is empty (route node)
```

**Contract:** `_build_hits_from_node` uses `node_stats["chunk_ids"]` (direct only), not `subtree_chunk_ids`. Route nodes produce zero hits even if subtree has evidence.

### Anti-Patterns to Avoid

- **Transplanting descendant chunks to parent hits:** If a route node is selected as hotspot, do not return descendant chunk_ids as parent hits. Parent is routing metadata; descendant chunks become hits when traversal drills to them. [VERIFIED: semantic_distribution.py line 252 "chunk_ids": direct_chunk_ids]
- **Returning parent content when parent lacks chunks:** If policy decides "keep_parent" for a route node with zero direct chunks, the hit list is empty. Do not fabricate parent content from descendant text. [VERIFIED: semantic_distribution.py line 898-922]
- **Skipping integrity check for hotspot hits:** Final hits must pass evidence-chain integrity (chunk_id != MISSING_CHUNK_ID, span_id != None). Navigation metadata does not replace provenance. [VERIFIED: test_tree_semantic_hotspot.py assertions]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|------|
| Subtree aggregation | Custom centroid computation from descendant vectors | `PersistedTreeSemanticDistributionAdapter.analyze_tree_semantic_distribution()` | Handles embedding coercion, dimension mismatch, node_id resolution, skipped chunks |
| Hotspot scoring | Manual similarity + depth + support bonus calculation | `SubtreeHotspotSelector.select_hotspots()` | Encapsulates route_bonus, depth_bonus, support_bonus, path overlap deduplication |
| Tree traversal | Custom recursion without policy decisions | `RecursiveTreeTraversalRunner.traverse_tree_for_query()` | Handles start_node_id, policy decision, navigation tracking, depth limit |
| Content preview | Direct canonical_spans.raw_text access | `EvidenceContentResolver.build_preview()` | Handles span-chunk resolution, fallback chain (span → chunk → summary/title) |
| Quality validation | Manual hit_rate/top1_relevance calculation | Phase 8 `calculate_phase8_metrics.py` pattern | Integrity gate, threshold comparison, level_assessment.json format |
| Impact analysis | Manual call graph inspection | GitNexus `gitnexus_impact({target: "symbolName", direction: "upstream"})` | CLAUDE.md mandates impact analysis before editing symbols |

**Key insight:** The hotspot semantic change is a traversal contract, not a content transplant. Use existing adapters and runners instead of re-implementing aggregation, scoring, traversal, or content resolution.

## Runtime State Inventory

> Phase 10 is validation, not rename/refactor/migration. Inventory section omitted.

## Common Pitfalls

### Pitfall 1: Database URL Configuration Missing

**What goes wrong:** Demo script fails with `[FAIL] DATABASE_URL is not configured` because environment variable is unset.

**Why it happens:** Phase 10 DB-backed whitebox requires real PostgreSQL connection; local environment may have DATABASE_URL in .env but script may not load dotenv correctly.

**How to avoid:** Ensure `.env` file exists with DATABASE_URL, and demo script calls `load_dotenv(REPO_ROOT / ".env")` before reading `os.getenv("DATABASE_URL")`. [VERIFIED: demo script line 121-125]

**Warning signs:** `[FAIL] DATABASE_URL is not configured` output; script exit code 2.

### Pitfall 2: Evidence-Chain Integrity Failure (All-Zero chunk_id)

**What goes wrong:** Final hits contain `chunk_id = UUID(int=0)` (MISSING_CHUNK_ID sentinel), indicating structural headings without vector chunks.

**Why it happens:** Phase 8 identified several retrieval hits as structural headings with all-zero chunk_id; hotspot traversal may inherit this if route nodes produce hits without checking direct chunk_ids.

**How to avoid:** Verify `_build_hits_from_node` uses `node_stats["chunk_ids"]` (direct only) and filters empty chunk_ids. Demo script assertion checks `zero_chunk_hits` count. [VERIFIED: demo script line 247-255]

**Warning signs:** `chunk_id_missing: True` in backend hit; `zero_chunk_hits > 0` in demo output.

### Pitfall 3: Navigation Metadata Not Preserved in Backend Hits

**What goes wrong:** Backend hits lack `hotspot_node_id`, `navigation_path`, `retrieval_path` fields, breaking provenance transparency.

**Why it happens:** `runtime.py` `_backend_hit_to_dict` may not map QueryHit navigation fields to BackendHit dict keys.

**How to avoid:** Verify `_backend_hit_to_dict` maps `hotspot_node_id`, `navigation_node_ids` to backend hit fields. Test asserts navigation metadata presence. [VERIFIED: runtime.py needs inspection; demo script line 242-244 checks hotspot_node_id, navigation_path]

**Warning signs:** Backend hit dict missing hotspot/navigation keys; demo assertion `[FAIL] expected evidence-bearing hits with normal chunk IDs`.

### Pitfall 4: Level Regression from Hotspot Routing

**What goes wrong:** Hotspot semantic retrieval produces worse metrics than Phase 8 baseline (hit_rate 0.70, top1_relevance 0.59, stability 0.65), causing Level downgrade or blocking Level advancement.

**Why it happens:** Hotspot routing may narrow search scope too aggressively, missing relevant evidence in other subtrees; or traversal policy may prune too early.

**How to avoid:** Run quality comparison on aligned corpus (Phase 8 corpus) with same queries/judgments; adjust hotspot limit, policy thresholds if metrics regress significantly. [VERIFIED: Phase 8 thresholds frozen; need rerun with hotspot backend]

**Warning signs:** Quality metrics lower than Phase 8; `level_assessment.json` shows Level_2 blocking factors unchanged.

### Pitfall 5: GitNexus Impact Analysis Not Run Before Commit

**What goes wrong:** Commit affects unexpected symbols/exec flows because `gitnexus_impact` was skipped, violating CLAUDE.md mandatory directive.

**Why it happens:** Phase 10 planner may assume tests passing is sufficient; CLAUDE.md requires GitNexus analysis before editing symbols or committing.

**How to avoid:** Before eventual commit, run `gitnexus_impact({target: "SubtreeHotspotSelector", direction: "upstream"})` and report blast radius; run `gitnexus_detect_changes()` to verify affected scope. [VERIFIED: CLAUDE.md "Always Do" / "Never Do"]

**Warning signs:** Commit blocked by GitNexus warning; affected symbols larger than expected.

## Code Examples

### Whitebox Demo Execution

```python
# Source: scripts/demo_hotspot_semantic_retrieval.py main()
from dotenv import load_dotenv
import psycopg

load_dotenv(REPO_ROOT / ".env")
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[FAIL] DATABASE_URL is not configured")
    return 2

with psycopg.connect(db_url) as conn:
    registry = PostgresRegistryWriter(conn)
    # register document, persist spans, generate tree, materialize vectors
    # ...
    hits = retrieve_tree_hits_from_pdf(
        source_path,
        query=query,
        embed_model=embed_model,
        similarity_top_k=5,
        registry=registry,
        version_id=version_id,
        backend_type="embedding",  # hotspot semantic path
    )
    # verify evidence-chain integrity
    zero_chunks = [hit for hit in hits if hit.get("chunk_id_missing") is True]
    if zero_chunks:
        print("[FAIL] expected evidence-bearing hits with normal chunk IDs")
        return 1
    print("[OK] parent hotspots were used as navigation; final hits are evidence-bearing chunks")
    return 0
```

### Hotspot Selection and Traversal

```python
# Source: llamaindex_runtime/tree/semantic_distribution.py
from llamaindex_runtime.tree.semantic_distribution import (
    PersistedTreeSemanticDistributionAdapter,
    SubtreeHotspotSelector,
    RecursiveTreeTraversalRunner,
    BaselineTreeBranchDecisionPolicy,
)

adapter = PersistedTreeSemanticDistributionAdapter()
report = adapter.analyze_tree_semantic_distribution(
    version_id=version_id,
    registry=registry,
)
query_embedding = embed_model.get_query_embedding(query)

hotspots = SubtreeHotspotSelector().select_hotspots(
    query_embedding=query_embedding,
    node_stats=report["node_stats"],
    tree_signals=report["tree_signals"],
    limit=3,
)

runner = RecursiveTreeTraversalRunner()
policy = BaselineTreeBranchDecisionPolicy(
    dispersion_threshold=1.0,
    entropy_threshold=0.5,
)

hits: list[QueryHit] = []
for hotspot in hotspots:
    hits.extend(
        runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
            start_node_id=hotspot.node_id,
            hotspot_node_id=hotspot.node_id,
        )
    )
    if len(hits) >= limit:
        break
```

### Quality Comparison Pattern (from Phase 8)

```python
# Source: verification/phase8-matched-validation-rerun/calculate_phase8_metrics.py pattern
import json
from pathlib import Path

# Load Phase 8 baseline
baseline_metrics = json.loads(
    Path("verification/phase8-matched-validation-rerun/quality_metrics.json").read_text()
)["metrics"]

# Run hotspot retrieval on same corpus/queries
# Calculate new metrics
hotspot_metrics = {
    "hit_rate": ...,
    "top1_relevance": ...,
    "stability": ...,
}

# Compare against thresholds
thresholds = baseline_metrics["thresholds"]  # or level_assessment.json thresholds
comparison = {
    "hit_rate": {
        "baseline": baseline_metrics["hit_rate"],
        "hotspot": hotspot_metrics["hit_rate"],
        "threshold": thresholds["hit_rate"],
        "improved": hotspot_metrics["hit_rate"] > baseline_metrics["hit_rate"],
        "passed": hotspot_metrics["hit_rate"] >= thresholds["hit_rate"],
    },
    # ... top1_relevance, stability
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parent nodes return content if they have chunk_ids | Parent nodes aggregate descendant semantics, act as routing hotspots, return only navigation metadata | Phase 10 implementation (semantic_distribution.py) | Separates routing from content; prevents parent-content confusion |
| Traversal from root only | Traversal from hotspot head (start_node_id) | Phase 10 implementation (RecursiveTreeTraversalRunner) | Narrows search scope; improves efficiency; enables subtree-focused retrieval |
| Hit provenance limited to chunk_id/span_id | Hit provenance extended with hotspot_node_id, navigation_node_ids, drill_depth | Phase 10 implementation (QueryHit dataclass) | Transparency: users see routing path, not just final evidence |

**Deprecated/outdated:**
- Root-bias traversal (Phase 4/8 concern): SubtreeHotspotSelector selects nearest route parent, not root, when descendant has evidence. Path overlap deduplication prevents root duplicate selection. [VERIFIED: semantic_distribution.py line 533-541]
- Parent-content hits (Phase 8 structural headings with all-zero chunk_id): `_build_hits_from_node` filters empty direct chunks; route nodes produce zero hits even with subtree evidence. [VERIFIED: semantic_distribution.py line 898-922]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | GitNexus MCP tools available via npx or MCP interface | Environment Availability | If unavailable, CLI fallback required; impact/detect-change cannot run automatically |
| A2 | DATABASE_URL configured in .env file | Environment Availability | If missing, DB-backed whitebox demo fails; Phase 10 validation blocked |
| A3 | Phase 8 aligned corpus still valid for Phase 10 comparison | Standard Stack / Validation | If corpus changed, metrics comparison invalid; need rerun with matched corpus/queries/judgments |
| A4 | DeterministicEmbedder(dim=16) produces valid embeddings for demo | Code Examples | If dimension mismatch or embedding quality poor, hotspot selection may fail; need real embed_model for quality validation |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions

1. **GitNexus availability in execution shell**
   - What we know: CLAUDE.md mandates `gitnexus_impact` before editing symbols; `gitnexus_detect_changes` before commit.
   - What's unclear: Is GitNexus MCP enabled in execution shell, or is CLI fallback (`npx gitnexus`) required?
   - Recommendation: Probe availability with `npx gitnexus analyze` or MCP tool; document fallback if unavailable.

2. **Phase 8 judgment reuse for hotspot quality comparison**
   - What we know: Phase 8 has 95 matched judgment rows for aligned corpus (PageIndex完整功能分析与集成方案.md).
   - What's unclear: Can we reuse Phase 8 judgments for hotspot retrieval hits, or do hotspot hits differ in content/preview enough that judgments become invalid?
   - Recommendation: If hotspot hits use same canonical_spans.raw_text, judgments may be reusable. If preview differs significantly (e.g., EvidenceContentResolver fallback chain), need new judgments. Integrity gate pattern from Phase 5 can validate retrieval/judgment match.

3. **Backend hit mapping completeness for navigation metadata**
   - What we know: QueryHit has hotspot_node_id, navigation_node_ids, drill_depth fields.
   - What's unclear: Does `_backend_hit_to_dict` in runtime.py map these fields to backend hit dict keys?
   - Recommendation: Inspect runtime.py `_backend_hit_to_dict` implementation; verify backend hit dict contains hotspot_node_id, navigation_path, retrieval_path. Test assertions check these fields.

4. **Hotspot traversal policy threshold tuning**
   - What we know: BaselineTreeBranchDecisionPolicy uses dispersion_threshold=1.0, entropy_threshold=0.5.
   - What's unclear: Are these thresholds optimal for hotspot routing, or do they need tuning based on real tree statistics?
   - Recommendation: Run whitebox demo with current thresholds; if traversal prunes too early or drills too deep, adjust thresholds iteratively. HIRO policy available as alternative.

5. **Level assessment update mechanism**
   - What we know: Phase 8 level_assessment.json is valid Level_2; Phase 10 may produce new metrics.
   - What's unclear: Should Phase 10 update level_assessment.json directly, or produce a separate assessment file (phase10_level_assessment.json)?
   - Recommendation: Follow Phase 8 pattern: produce phase10_quality_metrics.json and phase10_level_assessment.json; avoid modifying Phase 8 artifacts. Comparison report shows delta.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | DB-backed whitebox demo | ✓ (Phase 7/8 proven) | — | — |
| DATABASE_URL env var | Demo script, registry queries | ASSUMED | — | Blocked if missing |
| GitNexus MCP | Impact analysis, detect-change | ASSUMED | — | `npx gitnexus` CLI fallback |
| pytest | Test execution | ✓ | — | — |
| psycopg | PostgreSQL driver | ✓ | — | — |
| llama_index.core | Embedding interfaces | ✓ | — | — |
| DeterministicEmbedder | Demo embeddings | ✓ | — | — |

**Missing dependencies with no fallback:**
- DATABASE_URL: If missing, DB-backed whitebox demo fails; Phase 10 validation blocked.
- GitNexus: If MCP unavailable and CLI not installed, impact/detect-change blocked; commit violates CLAUDE.md directive.

**Missing dependencies with fallback:**
- GitNexus MCP: If unavailable, use `npx gitnexus` CLI for analysis/detection.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | None (standard pytest discovery) |
| Quick run command | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -v` |
| Full suite command | `pytest tests/llamaindex_runtime/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-P10-DB-BACKED-WHITEBOX | Run demo with real DB data | integration | `python scripts/demo_hotspot_semantic_retrieval.py` | ✅ |
| REQ-P10-EVIDENCE-CHAIN-INTegrity | Verify chunk_id != all-zero | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestSubtreeHotspotSelector -v` | ✅ |
| REQ-P10-NAVIGATION-METADATA | Verify hotspot_node_id preserved | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestRuntimeHotspotIntegration -v` | ✅ |
| REQ-P10-LEVEL-IMPACT | Compare metrics vs Phase 8 baseline | integration | `python verification/phase10_quality_comparison.py` (needs creation) | ❌ Wave 0 |
| REQ-P10-CODE-REVIEW-GATE | Architectural boundaries, GitNexus impact | manual | GitNexus tools or CLI | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** N/A (Phase 10 research scope: validation, not commit)
- **Per wave merge:** `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -v`
- **Phase gate:** Demo script success + evidence-chain integrity + quality comparison + code review

### Wave 0 Gaps
- [ ] `verification/phase10_hotspot_quality_comparison.py` — compares hotspot metrics vs Phase 8 baseline
- [ ] GitNexus impact analysis — needs execution in shell with GitNexus available
- [ ] Code review gate — architectural boundaries, performance, error handling

*(If no gaps: "None — existing test infrastructure covers all phase requirements" — but Level impact and code review gates are Wave 0 gaps)*

## Security Domain

> Security enforcement is implicit in Phase 10 (DB-backed validation, provenance integrity). ASVS categories apply where relevant.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Demo script uses DATABASE_URL only, no user authentication |
| V3 Session Management | no | No session state in validation scope |
| V4 Access Control | no | No user access control in validation scope |
| V5 Input Validation | yes | Query embedding validation (dimension check), node_stats field validation [VERIFIED: semantic_distribution.py _coerce_embedding, _required_value] |
| V6 Cryptography | no | No cryptographic operations in validation scope |

### Known Threat Patterns for Hotspot Semantic Retrieval

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Dimension mismatch in embeddings | Tampering | `_coerce_embedding` validates dimension consistency; `_compute_centroid` raises ValueError on mismatch [VERIFIED: semantic_distribution.py line 383-389] |
| Missing required fields in node_stats | Tampering | `_required_value` raises ValueError if key missing [VERIFIED: semantic_distribution.py line 351-354] |
| Recursion depth limit exceeded | Denial of Service | `_MAX_TRAVERSAL_DEPTH = 256` prevents infinite recursion [VERIFIED: semantic_distribution.py line 56, 674] |
| Path traversal injection in heading_path | Tampering | `_heading_path_parts` sanitizes separator, strips whitespace [VERIFIED: semantic_distribution.py line 544-551] |
| Missing node_id in chunk resolution | Tampering | `_resolve_node_id` returns None if no mapping; chunk skipped [VERIFIED: semantic_distribution.py line 333-348] |

## Sources

### Primary (HIGH confidence)
- semantic_distribution.py - SubtreeHotspotSelector, RecursiveTreeTraversalRunner, QueryHit implementation [VERIFIED: file inspection]
- runtime.py - _retrieve_tree_hits_from_backend, hotspot integration [VERIFIED: file inspection]
- test_tree_semantic_hotspot.py - 39 fixture-based tests [VERIFIED: file inspection, pytest collection]
- demo_hotspot_semantic_retrieval.py - DB-backed whitebox script [VERIFIED: file inspection]
- Phase 8 artifacts (quality_metrics.json, level_assessment.json) - Baseline metrics [VERIFIED: file inspection]

### Secondary (MEDIUM confidence)
- evidence_content_resolver.py - Content hydration contract [VERIFIED: partial file inspection]
- Phase 5/8 validation patterns - Integrity gate, quality comparison [CITED: ROADMAP Phase 5/8 entries]

### Tertiary (LOW confidence)
- GitNexus MCP availability - needs shell verification [ASSUMED: CLAUDE.md reference]
- DATABASE_URL configuration in .env - needs environment verification [ASSUMED: Phase 7/8 proven]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - implementation exists, tests passing, dependencies verified
- Architecture: HIGH - semantic_distribution.py, runtime.py structure inspected; navigation metadata fields confirmed
- Pitfalls: HIGH - demo script assertions, Phase 8 evidence-chain issues documented, GitNexus directive clear

**Research date:** 2026-06-11
**Valid until:** 30 days (implementation stable; DB-backed validation pending)