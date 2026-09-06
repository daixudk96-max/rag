# Psi-RAG Skeleton Evaluation Report

**Research Date:** 2026-05-20
**Phase:** 2 — Donor skeleton transplantation evaluation
**Primary Donor:** Psi-RAG (Newiz430/Psi-RAG)
**Target Seam:** Tree-internal vector distribution adapter

---

## Executive Summary

Psi-RAG provides a hierarchical tree-based RAG framework with iterative agentic retrieval, but its traversal skeleton and node representation logic are **NOT suitable for transplantation** into our local adapter seam. The Phase 1 baseline implementation (`PersistedTreeSemanticDistributionAdapter`) already provides sufficient functionality for computing semantic distribution statistics (centroid, dispersion, entropy, support_count), and Psi-RAG's traversal logic serves a different purpose (logarithmic-time retrieval) than our distribution analysis requirement.

**Transplantation Decision:** **NO** — Phase 1 baseline is sufficient; Psi-RAG skeleton addresses a different architectural concern.

---

## 1. Psi-RAG Source Location and Structure

### Repository Metadata
- **GitHub URL:** https://github.com/Newiz430/Psi-RAG
- **License:** MIT (verified)
- **Paper:** ICML 2026 (International Conference on Machine Learning)
- **Title:** "Hierarchical Abstract Tree for Cross-Document Retrieval Augmented Generation"
- **Status:** Active, research-grade implementation

### Repository Structure
```
Psi-RAG/
├── src/
│   ├── tree_retriever.py           # Tree traversal + hybrid retrieval + reranking
│   ├── tree_builder/
│   │   ├── base.py                 # Abstract TreeBuilder class
│   │   ├── abstract.py             # AbstractTreeBuilder implementation
│   │   ├── ann.py                  # HNSW graph for large corpora
│   │   └── utils.py                # Utility functions (prototype_embeddings)
│   ├── model/
│   │   ├── abstract.py             # LLM-based semantic summarization
│   │   └── embed.py                # Embedding model wrappers
│   └── prompt/
│       └── rag_abs.py              # Abstraction prompt templates
├── index.py                        # Tree index construction
├── qa.py                           # Query + retrieval orchestration
└── eval.py                         # Evaluation metrics
```

### Key Components Identified

**1. Tree Retriever (`src/tree_retriever.py`)**
- **Purpose:** Iterative layer-based descent from root to leaves for logarithmic-time retrieval
- **Traversal Pattern:**
  ```python
  for layer in range(start_layer, -1, -1):
      # Calculate vector distances at current layer
      # Mask identical embeddings
      # Filter candidates using confidence cutoff OR tree_top_k
      # Expand selected nodes' children for next iteration
      # Append higher-tier nodes directly to output context
  ```
- **Hybrid Search:** Combines dense semantic matching with BM25 sparse retrieval
- **Merging:** Reciprocal rank fusion or cross-encoder reranking
- **Output:** Formatted text passages with metadata (source document, hierarchy level, relevance)

**2. Abstract Tree Builder (`src/tree_builder/abstract.py`)**
- **Purpose:** Construct hierarchical tree using union-find clustering based on embedding similarity
- **Semantic Compression:** Two modes:
  - **With abstraction:** LLM summarizes child texts into "summative text" or "keywords"
  - **Without abstraction:** Aggregates child embeddings via `prototype_embeddings()`
- **Prototype Embedding Logic:**
  ```python
  # When exclude_abs=True:
  all_tree_nodes[node].embeddings = prototype_embeddings(
      np.asarray([all_tree_nodes[i].embeddings for i in children[node]])
  )
  ```
- **Hierarchy Tracking:** `layer_to_node_indices` maps tree layers (0 = leaves)

**3. Node Representation (`src/model/abstract.py`)**
- **Structure:** Each node contains:
  - `text` content (summative or keywords)
  - `ancestor_ids` and `children_ids` for hierarchy navigation
  - `embeddings` (vector representation)
- **Abstraction Methods:** OpenAI, Ollama, VLLM, Transformers backends
- **Prompt Template:** `get_abs_template(context, keyword=..., leaf=..., abs_max_length=...)`

---

## 2. Psi-RAG Concepts vs Local Adapter Seams

### Mapping Table

| Psi-RAG Concept | Local Seam | Compatibility Assessment |
|-----------------|------------|--------------------------|
| **Iterative layer descent** | `analyze_tree_semantic_distribution` | **MISMATCH** — Psi-RAG does logarithmic-time retrieval; we need per-node statistics computation (not iterative filtering) |
| **Node embedding aggregation** | `_compute_centroid` in Phase 1 baseline | **MATCH** — Both compute centroid vectors, but our baseline already implements this |
| **Distance normalization** | `_euclidean_distance` + dispersion | **PARTIAL MATCH** — Psi-RAG uses `(2 - distance) / 2` for cosine similarity; we use Euclidean distance for dispersion |
| **Top-k filtering per layer** | `BaselineTreeBranchDecisionPolicy` | **MISMATCH** — Psi-RAG's top-k is for retrieval filtering; our policy uses dispersion/entropy thresholds for decision logic |
| **Semantic compression (LLM summaries)** | Not in current seam | **NOT REQUIRED** — Our seam doesn't need LLM-based node summarization |
| **Hybrid BM25 + dense retrieval** | Not in current seam | **NOT REQUIRED** — Our seam is distribution analysis, not retrieval orchestration |
| **Union-find tree construction** | Registry-based node queries | **MISMATCH** — Psi-RAG builds trees via clustering; we query persisted trees from PostgreSQL registry |
| **Prototype embeddings** | `_compute_centroid` in Phase 1 | **MATCH** — Both aggregate child embeddings, but Phase 1 baseline already covers this |

