# HIRO Skeleton Transplantation Evaluation

## Context
- Phase 1 baseline: BaselineTreeBranchDecisionPolicy with distribution-based thresholds
- Current capability: decide "drill_down", "keep_parent", "prune" based on dispersion/entropy
- Threshold type: distribution-based (NOT distance-based)

## What We Need (per 02-INTERFACES.md)
- recursive decision skeleton
- dual-threshold design pattern

## HIRO Concept Analysis

### Recursive Decision Skeleton
HIRO-style decision typically involves:
1. **Recursive evaluation**: `evaluate_children()` called recursively on each subtree
2. **Dual-threshold pattern**: two thresholds (e.g., relevance_threshold, coverage_threshold)
3. **Decision outcomes**: keep, split, merge, prune based on dual criteria
4. **Aggregation**: results aggregated bottom-up or top-down

### HIRO Threshold Type
- HIRO may use **distance-based thresholds** (e.g., Euclidean distance between query embedding and node prototype)
- Phase 1 baseline uses **distribution-based thresholds** (dispersion, entropy)
- **Critical constraint**: we must NOT blindly transplant distance-based logic

### Local vs HIRO Gap Analysis

| HIRO Feature | Local Phase 1 Baseline | Gap |
|--------------|------------------------|-----|
| Recursive evaluation | ❌ Not implemented | Policy decides per-node, but no recursive aggregation |
| Dual-threshold pattern | ✅ Already implemented | dispersion_threshold + entropy_threshold |
| Decision outcomes | ✅ Partial match | "drill_down", "keep_parent", "prune" vs HIRO's "keep/split/merge/prune" |
| Threshold type | ❌ NOT compatible | HIRO distance-based vs our distribution-based |
| Aggregation logic | ❌ Not implemented | No bottom-up/top-down result aggregation |

### Critical Missing Piece
**Recursive aggregation skeleton**: Phase 1 policy decides per-node, but does NOT:
- Aggregate child subtree results up to parent
- Propagate decision context down to children
- Combine evidence from visited subtrees

## Transplantation Decision

**Decision: PARTIAL transplant**

### What to Transplant
1. **Recursive evaluation skeleton** (NEW code):
   - Call policy recursively on child subtrees
   - Aggregate child results up to parent
   - Propagate traversal context
   
### What NOT to Transplant
1. **Distance-based thresholds**: Phase 1 already has distribution-based thresholds (MUST keep)
2. **Dual-threshold parameters**: Phase 1 already has dispersion_threshold + entropy_threshold

### What to Adapt
1. **Decision outcomes**: Phase 1 has "drill_down/keep_parent/prune", may need to add "split/merge" if needed
2. **Aggregation logic**: implement bottom-up aggregation compatible with distribution-based decisions

### Transplantation Strategy
1. Enhance `BaselineTreeBranchDecisionPolicy` with recursive aggregation:
   ```python
   def evaluate_subtree(
       node_id: UUID,
       node_stats: dict[str, Any],
       child_stats: list[dict[str, Any]],
       tree_signals: dict[str, Any],
   ) -> dict[str, Any]:
       # Recursively evaluate children
       # Aggregate child decisions up to parent
       # Return subtree-level decision
   ```

### Adaptation Required
- HIRO may evaluate **all children simultaneously** (batch evaluation)
- Phase 1 baseline evaluates **one node at a time**
- **Adaptation**: add batch evaluation mode if traversal needs it

## Test Strategy
1. Test recursive evaluation on multi-level tree
2. Test aggregation combines child decisions correctly
3. Test distribution-based thresholds preserved (NOT distance-based)
4. Test provenance preserved (all decisions based on registry data)

## Implementation Plan
1. Add `evaluate_subtree` method to policy
2. Implement recursive aggregation logic
3. Integrate with traversal runner (from Psi-RAG transplant)
4. Write tests proving aggregation correctness
5. White-box demo: show recursive evaluation on real tree

## Rationale
- Phase 1 policy is **sufficient for per-node decisions**
- HIRO recursive aggregation fills the missing gap: subtree-level decisions
- Transplantation is **worth it** because it enables hierarchical retrieval
- **Low risk**: only adds aggregation logic, preserves distribution-based thresholds
- **Medium adaptation**: must ensure NOT to copy distance-based threshold logic