# Complete PageIndex Integration Migration Plan

## Document Status
- **Author:** System Analysis
- **Date:** 2026-06-06
- **Context:** Phase 4 (PageIndex Quality Improvement and Baseline Reconciliation)
- **Trigger:** User goal request for complete integration migration strategy

---

## Executive Summary

**Current State (Partial Integration):**
- Tree building: ✅ PageIndex integrated (PageIndexTreeAdapter)
- Retrieval: ❌ Local adapter/runtime (Psi-RAG traversal + HIRO decision)
- Gap: PageIndex's reasoning-based retrieval not wired into default path

**Target State (Complete Integration):**
- Tree building: ✅ PageIndex (preserve existing)
- Retrieval: ✅ PageIndex reasoning backend (ReasoningTreeBackend)
- Adapter role: Pure pass-through (schema translation only)

**Migration Complexity:** Medium
- Code changes: 3 files (runtime.py, query.py, reasoning_backend.py)
- Architecture shift: Embedding traversal → LLM reasoning
- Risk: Performance regression (LLM calls vs embedding similarity)
- Benefit: Token savings (PageIndex judges pages, not full-tree retrieval)

---

## 1. Current State Analysis

### 1.1 Tree Building Path (PageIndex-Integrated)

**File:** `llamaindex_runtime/tree/pageindex_adapter.py`

**Current Flow:**
```
PageIndexTreeAdapter.index_tree()
  → _call_pageindex_tree_parser_stub() (PDF)
    → pageindex.page_index.tree_parser()
    → Monkey-patch llm_acompletion → llm_acompletion_unified()
    → Routes through unified LLM seam
  → _call_pageindex_md_to_tree() (Markdown)
    → pageindex.page_index_md.md_to_tree()
    → Unified LLM seam via RuntimeSettings.from_env_llm_only()
  → _flatten_embedded_tree()
    → PageIndex embedded tree → local flat nodes
    → UUID generation (local provenance)
    → heading_path construction (parent chain)
  → registry.write_tree()
    → Persists nodes through RegistryWriter seam
```

**Status:** ✅ COMPLETE
- PageIndex donor logic transplanted
- Unified LLM seam prevents donor-owned config stack
- Frozen provenance contracts preserved (version_id, node_id UUIDs)
- Error handling: Controlled RuntimeError when credentials available but LLM fails

### 1.2 Retrieval Path (Local Adapter/Runtime)

**File:** `llamaindex_runtime/tree/runtime.py`

**Current Flow:**
```
retrieve_tree_hits_from_pdf()
  → _retrieve_tree_hits_from_backend()
    → Load nodes/spans from registry
    → embed_model.get_query_embedding(query_text)
    → PersistedTreeSemanticDistributionAdapter.analyze_tree_semantic_distribution()
      → Compute node statistics (centroid, dispersion, entropy, prototype_embedding)
      → Psi-RAG prototype embedding transplant
    → RecursiveTreeTraversalRunner.traverse_tree_for_query()
      → Traverse from root nodes
      → For each node:
        - Compute similarity (query embedding vs prototype embedding)
        - Policy.decide_branch_action() → "keep_parent" / "drill_down" / "prune"
        - HIROEnhancedTreeBranchDecisionPolicy.evaluate_children() (if children exist)
        - Recursively descend based on decision
      → Collect QueryHit list (node_id, span_id, chunk_id, similarity_score)
    → _map_query_hits_to_backend_hits()
      → QueryHit → BackendHit dict
```

**Decision Policy Options:**
- `decision_policy="baseline"`: BaselineTreeBranchDecisionPolicy (dispersion/entropy thresholds)
- `decision_policy="hiro"`: HIROEnhancedTreeBranchDecisionPolicy (distance thresholds, child evaluation)

**Status:** ❌ LOCAL IMPLEMENTATION
- Uses Psi-RAG traversal skeleton (Phase 5 transplant)
- Uses HIRO decision layer (Phase 6 transplant)
- NOT using PageIndex's reasoning-based retrieval
- Embedding-based similarity (not LLM judgment)

### 1.3 Reasoning Backend (Exists But Not Wired)

**File:** `llamaindex_runtime/tree/reasoning_backend.py`

