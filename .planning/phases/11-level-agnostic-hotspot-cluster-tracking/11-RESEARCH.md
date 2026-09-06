# Phase 11: Level-Agnostic Hotspot Cluster Tracking - Research

**Researched:** 2026-06-17
**Domain:** Semantic retrieval hotspot selection algorithm
**Confidence:** HIGH

## Summary

Phase 11 requires replacing the current pre-ranked route-node hotspot selection algorithm with a level-agnostic, post-hoc cluster-based hotspot tracking approach. The current `SubtreeHotspotSelector` applies route-node bonuses before traversing, which biases selection toward parent nodes regardless of semantic evidence density. The target design requires all eligible nodes to compete equally by cosine similarity first, then infer the hotspot region by observing where semantic hits cluster structurally after the fact.

The core semantic shift is:

```text
Old: hotspot_node_id = node preselected as route/hotspot with bonus scoring
New: hotspot_node_id = post-hoc inferred shared region where hits clustered
```

This research confirms that the existing codebase provides strong foundations for incremental implementation: `QueryHit` already supports hotspot metadata fields, `RecursiveTreeTraversalRunner` accepts `hotspot_node_id` parameters, and the backend-hit mapping preserves navigation provenance. The primary implementation risk lies in the CRITICAL runtime-path functions `_retrieve_tree_hits_from_backend` and `_map_query_hits_to_backend_hits`, which require switch-gated modifications to support the new selector while preserving rollback capability.

**Primary recommendation:** Implement `ClusterHotspotSelector` as a parallel class behind `RAG_TREE_HOTSPOT_SELECTOR=cluster`, preserve `route_subtree` as fallback, and use TDD fixtures that validate no-route-bonus behavior, densest-shared-ancestor selection, and p6 DNA query regression.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Node similarity scoring | API / Backend | — | Cosine similarity computation against persisted embeddings happens in the semantic distribution adapter |
| Cluster inference | API / Backend | — | Ancestor aggregation and cluster scoring is pure algorithm logic, no UI/network concerns |
| Hotspot region selection | API / Backend | — | Post-hoc inference of densest local subtree from semantic hit distribution |
| Traversal execution | API / Backend | — | Recursive descent with policy-guided decisions remains backend logic |
| Evidence-bearing hit construction | API / Backend | — | Final hits built from persisted chunks/spans, provenance anchored |
| Backend-hit mapping | API / Backend | Frontend Server (potential future) | Runtime maps QueryHit metadata to response shape; could be adapted for API responses |
| Selector switch configuration | API / Backend | — | Environment variable `RAG_TREE_HOTSPOT_SELECTOR` controls selector path |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.x | PostgreSQL connection | Existing registry backend |
| dataclasses | stdlib | Immutable data structures | Phase 10 `QueryHit`, `SubtreeHotspot` pattern established |
| uuid | stdlib | UUID provenance anchors | Phase 1-10 provenance contracts use UUID universally |
| math | stdlib | Cosine similarity, distance calculations | Existing `_cosine_similarity` in semantic_distribution.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 7.x | Test framework | TDD validation for cluster selector |
| unittest.mock | stdlib | Registry mocking | Fixture-based tests follow Phase 10 pattern |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom cluster scoring formula | LLM rerank over clusters | LLM rerank adds latency and cost; scoring formula is deterministic and testable |
| Environment variable switch | Config file switch | Environment variable matches Phase 8 `RAG_TREE_BACKEND_TYPE` pattern and enables per-run experiments |

**Installation:** No new external dependencies required. Implementation uses stdlib and existing project infrastructure.

**Version verification:** N/A — all dependencies are stdlib or existing project packages.

## Architecture Patterns

### System Architecture Diagram

```text
query embedding
  ↓
PersistedTreeSemanticDistributionAdapter.analyze_tree_semantic_distribution()
  → node_stats (all nodes with embeddings)
  → tree_signals (dimension, counts)
  ↓
ClusterHotspotSelector.select_hotspots() [NEW]
  → Build NodeSemanticHit candidates (similarity only, no bonuses)
  → Select broader candidate set (limit * 4)
  → Walk ancestors for each candidate
  → Build ClusterCandidate records (ancestor, members, density)
  → Score clusters (max_score + avg_score + support + density)
  → Select densest meaningful ancestor
  → Return inferred hotspot region node_id
  ↓
RecursiveTreeTraversalRunner.traverse_tree_for_query()
  → start_node_id = inferred hotspot
  → hotspot_node_id = inferred hotspot
  → Policy-guided descent to evidence-bearing children
  → Build QueryHit records with hotspot metadata
  ↓
_map_query_hits_to_backend_hits() [CRITICAL PATH]
  → Preserve hotspot_node_id, navigation_node_ids, drill_depth
  → Build backend hit dicts with text_preview, heading_path, span_ids
  ↓
Returned evidence-bearing hits from inferred hotspot region
```

