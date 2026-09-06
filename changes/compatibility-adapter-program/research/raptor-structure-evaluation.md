# RAPTOR Structure Donor Reference Evaluation

## Context
- Phase 1 baseline: PersistedTreeSemanticDistributionAdapter + BaselineTreeBranchDecisionPolicy
- Phase 2: Psi-RAG/HIRO evaluated → NO transplantation (architectural mismatch)
- Local traversal runner: implemented (not from Psi-RAG transplant)

## What We Need (per 02-INTERFACES.md)
- semantic cluster-tree construction ideas
- collapsed-tree retrieval structure

## RAPTOR Concept Analysis

### Core Ideas
1. **Cluster-based tree construction**: Group related nodes via clustering, build tree from clusters
2. **Collapsed retrieval**: Retrieve at multiple tree levels (leaf nodes + collapsed parent nodes)
3. **Semantic summarization**: Generate summaries for collapsed nodes

### Local vs RAPTOR Gap Analysis

| RAPTOR Feature | Local Phase 1 + Traversal | Gap |
|----------------|--------------------------|-----|
| Cluster-based tree | ❌ Not implemented | Tree structure from registry (not cluster-based) |
| Collapsed retrieval | ✅ Traversal runner | Can traverse multiple levels |
| Semantic summarization | ❌ Not implemented | No summarization logic |

### Critical Missing Piece
**None** - RAPTOR is listed as "third donor, only for reference", meaning we should only use it as a comparison point, not for transplantation.

## Transplantation Decision

**Decision: NO transplant (reference only)**

### What NOT to Transplant
1. **Cluster-based tree construction**: Local tree structure comes from PostgreSQL registry (frozen contract), not from clustering
2. **RAPTOR summarization**: Not required for our distribution analysis seam

### What to Use as Reference
1. **Collapsed retrieval pattern**: Compare our traversal runner's multi-level descent vs RAPTOR's collapsed retrieval
2. **Cluster-tree visualization**: Reference RAPTOR's tree visualization techniques for demo/debug

### Rationale
- RAPTOR is explicitly listed as "tertiary donor, only for reference" in frozen priority
- RAPTOR's cluster-based construction would violate PostgreSQL registry source-of-truth contract
- Phase 1 + traversal runner already covers multi-level retrieval

## Test Strategy
No transplantation tests needed - RAPTOR is reference only.

## Implementation Plan
None - RAPTOR serves as conceptual reference only.

## Exit Criteria Met
✅ Research report exists comparing RAPTOR structure vs local implementation
✅ Decision made: NO transplantation (reference only)
✅ Rationale: RAPTOR is tertiary donor, local baseline sufficient