**Implementation:**
```
ReasoningTreeBackend.retrieve_tree_hits()
  → Fetch tree structure from registry/documents dict
  → _llm_judge_relevant_pages()
    → Format structure for LLM (ultra-compact: "X:Title")
    → Call get_llm() (unified seam)
    → LLM prompt: "Pages:\n{structure}\nQuery: {query}\nRelevant:"
    → Parse response → comma-separated pages (e.g., "1,5,9")
  → get_page_content() (PageIndex client API)
    → Extract content for judged pages only (token savings)
  → Map to BackendHit format
    → node_id, span_ids, chunk_id from registry queries
    → heading_path from structure
```

**Status:** ⚠️ IMPLEMENTED BUT ISOLATED
- Exists in codebase (Phase 2 Task 2.2)
- NOT wired into runtime.py default path
- NOT exposed in query.py entrypoint
- Requires documents dict or registry fallback

---

## 2. Target State Definition

### 2.1 Complete Integration Architecture

**Tree Building:**
- ✅ PRESERVE: PageIndexTreeAdapter (already complete)

**Retrieval:**
- 🔧 SWITCH: ReasoningTreeBackend as default path
- 🔧 DEPRECATE: Embedding-based traversal (Psi-RAG/HIRO) as optional fallback

**Adapter Role:**
- 🔧 REDUCE: PageIndexTreeAdapter becomes pure pass-through
  - Keep: index_tree() (schema translation: PageIndex tree → local nodes)
  - Keep: retrieve_tree_hits() (provenance mapping: BackendHit format)
  - Remove: NOT used for retrieval logic (moved to ReasoningTreeBackend)

### 2.2 Expected Quality Improvements

**Hypothesis:** PageIndex reasoning retrieval improves quality metrics.

**Baseline (Current):**
- hit_rate: 5% (Phase 3 real validation)
- top1_relevance: 10%
- stability: 0%
- root-bias: High (traversal starts from root nodes)
- node-chunk mapping: 0% (Phase 3: chunks=0)

**Target (PageIndex Reasoning):**
- hit_rate: ≥80% (Phase 2 frozen threshold)
- top1_relevance: ≥90%
- stability: ≥85%
- root-bias: Reduced (LLM judges pages directly, not traversal descent)
- node-chunk mapping: ≥80% (improved provenance recovery)

**Rationale:**
1. **Root-bias reduction:**
   - Current: Traversal must start from root → bias toward high-level nodes
   - Target: LLM judges ALL pages equally → no structural bias

2. **Top1_relevance improvement:**
   - Current: Embedding similarity (prototype vs query) → semantic approximation
   - Target: LLM reasoning (query intent vs page content) → contextual understanding

3. **Token efficiency:**
   - Current: Traverse entire tree, compute embeddings for all nodes
   - Target: LLM judges N pages, extract content for M relevant pages (M < N)

---

## 3. Migration Steps

### Step 1: Wire ReasoningTreeBackend into runtime.py

**File:** `llamaindex_runtime/tree/runtime.py`

**Current Code (Lines 24-86):**
```python
def _retrieve_tree_hits_from_backend(
    query_text: str,
    *,
    version_id: Any,
    registry: Any,
    limit: int,
    embed_model: BaseEmbedding | None = None,
    decision_policy: str = "baseline",
) -> list[dict[str, Any]]:
    # Current: Embedding-based traversal path
    nodes = registry.query_tree_nodes_by_version(version_id)
    # ... Psi-RAG traversal + HIRO decision ...
```

**Migration Change:**
```python
def _retrieve_tree_hits_from_backend(
    query_text: str,
    *,
    version_id: Any,
    registry: Any,
    limit: int,
    embed_model: BaseEmbedding | None = None,
    decision_policy: str = "baseline",
    backend_type: str = "reasoning",  # NEW PARAMETER
    documents: dict[str, Any] | None = None,  # NEW PARAMETER
) -> list[dict[str, Any]]:
    # NEW: Reasoning backend path (default)
    if backend_type == "reasoning":
        from .reasoning_backend import ReasoningTreeBackend
        reasoning_backend = ReasoningTreeBackend(
            llm_model=RuntimeSettings.from_env_llm_only()["llm_model"],
            documents=documents or {},
        )
        backend_hits = reasoning_backend.retrieve_tree_hits(
            query_text=query_text,
            version_id=version_id,
            registry=registry,
            limit=limit,
        )
        return [hit.to_dict() for hit in backend_hits]

    # PRESERVE: Embedding traversal as fallback
    nodes = registry.query_tree_nodes_by_version(version_id)
    # ... existing Psi-RAG/HIRO logic ...
```