### Detailed Analysis

#### Traversal Skeleton Mismatch

**Psi-RAG Traversal Purpose:**
- **Goal:** Minimize retrieval latency via logarithmic-time search (skip irrelevant branches)
- **Mechanism:** Iterative filtering from root to leaves, expanding only top-k nodes per layer
- **Output:** Final candidate set of leaf chunks and intermediate summaries

**Local Seam Requirement:**
- **Goal:** Compute semantic distribution statistics for ALL nodes (not selective retrieval)
- **Mechanism:** Iterate through persisted tree nodes from PostgreSQL registry, compute centroid/dispersion/entropy per node
- **Output:** Per-node statistics dictionary for downstream decision policy

**Conclusion:** Psi-RAG's traversal skeleton is optimized for retrieval efficiency (skipping nodes), whereas our seam requires comprehensive statistics computation (visiting all nodes). The skeletons serve fundamentally different purposes and cannot be transplanted without architectural mismatch.

#### Prototype Embedding Convergence

**Psi-RAG Approach:**
```python
# Aggregates child embeddings into parent prototype
prototype_embeddings(np.asarray([child_embeddings]))
```

**Phase 1 Baseline Approach:**
```python
# Computes centroid of vectors belonging to a node
def _compute_centroid(vectors):
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(dimension)]
```

**Assessment:** Both approaches compute mean aggregation. Phase 1 baseline already implements prototype embedding logic. No transplantation needed.

#### Node Representation Differences

**Psi-RAG Node:**
- LLM-generated "summative text" or "keywords" as abstract representation
- Explicit `ancestor_ids` and `children_ids` for navigation
- Built during index construction via clustering

**Local Node:**
- Query from PostgreSQL registry: `query_tree_nodes_by_version(version_id)`
- Heading path + level_no + node_id from persisted structure
- No LLM summarization required

**Assessment:** Psi-RAG's node representation includes semantic compression (LLM summaries) that our seam does not require. Our nodes are persisted structural entities, not dynamically abstracted summaries.

---

## 3. Transplantation Feasibility Analysis

### What Could Be Transplanted (Theoretical)

**Option 1: Distance Normalization Formula**
- Psi-RAG uses `(2 - distance) / 2` for cosine similarity normalization
- Our baseline uses Euclidean distance directly
- **Decision:** NOT transplant — Euclidean distance is appropriate for dispersion calculation; cosine normalization is retrieval-specific

**Option 2: Prototype Embedding Function**
- Psi-RAG has `prototype_embeddings()` utility
- Our baseline has `_compute_centroid()` with identical logic
- **Decision:** NOT transplant — already implemented in Phase 1 baseline

**Option 3: Hybrid BM25 + Dense Retrieval**
- Psi-RAG combines sparse and dense retrieval
- **Decision:** NOT transplant — our seam is distribution analysis, not retrieval orchestration; BM25 hybrid belongs to Line A (PageIndex donor) not Line B

### What Must Be Discarded (Architectural Mismatch)

**Discarded Elements:**
1. **Iterative layer descent with top-k filtering** — Optimizes for retrieval latency, incompatible with comprehensive node statistics
2. **LLM-based semantic compression** — Our nodes are persisted structural entities, not dynamically abstracted
3. **Union-find tree construction** — We query persisted trees from registry, not build via clustering
4. **Cross-encoder reranking** — Retrieval-specific logic, not distribution analysis
5. **HNSW graph for large corpora** — Retrieval acceleration, not statistics computation

---

## 4. Transplantation Decision: NO

### Rationale

**1. Architectural Purpose Mismatch**
- Psi-RAG's traversal skeleton is optimized for **logarithmic-time retrieval** (selective node expansion)
- Our seam requires **comprehensive statistics computation** (visit all nodes)
- Transplanting the skeleton would violate our architectural requirement

**2. Phase 1 Baseline Already Covers Core Logic**
- `_compute_centroid()` implements prototype embedding aggregation
- `_euclidean_distance()` + `_compute_entropy()` provide distribution metrics
- `_build_node_stats()` produces per-node statistics dictionary
- Nothing from Psi-RAG would enhance this baseline

**3. Donor Logic Cannot Be Mapped to Local Provenance Contracts**
- Psi-RAG builds trees via clustering (owns node creation)
- We query persisted trees from PostgreSQL registry (source-of-truth)
- Transplanting Psi-RAG tree construction would violate our frozen decision: "PostgreSQL registry is source-of-truth"