### Recommended Project Structure

```text
llamaindex_runtime/tree/
├── semantic_distribution.py      # Add ClusterHotspotSelector, NodeSemanticHit, ClusterCandidate
├── runtime.py                    # Add selector switch, wire cluster selector
└── evidence_content_resolver.py  # Preserve existing resolver

tests/llamaindex_runtime/
├── test_tree_semantic_hotspot.py # Add cluster selector tests
├── test_tree_runtime_traversal_integration.py # Preserve existing integration tests
└── conftest.py                   # Shared fixtures

verification/phase11-level-agnostic-hotspot-cluster-tracking/
├── validation_corpus.md          # p6 validation corpus
├── validation_status.json        # Execution results
└── evidence_chain_report.json    # Metadata rates
```

### Pattern 1: Ancestor Cluster Aggregation

**What:** For each high-similarity semantic candidate node, walk ancestor chain and accumulate cluster support metrics.

**When to use:** Cluster-based hotspot inference requires observing where hits cluster structurally after the fact.

**Example:**

```python
# Source: Phase 11 design (11-01-PLAN.md)
@dataclass(frozen=True)
class NodeSemanticHit:
    node_id: UUID
    similarity: float
    heading_path: str | None
    parent_node_id: UUID | None
    path_to_root: tuple[UUID, ...]

@dataclass(frozen=True)
class ClusterCandidate:
    ancestor_node_id: UUID
    member_node_ids: tuple[UUID, ...]
    member_scores: tuple[float, ...]
    max_score: float
    avg_score: float
    support_count: int
    subtree_candidate_count: int
    density: float

# Walk ancestors for each candidate
def _build_ancestor_clusters(
    candidates: list[NodeSemanticHit],
    node_by_id: dict[UUID, dict[str, Any]],
) -> list[ClusterCandidate]:
    ancestor_to_members: dict[UUID, list[NodeSemanticHit]] = defaultdict(list)
    for candidate in candidates:
        ancestor_chain = candidate.path_to_root
        for ancestor_id in ancestor_chain:
            ancestor_to_members[ancestor_id].append(candidate)

    # Build cluster records
    clusters = []
    for ancestor_id, members in ancestor_to_members.items():
        member_scores = tuple(m.similarity for m in members)
        # subtree_candidate_count requires knowing all candidates under this ancestor
        subtree_count = _count_subtree_candidates(
            ancestor_id=ancestor_id,
            candidates=candidates,
            node_by_id=node_by_id,
        )
        density = len(members) / subtree_count if subtree_count > 0 else 0.0
        clusters.append(
            ClusterCandidate(
                ancestor_node_id=ancestor_id,
                member_node_ids=tuple(m.node_id for m in members),
                member_scores=member_scores,
                max_score=max(member_scores),
                avg_score=sum(member_scores) / len(member_scores),
                support_count=len(members),
                subtree_candidate_count=subtree_count,
                density=density,
            )
        )
    return clusters
```

### Pattern 2: Cluster Scoring Formula

**What:** Score candidate hotspot regions by balancing max similarity, average similarity, support count, and density.

**When to use:** Selecting the densest meaningful ancestor from competing cluster candidates.

**Example:**

```python
# Source: Phase 11 design (11-01-PLAN.md)
def _score_cluster(cluster: ClusterCandidate) -> float:
    normalized_support = cluster.support_count / 20.0  # Normalize against expected max
    return (
        cluster.max_score * 0.40
        + cluster.avg_score * 0.30
        + normalized_support * 0.20
        + cluster.density * 0.10
    )

# Tie-breaking logic
def _select_best_cluster(
    clusters: list[ClusterCandidate],
) -> ClusterCandidate:
    scored_clusters = [
        (cluster, _score_cluster(cluster))
        for cluster in clusters
    ]
    scored_clusters.sort(key=lambda pair: pair[1], reverse=True)

    # Tie breakers: support_count, max_score, deeper ancestor, shorter navigation distance
    # ... implementation details
    return scored_clusters[0][0]
```