**API Changes:**
- Add `backend_type` parameter: "reasoning" (default) | "embedding" (fallback)
- Add `documents` parameter: PageIndex workspace dict (optional)
- Preserve `decision_policy` for embedding fallback

### Step 2: Expose backend_type in query.py entrypoint

**File:** `llamaindex_runtime/entrypoints/query.py`

**Current Code (Lines 332-341):**
```python
else:  # resolved_mode == "tree"
    top_k = similarity_top_k if similarity_top_k is not None else 4
    raw_hits = retrieve_tree_hits_from_pdf(
        resolved_path,
        query=normalized_query_text,
        embed_model=embed_model,
        similarity_top_k=top_k,
        registry=registry if version_id is not None else None,
        version_id=version_id,
    )
```

**Migration Change:**
```python
else:  # resolved_mode == "tree"
    top_k = similarity_top_k if similarity_top_k is not None else 4
    raw_hits = retrieve_tree_hits_from_pdf(
        resolved_path,
        query=normalized_query_text,
        embed_model=embed_model,
        similarity_top_k=top_k,
        registry=registry if version_id is not None else None,
        version_id=version_id,
        backend_type="reasoning",  # NEW: Default to PageIndex reasoning
        documents=None,  # NEW: Optional workspace dict
    )
```

**Hybrid Mode Change (Lines 220-232):**
```python
# 3. Tree path
tree_top_k = similarity_top_k if similarity_top_k is not None else 4
tree_raw = retrieve_tree_hits_from_pdf(
    resolved_path,
    query=normalized_query_text,
    embed_model=embed_model,
    similarity_top_k=tree_top_k,
    registry=registry if version_id is not None else None,
    version_id=version_id,
    backend_type="reasoning",  # NEW: Hybrid also uses reasoning
    documents=None,
)
```

### Step 3: Enhance ReasoningTreeBackend provenance mapping

**File:** `llamaindex_runtime/tree/reasoning_backend.py`

**Current Gap (Lines 154-167):**
```python
hit = BackendHit(
    score=None,  # ⚠️ No similarity score
    text_preview=content_item.get("content", ""),
    heading_path=heading_path,
    page_no=page,
    span_ids=span_ids,
    node_id=node_id,
    chunk_id=chunk_id,
    entity_id=None,
    relation_id=None,
)
```

**Migration Enhancement:**
```python
# NEW: Compute LLM confidence as proxy score
llm_confidence = self._estimate_llm_confidence(response_text, judged_pages)

hit = BackendHit(
    score=llm_confidence,  # NEW: Confidence-based scoring
    text_preview=content_item.get("content", ""),
    heading_path=heading_path,
    page_no=page,
    span_ids=span_ids,
    node_id=node_id,
    chunk_id=chunk_id,
    entity_id=None,
    relation_id=None,
    backend_source="reasoning",
    retrieval_path="llm_navigation",
)
```

**New Method:**
```python
def _estimate_llm_confidence(self, response_text: str, pages: str) -> float:
    """Estimate LLM confidence from response pattern.

    Heuristic confidence scoring:
    - Single page: 0.95 (high confidence)
    - Few pages (2-3): 0.85 (medium confidence)
    - Many pages (≥4): 0.75 (lower confidence)
    - Parse failure: 0.5 (fallback)
    """
    try:
        page_list = [int(p.strip()) for p in pages.split(",") if p.strip()]
        page_count = len(page_list)

        if page_count == 1:
            return 0.95
        elif page_count <= 3:
            return 0.85
        elif page_count <= 5:
            return 0.75
        else:
            return 0.65
    except Exception:
        return 0.5
```

### Step 4: Deprecate embedding traversal path (optional fallback)