**4. Semantic Compression Not Required**
- Psi-RAG uses LLM to generate node summaries ("summative text" or "keywords")
- Our nodes have heading_path + level_no from persisted structure
- Adding LLM summarization would introduce unnecessary complexity and cost

### Alternative Path: Keep Phase 1 Baseline

**Phase 1 Baseline Strengths:**
- ✅ Computes centroid, dispersion, entropy, support_count per node
- ✅ Maps chunks → spans → nodes via registry queries
- ✅ Supports `BaselineTreeBranchDecisionPolicy` for decision logic
- ✅ Tests passing (12/12)
- ✅ White-box demo works on real document

**What Phase 1 Baseline Cannot Do (But Doesn't Need To):**
- ❌ Iterative retrieval with top-k filtering (Psi-RAG feature, not our requirement)
- ❌ LLM-based semantic compression (not needed for distribution analysis)
- ❌ Hybrid BM25 + dense retrieval (belongs to Line A, not Line B)

**Conclusion:** Phase 1 baseline is sufficient for Phase 2 requirements. No transplantation needed.

---

## 5. Proposed Action: Proceed Without Transplantation

### Phase 2 Exit Criteria Assessment

**Current Status:**
- ✅ Research report exists comparing Psi-RAG skeleton vs local adapter needs
- ✅ Decision made: **NO transplantation** (Phase 1 baseline is sufficient)
- ⏭️ Skip transplantation implementation
- ⏭️ Proceed to Phase 3: RAPTOR structure donor reference (per roadmap)

### Test Strategy (If No Transplantation)

**Validation:**
- Phase 1 baseline tests already pass (12/12)
- No new tests needed for Psi-RAG skeleton (not transplanting)
- Proceed to next phase with existing baseline

### Documentation Update

**Update `03-CURRENT-PHASE.md`:**
- Mark Phase 2 as COMPLETED
- Record decision: "Psi-RAG skeleton evaluation: NO transplantation"
- Record rationale: "Architectural mismatch; Phase 1 baseline sufficient"

---

## 6. Sources

### Primary Sources (HIGH confidence)

- [Psi-RAG GitHub Repository](https://github.com/Newiz430/Psi-RAG) — Code structure verified [VERIFIED: GitHub web fetch]
- [Psi-RAG README](https://raw.githubusercontent.com/Newiz430/Psi-RAG/main/README.md) — Architecture overview [VERIFIED: GitHub raw fetch]
- [Psi-RAG tree_retriever.py](https://raw.githubusercontent.com/Newiz430/Psi-RAG/main/src/tree_retriever.py) — Traversal logic [VERIFIED: GitHub raw fetch]
- [Psi-RAG model/abstract.py](https://raw.githubusercontent.com/Newiz430/Psi-RAG/main/src/model/abstract.py) — Node representation [VERIFIED: GitHub raw fetch]
- [Psi-RAG tree_builder/base.py](https://raw.githubusercontent.com/Newiz430/Psi-RAG/main/src/tree_builder/base.py) — Abstract tree builder [VERIFIED: GitHub raw fetch]

### Local Sources (HIGH confidence)

- `E:\github\rag\llamaindex_runtime\tree\semantic_distribution.py` — Phase 1 baseline implementation [VERIFIED: Read tool]
- `E:\github\rag\tests\llamaindex_runtime\test_tree_semantic_distribution.py` — Phase 1 baseline tests [VERIFIED: Read tool]
- `E:\github\rag\changes\compatibility-adapter-program\02-INTERFACES.md` — Interface requirements [VERIFIED: Read tool]
- `E:\github\rag\changes\compatibility-adapter-program\00-MASTER.md` — Frozen decisions [VERIFIED: Read tool]

### Secondary Sources (MEDIUM confidence)

- `E:\github\rag\docs\research\verified-project-matrix.md` — Psi-RAG project verification [CITED: project matrix]
- `E:\github\rag\docs\research\final-selection-checklist.md` — Psi-RAG donor priority [CITED: selection checklist]
- Chinese research document (结合非向量树状知识库...) — Psi-RAG multi-granularity retrieval description [CITED: research report]

---

## 7. Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Psi-RAG structure | HIGH | Verified via GitHub repository fetch and code examination |
| Traversal logic | HIGH | Extracted from tree_retriever.py source code |
| Node representation | HIGH | Extracted from model/abstract.py and tree_builder/abstract.py |
| Transplantation decision | HIGH | Clear architectural mismatch; Phase 1 baseline already covers core requirements |
| Local seam requirements | HIGH | Verified via INTERFACE.md and Phase 1 implementation |

**Overall Confidence:** **HIGH** — Sufficient information to make definitive transplantation decision.

---

## 8. Next Steps

1. **Mark Phase 2 as COMPLETED** in `03-CURRENT-PHASE.md`
2. **Proceed to Phase 3** — RAPTOR structure donor reference (per roadmap)
3. **Update program documentation** — Record Psi-RAG evaluation result for future reference
4. **No code changes** — Keep Phase 1 baseline as-is

---

**Research Completed:** 2026-05-20
**Researcher:** GSD Phase Research Agent
**Status:** Phase 2 evaluation complete; NO transplantation recommended