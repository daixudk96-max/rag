# Psi-RAG Skeleton Transplantation Evaluation

## Context
- Phase 1 baseline: PersistedTreeSemanticDistributionAdapter + BaselineTreeBranchDecisionPolicy
- Current capability: compute centroid, dispersion, entropy, support_count per node
- Decision policy: distribution-based thresholds (NOT distance-based)

## What We Need (per 02-INTERFACES.md)
- traversal skeleton
- node/tree semantic representation
- prototype embedding idea

## Psi-RAG Concept Analysis

### Traversal Skeleton
Psi-RAG-style traversal typically involves:
1. **Recursive tree descent**: start from root, recursively visit children
2. **Semantic-guided path selection**: at each node, evaluate which subtree to explore based on query embedding similarity
3. **Prototype-based representation**: each node represented by prototype embedding (centroid of chunk embeddings)
4. **Early stopping**: stop descent when semantic concentration threshold met

### Local vs Psi-RAG Gap Analysis

| Psi-RAG Feature | Local Phase 1 Baseline | Gap |
|----------------|------------------------|-----|
| Tree traversal | ❌ Not implemented | Only computes per-node stats, no traversal logic |
| Node prototype embedding | ✅ Already `centroid` | No gap - Phase 1 already computes this |
| Semantic representation | ✅ Already distribution stats | No gap - Phase 1 already computes this |
| Guided descent | ❌ Not implemented | Policy decides "drill_down" but no traversal loop |
| Early stopping | ✅ Policy "prune" decision | Partial gap - policy exists but no traversal loop |

### Critical Missing Piece
**Traversal loop skeleton**: Phase 1 computes stats per-node, but does NOT:
- Start from root and recursively descend
- Accumulate evidence across visited nodes
- Use decision policy to guide traversal path
- Return aggregated retrieval results

## Transplantation Decision

**Decision: PARTIAL transplant**

### What to Transplant
1. **Traversal skeleton structure** (NEW code):
   - Recursive descent loop
   - Node visitation order (depth-first vs breadth-first)
   - Evidence accumulation across visited nodes
   
### What NOT to Transplant (Phase 1 Already Has)
1. **Node prototype embedding**: Phase 1 `centroid` already computes this
2. **Semantic distribution stats**: Phase 1 already computes dispersion, entropy, support_count
3. **Decision thresholds**: Phase 1 already has distribution-based thresholds

### Transplantation Strategy
1. Create `TreeSemanticTraversalRunner` class
2. Use `PersistedTreeSemanticDistributionAdapter` to compute node stats
3. Use `BaselineTreeBranchDecisionPolicy` to guide traversal decisions
4. Implement recursive descent loop:
   ```python
   def traverse_tree_for_query(
       version_id: UUID,
       query_embedding: list[float],
       registry: SemanticDistributionRegistry,
       policy: TreeBranchDecisionPolicy,
   ) -> list[QueryHit]:
       # Start from root nodes
       # Recursively visit children based on policy decisions
       # Accumulate evidence (chunk_ids, span_ids)
       # Return QueryHit list
   ```

### Adaptation Required
- Psi-RAG may use **query-dependent traversal** (compare query embedding to node centroids)
- Phase 1 baseline is **query-independent** (just computes distribution stats)
- **Adaptation**: add query embedding parameter to traversal, use similarity scoring to prioritize child nodes

## Test Strategy
1. Test traversal starts from root nodes
2. Test policy guides descent decisions
3. Test evidence accumulation across visited nodes
4. Test returns QueryHit list with provenance (doc_id, version_id, span_id, chunk_id, node_id)
5. Test does NOT bypass registry (all evidence comes from persisted tables)

## Implementation Plan
1. Define `TreeSemanticTraversalRunner` protocol + implementation
2. Add query embedding parameter to traversal
3. Implement recursive descent with policy decisions
4. Integrate with Phase 1 adapter + policy
5. Write tests proving provenance preservation
6. White-box demo: show traversal path on real document

## Rationale
- Phase 1 baseline is **sufficient for node stats**, but **insufficient for retrieval**
- Psi-RAG traversal skeleton fills the missing gap: retrieval loop
- Transplantation is **worth it** because it enables end-to-end tree retrieval
- **Low risk**: only adds traversal loop, does NOT change Phase 1 provenance contracts