**Strategy:**
- Keep Psi-RAG/HIRO logic as `backend_type="embedding"` fallback
- Document as "legacy path" for backward compatibility
- Update tests to cover both paths
- Phase 5 validation: Compare reasoning vs embedding quality

### Step 5: Update environment variable control

**File:** `llamaindex_runtime/tree/runtime.py`

**Current (Lines 98-104):**
```python
# Phase 8: Resolve decision_policy from environment or default
if decision_policy is None:
    env_policy = os.environ.get("RAG_TREE_DECISION_POLICY", "baseline")
    decision_policy = env_policy
```

**Migration:**
```python
# NEW: Resolve backend_type from environment
if backend_type is None:
    env_backend = os.environ.get("RAG_TREE_BACKEND_TYPE", "reasoning")
    backend_type = env_backend

# PRESERVE: decision_policy for embedding fallback
if decision_policy is None:
    env_policy = os.environ.get("RAG_TREE_DECISION_POLICY", "baseline")
    decision_policy = env_policy
```

**Environment Variables:**
- `RAG_TREE_BACKEND_TYPE`: "reasoning" (default) | "embedding" (fallback)
- `RAG_TREE_DECISION_POLICY`: "baseline" | "hiro" (embedding path only)

---

## 4. Expected Effects

### 4.1 Quality Metrics Projection

**Baseline vs Target Comparison:**

| Metric | Baseline (Phase 3) | Target (PageIndex) | Delta |
|--------|---------------------|-------------------|-------|
| hit_rate | 5% | ≥80% | +75% |
| top1_relevance | 10% | ≥90% | +80% |
| stability | 0% | ≥85% | +85% |
| root-bias | High | Low | Reduced |
| node-chunk mapping | 0% | ≥80% | +80% |

**Improvement Mechanisms:**

1. **Root-bias reduction:**
   - Embedding traversal: Must descend from root → structural bias
   - Reasoning backend: Judges all pages independently → flat selection

2. **Top1_relevance boost:**
   - Embedding similarity: Semantic approximation (prototype vs query)
   - LLM reasoning: Contextual understanding (query intent vs page content)

3. **Stability improvement:**
   - Embedding path: Sensitive to embedding quality, traversal parameters
   - Reasoning path: LLM judgment more robust to embedding noise

### 4.2 Performance Impact

**Token Cost Analysis:**

| Path | Token Usage | Cost |
|------|-------------|------|
| Embedding traversal | Embedding all nodes + traversal | Moderate (embedding API calls) |
| Reasoning backend | LLM judgment + content extraction | Higher (LLM reasoning calls) |

**Optimization:**
- Ultra-compact prompt (reasoning_backend.py Lines 227-228): ~80 tokens
- Filtered content extraction: Only judged pages (not full tree)
- Target: 90%+ token savings vs full-tree LLM processing

### 4.3 Architectural Benefits

1. **PageIndex alignment:**
   - Tree building: Already PageIndex
   - Retrieval: Becomes PageIndex
   - Consistent donor logic across build + retrieval

2. **Adapter simplification:**
   - PageIndexTreeAdapter: Schema translation only
   - ReasoningTreeBackend: Retrieval logic
   - Clear separation of concerns

3. **Provenance preservation:**
   - Frozen contracts maintained (node_id, span_id, chunk_id UUIDs)
   - Registry seam unchanged
   - BackendHit format preserved

---

## 5. Phase 5 Implementation Plan

### 5.1 Task Breakdown

**Task 1: Wire ReasoningTreeBackend (2 hours)**
- Modify runtime.py `_retrieve_tree_hits_from_backend()`
- Add backend_type parameter
- Import ReasoningTreeBackend
- Wire retrieval path

**Dependencies:** None (backend already implemented)

**Exit Criteria:**
- ReasoningTreeBackend callable from runtime.py
- backend_type="reasoning" path works
- BackendHit format compatible

**Task 2: Expose backend_type in entrypoints (1 hour)**
- Modify query.py tree mode
- Modify query.py hybrid mode
- Add backend_type parameter
- Default to "reasoning"

**Dependencies:** Task 1 complete

**Exit Criteria:**
- query(mode="tree") uses reasoning backend
- query(mode="hybrid") uses reasoning backend for tree leg

