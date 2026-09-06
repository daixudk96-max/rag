# Phase 11 Plan — Level-Agnostic Hotspot Cluster Tracking

## Status

- **Phase:** 11
- **Name:** Level-Agnostic Hotspot Cluster Tracking
- **Mode:** Corrective implementation plan
- **Source:** User design correction after Phase 10 hotspot validation discussion
- **Created:** 2026-06-17
- **Implementation status:** Not started

## Phase Goal

Replace the current pre-ranked route-node hotspot selection with a **level-agnostic, post-hoc cluster-based hotspot tracking algorithm**.

The intended behavior is:

```text
query embedding
→ compare against all eligible nodes equally
→ collect top semantic hits across the tree
→ analyze where those hits cluster structurally
→ infer the densest shared parent/local subtree after the fact
→ read from that inferred hotspot area
```

No node should be treated as a hotspot merely because it is a parent, route node, or has no direct chunks.

## Why This Phase Exists

Phase 10 proved that the retrieval pipeline can carry hotspot metadata and evidence-chain metadata:

- `hotspot_node_id`
- `navigation_path`
- `drill_depth`
- evidence-bearing chunks
- subtree traversal metadata

However, the current implementation does **not** match the intended hotspot semantics. The current implementation is closer to:

```text
preselect route-like nodes
→ apply route bonus
→ treat selected route node as hotspot
→ traverse children
```

The intended design is:

```text
all nodes compete equally
→ observe semantic hit distribution
→ infer hotspot from where hits cluster
```

This phase corrects that semantic mismatch before treating hotspot tracking as product-complete.

## Current Design Mismatch

### Current implementation

Relevant files:

- `llamaindex_runtime/tree/runtime.py`
- `llamaindex_runtime/tree/semantic_distribution.py`

Current flow in `runtime.py`:

```python
hotspots = SubtreeHotspotSelector().select_hotspots(...)
```

`SubtreeHotspotSelector` currently uses logic equivalent to:

```python
is_route_node = bool(stats.get("is_route_node"))
route_bonus = _ROUTE_NODE_BONUS if is_route_node else 0.0
score = similarity + route_bonus + depth_bonus + support_bonus - root_penalty
```

And `is_route_node` is derived from:

```python
"is_route_node": not direct_chunk_ids and bool(subtree_chunk_ids)
```

This implicitly distinguishes:

- route/hotspot-like parent nodes
- direct evidence/content nodes

That is a pre-declared role split. The target design requires no such pre-role split.

## Target Design

### Required behavior

1. Compute similarity for all eligible nodes.
2. Do not apply route-node bonus.
3. Do not prefer parent nodes by default.
4. Select a broader candidate set, for example:

```python
candidate_top_n = max(similarity_top_k * 4, 20)
```

5. Group high-similarity hits by ancestors.
6. Score candidate hotspot regions by cluster strength.
7. Pick the densest meaningful local region.
8. Return:
   - hotspot region node
   - concrete evidence nodes inside that region
   - navigation path from inferred hotspot to returned evidence

## Key Semantic Change

### Old semantics

```text
hotspot_node_id = node preselected as route/hotspot
node_id = evidence node found under that hotspot
```

### New semantics

```text
hotspot_node_id = post-hoc inferred cluster/root region
node_id = concrete semantic hit or evidence node inside that cluster
```

`hotspot_node_id` remains useful, but its meaning changes:

```text
not "this was pre-classified as a hotspot"
but "this is the shared region where semantic hits clustered"
```

## Proposed Algorithm

### Step 1 — Build candidate node scores

For every eligible node:

```python
similarity = cosine_similarity(query_embedding, node_embedding)
```

No bonuses:

- no route bonus
- no depth bonus in initial score
- no parent/child preference
- no direct/indirect chunk preference

Output shape:

```python
NodeSemanticHit(
    node_id,
    similarity,
    heading_path,
    parent_node_id,
    path_to_root,
)
```

### Step 2 — Select semantic candidates

Take top candidate nodes:

```python
candidate_top_n = max(limit * 4, 20)
```

Initial threshold:

```python
min_similarity_threshold = 0.0
```

Optional later threshold:

```python
relative_threshold = top_score * 0.65
```

### Step 3 — Build ancestor clusters

For each candidate hit, walk ancestors.

Example tree:

```text
root
└── 00:31 - 产品特性对比
    ├── 传统软件比喻
    ├── AI时代产品特性
    └── AI产品经理核心DNA
```

Each ancestor receives support from descendant hits.

Cluster record:

```python
ClusterCandidate(
    ancestor_node_id,
    member_node_ids,
    member_scores,
    max_score,
    avg_score,
    support_count,
    subtree_candidate_count,
    density,
)
```

### Step 4 — Score clusters

Recommended scoring formula:

```python
cluster_score = (
    max_score * 0.40
    + avg_score * 0.30
    + normalized_support_count * 0.20
    + density * 0.10
)
```

Where:

```python
density = support_count / subtree_candidate_count
```

Important constraints:

- root is penalized or excluded unless no better candidate exists
- prefer the smallest meaningful ancestor when scores are close
- do not select an ancestor only because it is high-level

### Step 5 — Select hotspot region

Choose the cluster with highest `cluster_score`.

Tie breakers:

1. higher support count
2. higher max score
3. smaller/deeper ancestor region
4. shorter navigation distance to strongest hit

### Step 6 — Return evidence nodes

Inside selected hotspot region, return:

- strongest direct semantic hits
- nearby sibling nodes when needed for context
- enough nodes to satisfy `similarity_top_k`

Example query:

```text
AI产品经理的核心DNA是什么？
```

Expected selected hotspot region:

```text
AI产品经理项目实战与深度思考架构分析
> 00:31 - 产品特性对比
```

Expected returned evidence includes:

```text
AI产品经理核心DNA
- 数据驱动
- 非确定性
- 持续性
```

## Affected Files

### Primary implementation

#### `llamaindex_runtime/tree/semantic_distribution.py`

Add or equivalent:

```python
ClusterHotspotSelector
ClusterCandidate
NodeSemanticHit
```

Modify or supplement existing:

```python
SubtreeHotspotSelector
RecursiveTreeTraversalRunner
QueryHit
```

Do not remove the old selector immediately. Keep it as fallback until validation passes.

#### `llamaindex_runtime/tree/runtime.py`

Add selector switch:

```text
RAG_TREE_HOTSPOT_SELECTOR=cluster
```

Supported values:

```text
route_subtree   # existing behavior
cluster         # new behavior
```

Recommended default after tests pass:

```text
cluster
```

### Validation scripts

Create or adapt validation path:

```text
verification/phase11-level-agnostic-hotspot-cluster-tracking/
```

Required query:

```text
AI产品经理的核心DNA是什么？
```

Expected result must contain:

```text
数据驱动
非确定性
持续性
```

### Tests

Likely location:

```text
tests/llamaindex_runtime/
```

Add tests for:

- cluster selector
- ancestor grouping
- short exact node recovery
- no route bonus behavior
- p6-style regression fixture

## Required Impact Analysis Before Edits

Project instructions require GitNexus impact analysis before editing symbols.

Before modifying these symbols, run impact analysis:

```text
SubtreeHotspotSelector
RecursiveTreeTraversalRunner
QueryHit
_retrieve_tree_hits_from_backend
_map_query_hits_to_backend_hits
```

Required report before edit:

```text
symbol
direct callers
affected processes
risk level
decision
```

If GitNexus reports HIGH or CRITICAL risk, surface it before editing.

## TDD Plan

### Test 1 — all nodes compete equally

Name:

```text
test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus
```

Given:

- one route-like parent node
- one direct child node
- same or lower similarity on route node

Expect:

- route-like parent is not preferred solely because it is route-like

### Test 2 — shared ancestor cluster wins

Name:

```text
test_cluster_hotspot_selector_selects_densest_shared_ancestor
```

Given:

```text
A
├── A1 high hit
├── A2 high hit
└── A3 medium hit

B
└── B1 highest single hit
```

Expect:

```text
hotspot = A
```

because the cluster under A is stronger overall than one isolated hit under B.

### Test 3 — root is not selected too eagerly

Name:

```text
test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists
```

Given:

- root contains all hits
- a local ancestor contains most hits

Expect:

```text
hotspot = local ancestor
```

### Test 4 — short exact node is not hidden by long related node

Name:

```text
test_short_exact_heading_node_survives_long_related_text
```

Given:

Short node:

```text
AI产品经理核心DNA
数据驱动 / 非确定性 / 持续性
```

Long related node:

```text
AI产品经理的思考方向 / 数据飞轮 / 用户行为...
```

Query:

```text
AI产品经理的核心DNA是什么？
```

Expect:

- short exact node appears in returned hits
- selected hotspot is its local parent or itself
- long related node does not steal the whole hotspot

### Test 5 — p6 regression

Name:

```text
test_p6_ai_product_manager_core_dna_routes_to_product_characteristics
```

Expected:

```text
hotspot_path contains "00:31 - 产品特性对比"
returned text contains "数据驱动"
returned text contains "非确定性"
returned text contains "持续性"
```

## Validation Plan

### Validation corpus

Use:

```text
verification/p6_validation/p6_final_sample_structured.md
```

### Required query set

Include at least:

```text
AI产品经理的核心DNA是什么？
传统软件和AI产品的输出特点有什么区别？
AI产品的智能来源是什么？
什么是数据闭环飞轮？为什么它重要？
抖音如何利用用户行为数据优化推荐？
特斯拉如何收集自动驾驶数据？
AI产品落地时第一个要思考的问题是什么？
如何处理不干净的数据？
李菲菲在AI 1.0时代遇到了什么数据问题？
独家数据为什么是真正的护城河？
```

### Pass criteria

Functional:

```text
query_failures = 0
total_hits > 0
hotspot_metadata_rate >= 0.90
navigation_path_rate >= 0.90
empty_preview_hits = 0
```

Semantic:

```text
Q: AI产品经理的核心DNA是什么？
must return:
- 数据驱动
- 非确定性
- 持续性
```

Hotspot behavior:

```text
Selected hotspot should be:
00:31 - 产品特性对比
or AI产品经理核心DNA itself if selector chooses exact local node
```

It must **not** select unrelated regions as the primary hotspot for the DNA query:

```text
05:40 - 抖音案例
04:40 - 数据工作重要性
06:29 - 特斯拉案例
```

## Non-Goals

This phase should not attempt to solve everything at once.

Do not include:

- full quality Level promotion
- human judgment collection
- UI changes
- broad ingestion redesign
- replacing embedding model globally
- committing unrelated dirty-tree files
- deleting old selector immediately

Possible later improvements:

- title/heading-path text augmentation
- BM25 + vector hybrid retrieval
- reranking with cross-encoder
- LLM rerank over candidate clusters

## Rollback Strategy

Keep existing selector available:

```text
RAG_TREE_HOTSPOT_SELECTOR=route_subtree
```

If cluster selector causes regression:

```text
RAG_TREE_HOTSPOT_SELECTOR=route_subtree
```

restores current Phase 10 behavior.

## Done Criteria

Phase 11 is complete only when:

- tests for cluster selector pass
- route-node bonus is no longer part of the new default path
- p6 DNA query returns the correct core DNA content
- validation artifacts show evidence-bearing hits
- navigation path still works
- old selector remains available as fallback
- code review passes
- security review finds no critical/high findings
- GitNexus detect-changes is run before commit

## Next Action

Proceed to implementation planning/execution for Phase 11 using TDD:

1. run required GitNexus impact analysis before editing symbols
2. write failing tests for cluster-based hotspot selection
3. implement `ClusterHotspotSelector`
4. wire selector behind `RAG_TREE_HOTSPOT_SELECTOR=cluster`
5. rerun p6 validation
6. review and verify