### Anti-Patterns to Avoid

- **Route-node bonus in initial scoring:** Applying `route_bonus` before cluster analysis reintroduces pre-declared role bias, defeating the level-agnostic design.
- **Root selection by default:** Selecting root when local clusters exist defeats hotspot localization; root should be penalized or excluded unless no better candidate exists.
- **Pre-declared hotspot/evidence split:** Treating nodes as "hotspot candidates" vs "evidence candidates" before similarity scoring reintroduces the Phase 10 semantic mismatch.
- **Deleting SubtreeHotspotSelector immediately:** Removing rollback capability before cluster validation passes creates irreversible commit risk.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity computation | Custom distance function | `_cosine_similarity` in semantic_distribution.py | Existing tested implementation handles dimension mismatch validation |
| Ancestor chain walking | Recursive tree traversal without guards | `_collect_subtree_values` pattern with depth/cycle guards | Phase 10 implementation proven safe with `_MAX_TRAVERSAL_DEPTH` guard |
| Backend-hit mapping | Manual dict construction | `_map_query_hits_to_backend_hits` | Existing mapping handles provenance, navigation path, text preview resolution |
| Evidence content resolution | Custom preview fallback chain | `EvidenceContentResolver.build_text_preview` | Phase 5 resolver handles registry lookup, span resolution, fallback chain |

**Key insight:** The existing semantic distribution and traversal infrastructure provides tested, validated patterns for cluster aggregation and provenance tracking. Reuse these rather than introducing new untested implementations.

## Runtime State Inventory

> Phase 11 involves algorithm change and selector switch, not rename/refactor/migration. No stored data or runtime state requires migration.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — algorithm change only | None |
| Live service config | None — selector switch is environment variable | Add `RAG_TREE_HOTSPOT_SELECTOR=cluster` to .env.example |
| OS-registered state | None | None |
| Secrets/env vars | None — no new secrets required | Document `RAG_TREE_HOTSPOT_SELECTOR` in .env.example |
| Build artifacts | None — Python source only | None |

**Nothing found in category:** Verified by reading Phase 11 scope (11-01-PLAN.md) which describes algorithm replacement, not data migration.

## Common Pitfalls

### Pitfall 1: Route-Node Bonus Creep

**What goes wrong:** Implementer accidentally transplants `_ROUTE_NODE_BONUS` logic into cluster scoring, reintroducing pre-declared role bias.

**Why it happens:** Phase 10 code patterns use `is_route_node` flag extensively, making it easy to copy route-bonus logic into new selector.

**How to avoid:** Explicitly forbid route-node bonuses in `ClusterHotspotSelector` tests; add test `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus` that validates route-like parent nodes are not preferred solely because they are route-like.

**Warning signs:** Cluster selection consistently prefers high-level parents over dense local clusters; hotspot_node_id often equals root node for diverse queries.

### Pitfall 2: Root-Bias in Cluster Scoring

**What goes wrong:** Root ancestor receives high support count because all candidates are under root, leading to root selection when no explicit penalty exists.

**Why it happens:** Cluster scoring formula weights `support_count` 20%; root naturally accumulates maximum support.

**How to avoid:** Explicit root penalty or exclusion in cluster scoring; add test `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists` that validates local ancestor wins over root when meaningful local cluster exists.

**Warning signs:** Hotspot_node_id frequently equals root node; evidence hits come from widely scattered subtrees.

### Pitfall 3: Short Exact Node Hidden by Long Related Node

**What goes wrong:** Short heading node with exact keyword match receives lower similarity than long text node with related content, causing cluster selector to prefer the long node's subtree.

**Why it happens:** Embedding similarity favors longer text when exact heading has limited token count.

**How to avoid:** Include heading path in similarity computation or validate short-node survival in tests; add test `test_short_exact_heading_node_survives_long_related_text` that validates short exact node appears in returned hits.

**Warning signs:** p6 DNA query returns long related sections instead of exact "AI产品经理核心DNA" node.

### Pitfall 4: CRITICAL Runtime Path Unintended Modification

**What goes wrong:** Editing `_retrieve_tree_hits_from_backend` or `_map_query_hits_to_backend_hits` without switch gating breaks existing `route_subtree` fallback.

**Why it happens:** These functions handle all selector paths; modifying them directly affects rollback capability.