**Task 3: Enhance confidence scoring (1 hour)**
- Add `_estimate_llm_confidence()` to reasoning_backend.py
- Update BackendHit score field
- Document heuristic scoring

**Dependencies:** Task 1 complete

**Exit Criteria:**
- BackendHit has non-null score
- Confidence heuristic documented
- Score reflects LLM judgment quality

**Task 4: Update environment control (30 minutes)**
- Add RAG_TREE_BACKEND_TYPE env var
- Resolve backend_type from environment
- Document environment variable

**Dependencies:** Task 1 complete

**Exit Criteria:**
- Environment variable control works
- Default "reasoning"
- Fallback "embedding" available

**Task 5: Write integration tests (2 hours)**
- Test reasoning backend path
- Test backend_type switch
- Test environment variable control
- Test fallback to embedding

**Dependencies:** Tasks 1-4 complete

**Exit Criteria:**
- Tests pass
- Both paths covered
- Environment control verified

**Task 6: Quality validation (4 hours)**
- Run Phase 3 validation script
- Use reasoning backend (backend_type="reasoning")
- Compare metrics vs baseline
- Document results

**Dependencies:** Tasks 1-5 complete, Phase 3 validation script available

**Exit Criteria:**
- Quality metrics measured
- Comparison vs baseline documented
- Improvement hypothesis validated/invalidated

**Total Time:** ~10.5 hours

### 5.2 Dependency Graph

```
Task 1 (Wire backend)
  ↓
Task 2 (Expose entrypoints) ← Task 4 (Environment control)
  ↓
Task 3 (Confidence scoring)
  ↓
Task 5 (Integration tests)
  ↓
Task 6 (Quality validation)
```

**Critical Path:** Task 1 → Task 2 → Task 5 → Task 6

### 5.3 Risk Assessment

**Risk 1: LLM performance regression**
- Probability: Medium
- Impact: High (quality metrics degrade)
- Mitigation:
  - Keep embedding fallback (backend_type="embedding")
  - Phase 5 validation compares both paths
  - Environment variable control for quick rollback

**Risk 2: Provenance mapping gaps**
- Probability: Low
- Impact: Medium (node-chunk mapping incomplete)
- Mitigation:
  - Enhance `_query_chunk_id_for_hit()` (reasoning_backend.py Lines 402-434)
  - Registry fallback queries robust
  - Task 3 confidence scoring validates mapping

**Risk 3: Token cost exceeds budget**
- Probability: Low
- Impact: Medium (cost budget overrun)
- Mitigation:
  - Ultra-compact prompt optimization (reasoning_backend.py Lines 227-228)
  - Filtered content extraction (judged pages only)
  - Task 6 validation measures token usage

**Risk 4: Credentials unavailable**
- Probability: High (Phase 8 blocker)
- Impact: High (reasoning backend fails)
- Mitigation:
  - Environment variable RAG_TREE_BACKEND_TYPE allows fallback
  - Error handling: RuntimeError when credentials unavailable
  - Task 5 tests cover credential availability cases

### 5.4 Validation Plan

**Validation Criteria:**
1. **Functional:**
   - Reasoning backend callable from runtime.py
   - BackendHit format compatible
   - Provenance contracts preserved

2. **Quality:**
   - hit_rate ≥80% (Phase 2 frozen threshold)
   - top1_relevance ≥90%
   - stability ≥85%

3. **Performance:**
   - Token usage within budget
   - LLM latency acceptable
   - Fallback path available

**Validation Execution:**
- Use Phase 3 validation script (`verification/phase3-real-validation/run_validation.py`)
- Switch backend_type="reasoning"
- Run on same corpus (竞品分析 PDF)
- Compare metrics vs Phase 3 baseline

**Go/No-Go Criteria:**
- **Go:** Quality metrics meet Phase 2 frozen thresholds
- **No-Go:** Quality metrics degrade vs baseline → rollback to embedding path

---

## 6. Implementation Timeline

### Week 1: Core Integration (Tasks 1-4)
- Day 1-2: Task 1 (Wire backend)
- Day 2: Task 2 (Expose entrypoints)
- Day 3: Task 3 (Confidence scoring)
- Day 3: Task 4 (Environment control)

