# Compatibility Adapter Program — Frozen Interfaces

## Provenance Contracts (Do Not Change)

- `doc_id`
- `version_id`
- `span_id`
- `chunk_id`
- `node_id`
- `entity_id`
- `relation_id`
- `evidence_id`
- `QueryHit`

## Planned Local Interfaces

### TreeBackendAdapter
Purpose: donor-backed tree build / retrieval path.

### TreeSemanticDistributionAdapter
Purpose: compute semantic distribution statistics inside the persisted tree.

Expected outputs include:
- `node_id`
- `span_ids`
- `chunk_ids`
- centroid vector
- dispersion
- entropy
- support_count
- optional subtree signals

### TreeBranchDecisionPolicy
Purpose: consume semantic distribution statistics and decide:
- drill down
- prune
- keep parent
- expand siblings / adjacent structures (future)

## Donor-to-Seam Mapping

### Psi-RAG
Use as donor for:
- traversal skeleton
- node/tree semantic representation
- prototype embedding idea

### HIRO
Use as donor for:
- recursive decision skeleton
- dual-threshold design pattern

### RAPTOR
Use as donor for:
- semantic cluster-tree construction ideas
- collapsed-tree retrieval structure

### PageIndex
Use as donor for:
- structural tree build
- tree retrieval line only

### LightRAG / RAG-Anything
Do not use in the active tree-semantic-distribution line.

## Integration Rule

Donor outputs must always be mapped back into local IDs and local storage contracts. No donor result may bypass registry write-back or final `QueryHit` normalization.
