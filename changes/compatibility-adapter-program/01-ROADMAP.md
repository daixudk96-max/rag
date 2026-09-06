# Compatibility Adapter Program — Roadmap Snapshot

## Mainline Route

### Line A — Tree build / retrieval
- Primary donor: `PageIndex`
- Purpose: stronger structural tree build and tree retrieval
- Reason: mature tree-oriented logic, but not a vector-distribution engine

### Line B — Tree-internal vector distribution
- Primary donor reference: `Psi-RAG`
- Secondary donor reference: `HIRO`
- Tertiary donor reference: `RAPTOR`
- Purpose: analyze semantic concentration / dispersion inside the tree without forcing direct answer retrieval from this lane

### Line C — Graph / graph-text
- Status: paused
- Future donor: `LightRAG`
- Only reopen after Line A + Line B stabilize

### Line D — Multimodal enhancement
- Status: paused
- Future donor: `RAG-Anything`
- Only reopen after graph branch is intentionally reactivated

## What was confirmed from local donor validation

### Psi-RAG
- strong donor for tree structure + node embeddings + traversal skeleton
- not a ready-made distribution-statistics producer

### HIRO
- strong donor for recursive decision skeleton and dual-threshold design
- not a producer of centroid / entropy / dispersion

### RAPTOR
- strong donor for cluster-tree construction and collapsed-tree retrieval
- secondary donor for current needs

### PageIndex
- strong donor for page/TOC-style tree build and retrieval
- not suitable as the primary tree-internal vector distribution donor

## Integration Phase Sequence

### Phase 4 — PageIndex tree adapter landing
- implement `PageIndexTreeAdapter`
- make the structural tree path runnable through the local `TreeBackendAdapter` seam
- preserve local `tree_nodes` / `tree_node_spans` write-back
- prove white-box traceability back to local `span_id`

### Phase 5 — Psi-RAG donor integration
- transplant only the selected traversal / node semantic representation logic
- do not transplant donor-native storage or IDs
- wire the selected logic into the local tree-semantic-distribution lane
- keep the local baseline implementation as fallback and comparison target

### Phase 6 — HIRO decision-layer integration
- transplant only the recursive decision skeleton and dual-threshold pattern
- convert distance-based thresholding into distribution-based branch decisions
- keep decision output aligned with local provenance and local node identities

### Phase 7 — Consolidation, verification, and default-path decision
- run white-box demos on real documents
- compare donor-integrated path vs local baseline
- verify provenance integrity, tests, Sonar, and GitNexus reindex
- decide whether the integrated path is ready to become the default path

### Phase 8 — donor default-path promotion
- stabilize real-document donor operation under valid LLM credentials
- prove repeated real-document runs without donor fallback/stub
- compare donor-integrated path against baseline for retrieval quality and provenance integrity
- decide whether donor-integrated path is ready to replace baseline as the default active path
- if donor path is still unstable, document blocking factors and keep baseline as default

## Current Program Sequence

1. keep frozen adapter contracts unchanged
2. preserve the local baseline implementation as fallback and comparison target
3. complete Phase 4a (LlamaIndex unified LLM integration)
4. complete Phase 4b (`PageIndexTreeAdapter` landing)
5. complete Phase 5 (selected `Psi-RAG` donor integration)
6. complete Phase 6 (selected `HIRO` decision-layer integration)
7. complete Phase 7 (consolidation / verification / default-path decision)
8. complete Phase 8 (donor default-path promotion or explicit deferral with evidence)
9. only after that, consider whether any paused graph or multimodal branch should be reopened