### Week 2: Validation (Tasks 5-6)
- Day 1-2: Task 5 (Integration tests)
- Day 3-4: Task 6 (Quality validation)
- Day 5: Documentation and decision

**Total Duration:** 2 weeks (10.5 hours actual work time)

---

## 7. Decision Framework

### 7.1 Promotion Criteria (Success)

**Required:**
1. Quality metrics meet Phase 2 frozen thresholds (hit_rate ≥80%, top1_relevance ≥90%)
2. Provenance contracts preserved (node_id, span_id, chunk_id UUIDs)
3. Reasoning backend stable (no RuntimeError with credentials)
4. Tests pass (Task 5 integration tests)

**Optional:**
5. Token usage within budget
6. Root-bias reduced (measured by page distribution)
7. Node-chunk mapping ≥80%

### 7.2 Rollback Criteria (Failure)

**Triggers:**
1. Quality metrics degrade vs baseline (hit_rate <5%, top1_relevance <10%)
2. LLM performance regression (latency >2x baseline)
3. Provenance mapping gaps (node-chunk <80%)
4. Credential instability (RuntimeError with real API key)

**Rollback Action:**
- Set RAG_TREE_BACKEND_TYPE="embedding" (environment variable)
- Reasoning backend becomes optional path
- Embedding traversal restored as default

### 7.3 Decision Evidence

**Evidence Sources:**
- Task 6 validation report (quality metrics)
- Task 5 test results (functional correctness)
- Phase 3 baseline comparison (improvement delta)
- Token usage logs (performance impact)

**Decision Authority:**
- Phase 5 validation lead (technical correctness)
- Project owner (promotion/rollback decision)

---

## 8. Appendix: Code References

### 8.1 Key Files

| File | Role | Lines |
|------|------|-------|
| `llamaindex_runtime/tree/pageindex_adapter.py` | Tree building (PageIndex) | 43-90 (index_tree), 92-163 (retrieve_tree_hits) |
| `llamaindex_runtime/tree/runtime.py` | Retrieval runtime | 24-86 (_retrieve_tree_hits_from_backend), 89-126 (retrieve_tree_hits_from_pdf) |
| `llamaindex_runtime/tree/reasoning_backend.py` | Reasoning backend | 81-172 (retrieve_tree_hits), 191-238 (_llm_judge_relevant_pages) |
| `llamaindex_runtime/entrypoints/query.py` | Query entrypoint | 332-353 (tree mode), 220-232 (hybrid tree leg) |
| `llamaindex_runtime/tree/semantic_distribution.py` | Embedding traversal (fallback) | 412-467 (traverse_tree_for_query) |

### 8.2 Frozen Contracts

**Immutable provenance fields:**
- `doc_id`: UUID (document identity)
- `version_id`: UUID (version anchoring)
- `span_id`: UUID (text span)
- `chunk_id`: UUID (vector chunk)
- `node_id`: UUID (tree node)
- `entity_id`: UUID (graph entity)
- `relation_id`: UUID (graph relation)
- `evidence_id`: UUID (evidence chain)

**BackendHit fields:**
- `score`: float | None
- `text_preview`: str
- `heading_path`: str | None
- `page_no`: int | None
- `span_ids`: list[UUID]
- `node_id`: UUID
- `chunk_id`: UUID
- `entity_id`: UUID | None
- `relation_id`: UUID | None

---

## 9. Conclusion

**Migration Strategy:**
1. Wire ReasoningTreeBackend into runtime.py (backend_type="reasoning")
2. Expose backend_type in query.py entrypoints
3. Enhance confidence scoring (proxy similarity score)
4. Preserve embedding traversal as fallback (backend_type="embedding")
5. Validate quality metrics vs Phase 3 baseline

**Expected Outcome:**
- Complete PageIndex integration (tree building + retrieval)
- Adapter simplification (schema translation only)
- Quality improvement (root-bias reduced, top1_relevance boosted)
- Backward compatibility (embedding fallback preserved)

**Next Action:**
- Proceed to Phase 5 implementation (Task 1: Wire backend)
- Validate quality metrics (Task 6)
- Make promotion/rollback decision based on evidence

---

**End of Document**