**How to avoid:** Implement selector switch at runtime entry point before calling selector; preserve existing functions unchanged for `route_subtree` path; add explicit switch tests validating both paths work.

**Warning signs:** GitNexus detect-changes shows unexpected symbol modifications; existing Phase 10 tests fail after cluster implementation.

## Code Examples

Verified patterns from existing codebase:

### Ancestor Walking with Cycle Guard

```python
# Source: llamaindex_runtime/tree/semantic_distribution.py:266-304
def _collect_subtree_values(
    *,
    tree_nodes: Sequence[dict[str, Any]],
    direct_values: dict[UUID, list[Any]],
) -> dict[UUID, list[Any]]:
    parent_to_children = _build_parent_to_children(tree_nodes)
    cached_values: dict[UUID, list[Any]] = {}

    def collect(
        node_id: UUID,
        *,
        active_path: frozenset[UUID] = frozenset(),
        depth: int = 0,
    ) -> list[Any]:
        if depth > _MAX_TRAVERSAL_DEPTH:
            raise ValueError(
                f"tree traversal depth exceeded {_MAX_TRAVERSAL_DEPTH} at node_id={node_id}"
            )
        if node_id in cached_values:
            return cached_values[node_id]
        if node_id in active_path:
            raise ValueError(f"tree cycle detected at node_id={node_id}")

        values = list(direct_values.get(node_id, []))
        next_path = active_path | frozenset((node_id,))
        for child in parent_to_children.get(node_id, []):
            values.extend(
                collect(
                    _required_value(child, "node_id"),
                    active_path=next_path,
                    depth=depth + 1,
                )
            )
        cached_values[node_id] = values
        return values

    for node in tree_nodes:
        collect(_required_value(node, "node_id"))
    return cached_values
```

### Cosine Similarity Validation

```python
# Source: llamaindex_runtime/tree/semantic_distribution.py:898-914
def _cosine_similarity(vector_a: Sequence[float], vector_b: Sequence[float]) -> float:
    """Compute cosine similarity between same-dimensional vectors."""
    if not vector_a or not vector_b:
        return 0.0
    if len(vector_a) != len(vector_b):
        raise ValueError(
            f"vectors must share the same dimension; got {len(vector_a)} and {len(vector_b)}"
        )

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
```

### QueryHit Provenance Anchoring

```python
# Source: llamaindex_runtime/tree/semantic_distribution.py:458-476
@dataclass(frozen=True)
class QueryHit:
    """Provenance-anchored hit from tree traversal.

    This preserves all immutable provenance contracts from Phase 1.  Hotspot
    fields describe navigation provenance only; final hits still come from
    evidence-bearing chunk/span nodes.
    """

    doc_id: UUID
    version_id: UUID
    span_id: UUID
    chunk_id: UUID
    node_id: UUID
    similarity_score: float
    hotspot_node_id: UUID | None = None
    navigation_node_ids: tuple[UUID, ...] = ()
    drill_depth: int = 0
```

### Backend Hit Metadata Mapping

```python
# Source: llamaindex_runtime/tree/runtime.py:253-308
def _map_query_hits_to_backend_hits(
    *,
    query_hits: list[QueryHit],
    node_by_id: dict[Any, dict[str, Any]],
    span_ids_by_node: dict[Any, list[Any]],
    registry: Any | None = None,
    version_id: Any | None = None,
) -> list[dict[str, Any]]:
    backend_hits: list[dict[str, Any]] = []
    resolver = EvidenceContentResolver()
    seen_chunks: set[Any] = set()
    for hit in query_hits:
        if hit.chunk_id == MISSING_CHUNK_ID or hit.chunk_id in seen_chunks:
            continue
        node = node_by_id.get(hit.node_id)
        if node is None:
            continue
        span_ids = span_ids_by_node.get(hit.node_id, []) or [hit.span_id]
        fallback_text = node.get("summary_text") or node.get("title") or ""
        text_preview = fallback_text
        if registry is not None and version_id is not None:
            text_preview = resolver.build_text_preview(
                registry=registry,
                version_id=version_id,
                node_id=hit.node_id,
                span_ids=span_ids,
                fallback_text=fallback_text,
                chunk_id=hit.chunk_id,
            )
        navigation_path = [
            node_by_id[node_id].get("heading_path") or node_by_id[node_id].get("title")
            for node_id in hit.navigation_node_ids
            if node_id in node_by_id
        ]
        hit_dict = {
            "node_id": hit.node_id,
            "chunk_id": hit.chunk_id,
            "chunk_id_missing": False,
            "score": hit.similarity_score,
            "text_preview": text_preview,
            "heading_path": node.get("heading_path"),
            "span_ids": list(span_ids),
            "hotspot_node_id": hit.hotspot_node_id,
            "navigation_node_ids": list(hit.navigation_node_ids),
            "navigation_path": navigation_path,
            "drill_depth": hit.drill_depth,
            "backend_source": "tree_semantic",
            "retrieval_path": (
                "subtree_hotspot_traversal"
                if hit.hotspot_node_id is not None
                else "semantic_traversal"
            ),
        }
        backend_hits.append(hit_dict)
        seen_chunks.add(hit.chunk_id)
    return backend_hits
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pre-ranked route-node hotspot selection with route bonuses | Level-agnostic cluster-based inference | Phase 11 (planned) | Removes route-node bias; hotspot meaning shifts from preclassified to inferred |
| Direct similarity scoring on prototype embeddings | Cluster scoring formula balancing max/avg/density | Phase 11 (planned) | Enables densest-local-region selection instead of highest-parent selection |
| Route/evidence predeclared role split | All nodes compete equally first | Phase 11 (planned) | Eliminates semantic mismatch between intended behavior and implemented behavior |

**Deprecated/outdated:**

- `_ROUTE_NODE_BONUS` logic in `SubtreeHotspotSelector` — will be preserved as fallback but deprecated as default path
- `is_route_node` flag usage in hotspot scoring — will remain for `route_subtree` fallback but not used in `cluster` path

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cosine similarity computation remains valid for cluster scoring | Standard Stack | LOW — existing `_cosine_similarity` function tested in Phase 10 |
| A2 | Ancestor walking with cycle/depth guards sufficient for cluster aggregation | Architecture Patterns | LOW — `_collect_subtree_values` pattern validated in Phase 10 |
| A3 | Cluster scoring formula weights (max 40%, avg 30%, support 20%, density 10%) are reasonable starting values | Cluster Scoring Formula | MEDIUM — requires empirical validation on p6 corpus |
| A4 | Root penalty or exclusion logic required to avoid root-bias | Pitfall 2 | MEDIUM — exact penalty magnitude requires experimentation |
| A5 | Heading path inclusion in similarity computation may improve short-node survival | Pitfall 3 | MEDIUM — optional enhancement, may not be required if density scoring captures local clusters |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions

1. **Heading path augmentation for similarity**

   - What we know: Short exact heading nodes may receive lower similarity than long related text nodes due to embedding token count differences.
   - What's unclear: Whether cluster density scoring alone captures local exact-node clusters, or whether heading path text augmentation is required.
   - Recommendation: Implement baseline cluster selector without heading augmentation; if p6 DNA query fails to return exact node, add heading augmentation in follow-up task.

2. **Cluster candidate threshold**

   - What we know: Phase 11 design suggests `candidate_top_n = max(similarity_top_k * 4, 20)`.
   - What's unclear: Whether this multiplier is optimal for diverse query types; may need dynamic threshold based on similarity distribution.
   - Recommendation: Start with fixed multiplier; add validation artifacts comparing top-N values on p6 corpus.

3. **Root penalty magnitude**

   - What we know: Root should be penalized or excluded unless no better candidate exists.
   - What's unclear: Exact penalty magnitude; whether 0.06 root penalty from Phase 10 transfers well to cluster scoring.
   - Recommendation: Add configurable root penalty parameter; validate against p6 corpus with penalty values 0.05, 0.06, 0.10.

## Environment Availability

> Phase 11 requires Python runtime and PostgreSQL for DB-backed validation. External dependencies checked.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Runtime execution | ✓ | 3.11 | — |
| PostgreSQL | DB-backed validation | ✓ | Docker Desktop | In-memory mock for fixture tests |
| pytest | Test execution | ✓ | 7.x | — |
| psycopg | PostgreSQL connection | ✓ | 3.x | — |

**Missing dependencies with no fallback:**

- None — all dependencies available.

**Missing dependencies with fallback:**

- None — PostgreSQL available via Docker Desktop (Phase 10 validated).

## Validation Architecture

> Nyquist validation enabled (workflow.nyquist_validation absent = enabled per spec).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | tests/conftest.py |
| Quick run command | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -x` |
| Full suite command | `pytest tests/llamaindex_runtime/ -x --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-11-NO-ROUTE-BONUS | Cluster selector scores all nodes without route-node bonus | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestClusterHotspotSelector::test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus -x` | ❌ Wave 0 |
| REQ-11-DENSEST-ANCESTOR | Cluster selector selects densest shared ancestor | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestClusterHotspotSelector::test_cluster_hotspot_selector_selects_densest_shared_ancestor -x` | ❌ Wave 0 |
| REQ-11-ROOT-AVOIDANCE | Cluster selector avoids root when local cluster exists | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestClusterHotspotSelector::test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists -x` | ❌ Wave 0 |
| REQ-11-SHORT-NODE | Short exact heading node survives long related text | unit | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestClusterHotspotSelector::test_short_exact_heading_node_survives_long_related_text -x` | ❌ Wave 0 |
| REQ-11-P6-REGRESSION | p6 DNA query returns 数据驱动, 非确定性, 持续性 | integration | `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestClusterHotspotSelector::test_p6_ai_product_manager_core_dna_routes_to_product_characteristics -x` | ❌ Wave 0 |
| REQ-11-SWITCH-GATE | Selector switch gates cluster vs route_subtree | unit | `pytest tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py::TestSelectorSwitch -x` | ❌ Wave 0 |
| REQ-11-METADATA-RATE | Hotspot metadata rate ≥ 0.90 | validation | `python verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_runner.py` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -x`
- **Per wave merge:** `pytest tests/llamaindex_runtime/ -x --tb=short`
- **Phase gate:** Full suite green + DB-backed validation runner passing + GitNexus detect-changes reviewed.

### Wave 0 Gaps

- [ ] `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` — add `TestClusterHotspotSelector` class with 5 tests
- [ ] `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` — add `TestSelectorSwitch` class
- [ ] `verification/phase11-level-agnostic-hotspot-cluster-tracking/` — validation runner, corpus, status artifacts
- [ ] Framework install: N/A — pytest already installed

*(Existing test infrastructure covers traversal integration and hotspot metadata mapping; Wave 0 adds cluster-selector-specific tests and validation runner)*

## Security Domain

> Security enforcement enabled (absent = enabled per spec).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no authentication in Phase 11 scope) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Environment variable validation for `RAG_TREE_HOTSPOT_SELECTOR` |
| V6 Cryptography | no | — (no cryptographic operations) |

### Known Threat Patterns for Semantic Retrieval

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Environment variable injection | Tampering | Validate against allowed values: `route_subtree`, `cluster` |
| SQL injection via registry methods | Tampering | Registry methods use parameterized queries (Phase 1-10 pattern) |
| Provenance fabrication | Spoofing | QueryHit immutable dataclass with UUID anchors (Phase 10 pattern) |
| Unbounded traversal depth | Denial of Service | `_MAX_TRAVERSAL_DEPTH` guard (Phase 10 pattern) |
| Cyclic tree relationship | Denial of Service | Cycle detection in ancestor walking (Phase 10 pattern) |

## Sources

### Primary (HIGH confidence)

- Phase 11 design document: `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-01-PLAN.md` — algorithm specification, TDD targets, validation corpus
- Existing implementation: `llamaindex_runtime/tree/semantic_distribution.py` — ancestor walking, cosine similarity, QueryHit provenance
- Existing implementation: `llamaindex_runtime/tree/runtime.py` — backend-hit mapping, selector integration
- Existing tests: `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` — hotspot navigation integration tests
- Existing tests: `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` — runtime integration tests

### Secondary (MEDIUM confidence)

- Phase 10 validation: `scripts/demo_hotspot_semantic_retrieval.py` — DB-backed whitebox demo pattern
- Phase 10 artifacts: `.planning/phases/10-hotspot-semantic-retrieval-validation/10-RESEARCH.md` — hotspot semantic change context

### Tertiary (LOW confidence)

- None — all critical patterns verified from existing codebase.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all dependencies are stdlib or existing project packages.
- Architecture: HIGH — ancestor walking, cosine similarity, and provenance patterns validated in Phase 10.
- Pitfalls: HIGH — route-node bonus creep, root-bias, and CRITICAL path risks documented in Phase 11 design.

**Research date:** 2026-06-17
**Valid until:** 30 days — Python stdlib and project patterns are stable; cluster scoring formula may require empirical tuning.