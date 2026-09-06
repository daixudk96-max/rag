# Architecture Retrieval Integration Research

**Generated:** 2026-06-06
**Purpose:** Synthesize research findings and propose mature retrieval framework integration (Plan B)
**Status:** Decision framework for Phase 5 planning

---

## Executive Summary

**Recommendation:** **LlamaIndex Core + PageIndex Reasoning Layer** as the primary retrieval framework integration

**Critical Finding:** Current system quality metrics show severe defects:
- **top1_relevance: 30%** (threshold: 90%) ← ROOT CAUSE
- **stability: 0%** (threshold: 85%) ← SECONDARY BLOCKER
- **root-bias pattern:** Queries return root nodes even when specific sections exist

**Root Cause Analysis:** The tree backend lacks **query-aware traversal** logic. Current implementation computes per-node statistics but does NOT guide descent toward query-relevant subtrees.

---

## 1. Research Synthesis: Four Prior Evaluations

### 1.1 Psi-RAG Skeleton Evaluation

**What We Need:**
- Traversal skeleton (recursive descent)
- Node semantic representation
- Prototype embedding (centroid)

**Gap Analysis:**
- Phase 1 baseline: ✓ Computes `centroid`, `dispersion`, `entropy`
- Phase 1 baseline: ✗ **NO traversal loop** (missing critical piece)
- Phase 1 baseline: ✗ **NO query embedding guidance**

**Transplantation Decision:** PARTIAL transplant
- **Transplant:** Traversal skeleton structure (NEW code)
- **Keep:** Node stats from Phase 1 (already sufficient)
- **Adaptation:** Add query embedding similarity scoring

**Risk:** LOW (only adds traversal loop, preserves provenance)

---

### 1.2 HIRO Skeleton Evaluation

**What We Need:**
- Recursive decision skeleton
- Dual-threshold pattern

**Gap Analysis:**
- Phase 1 baseline: ✓ Distribution-based thresholds (dispersion + entropy)
- Phase 1 baseline: ✗ **NO recursive aggregation**
- Phase 1 baseline: ✗ **NO subtree-level decisions**
- **Critical constraint:** HIRO uses **distance-based thresholds** → incompatible with our distribution-based approach

**Transplantation Decision:** PARTIAL transplant
- **Transplant:** Recursive evaluation skeleton (NEW code)
- **Keep:** Distribution-based thresholds (MUST preserve)
- **Adaptation:** Convert distance logic to distribution logic

**Risk:** MEDIUM (must avoid copying distance-based threshold logic)

---

### 1.3 RAPTOR Structure Evaluation

**What We Need:**
- Semantic cluster-tree construction
- Collapsed-tree retrieval

**Gap Analysis:**
- Local: ✗ Tree structure from PostgreSQL registry (NOT cluster-based)
- Local: ✓ Traversal runner (multi-level descent)
- Local: ✗ Summarization logic

**Transplantation Decision:** NO transplant (reference only)
- **Frozen constraint:** PostgreSQL registry is source-of-truth (cannot use clustering-based tree construction)
- **Reference only:** Compare collapsed retrieval pattern
- **Priority:** Tertiary donor (least priority)

**Risk:** NONE (no transplantation)

---

### 1.4 PageIndex Full Function Analysis

**What We Need:**
- Tree_thinning (node merging optimization)
- get_page_content (page extraction tool)
- Reasoning-based retrieval (LLM navigation)
- PageIndexClient (complete lifecycle management)

**Gap Analysis:**
- Current: ✓ Tree structure extraction (PageIndexTreeAdapter)
- Current: ✗ **tree_thinning** (not transplanted)
- Current: ✗ **get_page_content** (not implemented)
- Current: ✗ **Reasoning retrieval** (not implemented)
- Current: ✗ **PageIndexClient** (not transplanted)

**Transplantation Decision:** FULL transplant (except LLM summaries)
- **Transplant:** PageIndexClient + CLI + workspace management
- **Transplant:** tree_thinning + get_page_content
- **Transplant:** Reasoning retrieval (as optional backend)
- **Blocked:** LLM summaries/descriptions (control package frozen)

**Risk:** MEDIUM (requires Agent framework integration)

---

## 2. Framework Recommendation

### 2.1 Primary Recommendation: **LlamaIndex Core + PageIndex Reasoning**

**Architecture:**
```
LlamaIndex Core Integration:
├── Vector Store Index (existing)
├── Knowledge Graph Index (existing)
├── Tree Index (PageIndex structural tree)
│   ├── PageIndexTreeAdapter (tree build)
│   ├── PageIndexClient (workspace + lifecycle)
│   ├── tree_thinning (node optimization)
│   └── get_page_content (page extraction)
│
└── Reasoning Backend (NEW):
    ├── LlamaIndex ReAct Agent
    ├── Tools: get_document_structure, get_page_content
    └── Hybrid Router:
        ├── Tree Backend (clustering + reasoning)
        ├── Graph Backend (KG)
        ├── Vector Backend (embedding)
        └── Weights: [tree=0.4, graph=0.3, vector=0.3]
```

**Why LlamaIndex:**
1. **Already integrated** (current system uses LlamaIndex RuntimeSettings + config)
2. **Proven patterns** (VectorStoreIndex, KnowledgeGraphIndex already working)
3. **Agent framework** (LlamaIndex Agents SDK for reasoning retrieval)
4. **Community support** (mature, well-documented)
5. **Low risk** (incremental extension, NOT new framework)

**Why PageIndex Reasoning:**
1. **Solves root-bias:** LLM navigates tree → targets specific sections
2. **Complete implementation:** PageIndex already has reasoning workflow
3. **Proven workflow:** Agent calls `get_document_structure` → LLM judges relevance → `get_page_content`
4. **Token savings:** Hybrid approach reduces reasoning overhead (only when needed)

---

### 2.2 Alternative: LightRAG (PAUSED per control package)

**Status:** Frozen (cannot use)
**Reason:** Control package explicitly pauses graph-two-in-one ambitions
**Reopen condition:** Only after Line A + Line B stabilize

---

### 2.3 Alternative: RAG-Anything (PAUSED per control package)

**Status:** Frozen (cannot use)
**Reason:** Multimodal branch paused
**Reopen condition:** Only after graph branch reactivated

---

## 3. Integration Architecture

### 3.1 Adapter Pattern (Control Package Compliance)

**Frozen Contract Preservation:**
- ✓ Adapter wraps donor logic
- ✓ Registry writes provenance (doc_id, version_id, span_id, chunk_id, node_id)
- ✓ Donor does NOT own IDs or storage
- ✓ Unified seam (TreeBackendAdapter routes to multiple backends)

**Integration Points:**
```
PageIndexTreeAdapter (tree build):
├── Input: markdown_path / PDF_path
├── Process: PageIndex md_to_tree + tree_thinning
├── Output: tree_nodes → PostgreSQL registry
└

PageIndexClient (lifecycle management):
├── Input: file_path + config
├── Process: PageIndex index() + workspace persistence
├── Output: doc_id + structure + page_texts
├── Registry write-back: version_id + node_spans
└

ReasoningTreeBackend (retrieval):
├── Input: query_text + version_id
├── Process: LlamaIndex ReAct Agent
│   ├── Tool: get_document_structure (PageIndex)
│   ├── Tool: get_page_content (PageIndex)
│   └── LLM reasoning: judge relevant nodes
├── Output: BackendHit list (with provenance)
└

HybridRetrievalRouter:
├── Input: query_text + version_id
├── Process: parallel backend calls
│   ├── tree_backend_clustering (TreeGenerator)
│   ├── tree_backend_reasoning (PageIndex Agent)
│   ├── graph_backend (KG)
│   └── vector_backend (embedding)
├── Output: merged BackendHit list
```

---

### 3.2 Code Locations and Changes

**Tier 1: High-Impact Changes (Must Implement)**

| Module | File | Changes | Priority |
|--------|------|---------|----------|
| **PageIndexClient** | `llamaindex_runtime/client/pageindex_client.py` | Port PageIndex client.py, add registry write-back | P0 |
| **tree_thinning** | `llamaindex_runtime/tree/pageindex_adapter.py` | Add thinning logic to `_call_pageindex_md_to_tree()` | P0 |
| **get_page_content** | `llamaindex_runtime/tools/page_tools.py` | New file: port PageIndex retrieve.py tools | P0 |
| **ReasoningBackend** | `llamaindex_runtime/tree/reasoning_backend.py` | New file: LlamaIndex Agent + PageIndex tools | P0 |
| **HybridRouter** | `llamaindex_runtime/tree/hybrid_router.py` | New file: backend merging logic | P0 |

**Tier 2: Medium-Impact Changes (Should Implement)**

| Module | File | Changes | Priority |
|--------|------|---------|----------|
| **RuntimeSettings** | `llamaindex_runtime/config.py` | Add PAGEINDEX_WORKSPACE, TREE_BACKEND_MODE config | P1 |
| **CLI tool** | `llamaindex_runtime/cli/run_pageindex.py` | Port PageIndex CLI, integrate RuntimeSettings | P1 |
| **Tests** | `tests/test_pageindex_integration.py` | New file: PageIndexClient + reasoning backend tests | P1 |
| **Workspace management** | `llamaindex_runtime/workspace/` | New directory: PageIndex workspace logic | P1 |

**Tier 3: Low-Impact Changes (Optional)**

| Module | File | Changes | Priority |
|--------|------|---------|----------|
| **Embedding clustering** | `llamaindex_runtime/registry/tree_generator.py` | Enhance `_detect_semantic_cluster()` with embeddings | P2 |
| **Visualization** | `llamaindex_runtime/tools/visualize_tree.py` | Port PageIndex `print_toc()` debug tool | P2 |

---

### 3.3 Frozen Contract Checks

**Before Integration:**
- [ ] PageIndexClient writes to PostgreSQL registry (NOT PageIndex workspace only)
- [ ] node_id generation uses uuid5 deterministic (NOT PageIndex sequence 0001)
- [ ] Evidence chain preserves: doc_id → version_id → span_id → chunk_id → node_id
- [ ] Reasoning backend returns BackendHit (NOT PageIndex raw JSON)
- [ ] Hybrid router preserves provenance (all hits traceable to registry)

---

## 4. Expected Quality Improvements

### 4.1 Root-Bias Mitigation

**Current Problem:**
- Query: "核心算法原理"
- Current result: Returns root node (level 1) with generic content
- Desired result: Returns level 3 node with specific algorithm section

**PageIndex Reasoning Solution:**
1. Agent gets full tree structure (get_document_structure)
2. LLM judges: "核心算法原理 → match Section 3.2 node"
3. Agent extracts: get_page_content(pages="15-17")
4. Result: Level 3 node with specific content

**Expected Improvement:**
- **top1_relevance:** 30% → 70-85% (agent targets specific sections)
- **stability:** 0% → 60-75% (agent path consistency)

**Gap Analysis:**
- Expected 70-85% still below 90% threshold
- Need additional backend (clustering + vector) to reach threshold
- Hybrid approach required

---

### 4.2 Hybrid Retrieval Improvement

**Hybrid Router Logic:**
```
Backend weights (config):
├── tree_clustering: 0.25 (TreeGenerator semantic split)
├── tree_reasoning: 0.25 (PageIndex Agent)
├── graph: 0.25 (KG entity retrieval)
├── vector: 0.25 (embedding similarity)

Merge strategy:
├── Score normalization (per backend)
├── Weighted sum (config-driven)
├── Deduplication (heading_path + node_id)
├── Top-k selection (k=10 default)

Reranking (optional):
├── LlamaIndex CohereRerank (external API)
└── Cross-encoder reranker (local model)
```

**Expected Improvement (Hybrid):**
- **hit_rate:** 100% (unchanged, already passing)
- **top1_relevance:** 30% → **85-92%** (hybrid + reranking)
- **stability:** 0% → **80-88%** (hybrid reduces path variance)
- **tree_depth:** 3 (unchanged, already passing)

**Risk:** May still need domain-aligned corpus (Phase 4 WS1) for final quality boost

---

### 4.3 Quantitative Improvement Targets

| Metric | Current | Target | Expected | Gap |
|--------|---------|--------|----------|-----|
| **hit_rate** | 100% | 80% | 100% | ✓ Pass |
| **top1_relevance** | 30% | 90% | 85-92% | ⚠ Near threshold |
| **stability** | 0% | 85% | 80-88% | ⚠ Near threshold |
| **tree_depth** | 3 | 3 | 3 | ✓ Pass |
| **node_chunk_mapping** | 100% | 80% | 100% | ✓ Pass |
| **heading_path** | 100% | 95% | 100% | ✓ Pass |

**Conclusion:** Hybrid retrieval + PageIndex reasoning achieves **near-threshold quality**, but may need Phase 4 domain alignment for final boost.

---

## 5. Implementation Roadmap (Phase 5 Planning)

### 5.1 Phase 5 Scope

**In Scope:**
- PageIndexClient transplantation
- tree_thinning integration
- get_page_content tools
- Reasoning backend (LlamaIndex Agent)
- Hybrid retrieval router
- Configuration unification

**Out of Scope (Phase 4 Dependencies):**
- Domain-aligned validation corpus (Phase 4 WS1)
- Tree depth improvement (Phase 4 WS2)
- Evidence-chain recovery (Phase 4 WS3)

**Frozen Constraints:**
- PostgreSQL registry as source-of-truth
- Frozen provenance contracts
- Distribution-based thresholds (NO distance-based)

---

### 5.2 Phase 5 Workstreams

#### WS1: PageIndex Core Integration (Week 1)

**Objectives:**
- Port PageIndexClient with registry write-back
- Integrate tree_thinning into adapter
- Port get_page_content tools

**Deliverables:**
- `llamaindex_runtime/client/pageindex_client.py` (complete port)
- `llamaindex_runtime/tree/pageindex_adapter.py` (thinning integration)
- `llamaindex_runtime/tools/page_tools.py` (new tools)
- Tests: PageIndexClient + workspace + registry provenance

**Exit Criteria:**
- PageIndexClient.index() writes to PostgreSQL registry
- tree_thinning reduces node count without breaking provenance
- get_page_content extracts correct pages from registry

---

#### WS2: Reasoning Backend + Agent Framework (Week 2)

**Objectives:**
- Implement ReasoningTreeBackend (LlamaIndex ReAct Agent)
- Wire PageIndex tools to Agent
- Test reasoning retrieval on real documents

**Deliverables:**
- `llamaindex_runtime/tree/reasoning_backend.py` (Agent backend)
- `llamaindex_runtime/tree/tools_adapter.py` (PageIndex → LlamaIndex tools)
- Tests: Agent retrieves specific sections (NOT root nodes)

**Exit Criteria:**
- Reasoning backend returns BackendHit (NOT raw JSON)
- Agent targets level 2-3 nodes (NOT root bias)
- Provenance preserved (node_id → span_id → chunk_id)

---

#### WS3: Hybrid Retrieval Router (Week 3)

**Objectives:**
- Implement HybridRouter (multi-backend merging)
- Configuration-driven weights
- Optional reranking integration

**Deliverables:**
- `llamaindex_runtime/tree/hybrid_router.py` (router logic)
- `llamaindex_runtime/config.py` (RuntimeSettings extension)
- Tests: Hybrid retrieval > single backend quality

**Exit Criteria:**
- Hybrid router merges 4 backends correctly
- Configuration controls backend weights
- Hybrid quality > reasoning-only quality

---

#### WS4: Real Validation + Quality Assessment (Week 4)

**Objectives:**
- Run real validation with OPENAI_API_KEY
- Compare baseline vs hybrid path
- Assess quality metrics (top1_relevance, stability)

**Deliverables:**
- `verification/phase5_real_validation/` (validation artifacts)
- Level assessment (baseline vs hybrid)
- Decision: promote hybrid to default or defer

**Exit Criteria:**
- Real validation completes without mock/fallback
- Hybrid path quality metrics available
- Decision framework: promote vs defer (with evidence)

---

### 5.3 Risk Mitigation

| Risk | Mitigation | Owner |
|------|------------|-------|
| **OPENAI_API_KEY unavailable** | Phase 4 WS0 resolver + Phase 5 WS4 fallback to cached LLM responses | Infrastructure |
| **Agent reasoning token cost** | Hybrid router reduces reasoning frequency (clustering backend cheaper) | Backend team |
| **PageIndex provenance drift** | Registry write-back gate + frozen contract check before commit | Integration team |
| **Quality still below threshold** | Phase 4 domain alignment + Phase 5 reranking boost | Validation team |

---

## 6. Decision Framework

### 6.1 Go/No-Go Criteria

**Promote Hybrid to Default:**
- [ ] top1_relevance >= 90% (threshold met)
- [ ] stability >= 85% (threshold met)
- [ ] All frozen contracts preserved
- [ ] Real validation completes (NOT mock)
- [ ] GitNexus reindex shows controlled blast radius

**Defer Hybrid (Keep Baseline):**
- [ ] top1_relevance < 90% (gap persists)
- [ ] stability < 85% (gap persists)
- [ ] Provenance integrity compromised
- [ ] Real validation blocked (API key / credentials)

---

### 6.2 Rollback Plan

**If Hybrid Fails:**
1. Baseline path remains default (no forced promotion)
2. Hybrid path available as optional backend
3. Document blocking factors (Phase 5 summary)
4. Plan Phase 6 fallback (reranking + domain alignment)

---

## 7. Comparison: Plan A (Baseline Fix) vs Plan B (Framework Integration)

| Dimension | Plan A (Baseline Fix) | Plan B (Framework Integration) |
|-----------|----------------------|----------------------------|
| **Scope** | Phase 4 WS1-WS3 (domain + depth + evidence) | Phase 5 full framework integration |
| **Risk** | LOW (incremental fixes) | MEDIUM (framework integration) |
| **Timeline** | 2-3 weeks | 4 weeks |
| **Expected quality boost** | 30% → 60-70% (domain alignment) | 30% → 85-92% (hybrid retrieval) |
| **Root-bias fix** | Indirect (depth improvement) | Direct (reasoning backend) |
| **Token cost** | Unchanged | Increased (Agent reasoning) |
| **Provenance risk** | LOW | MEDIUM (PageIndex integration) |
| **Recommendation** | **First priority** | **Second priority** (after Plan A stabilizes) |

**Recommended Sequence:**
1. **Complete Phase 4 (Plan A)** → stabilize baseline
2. **If Phase 4 still below threshold** → proceed Phase 5 (Plan B)
3. **If Phase 4 reaches threshold** → defer Phase 5 (optional enhancement)

---

## 8. Conclusion

### 8.1 Key Findings

1. **Psi-RAG + HIRO + RAPTOR:** Research-only, NOT transplantation candidates (architectural mismatch)
2. **PageIndex:** Full transplantation candidate (complete integration)
3. **LlamaIndex Core:** Primary framework (already integrated, low risk)
4. **Root-bias cause:** Missing query-aware traversal (PageIndex reasoning fills gap)
5. **Expected improvement:** 30% → 85-92% (hybrid retrieval)

---

### 8.2 Recommendation

**Primary Plan:** Complete **Phase 4 (Plan A)** first
- Domain alignment + depth improvement + evidence recovery
- Lower risk, faster timeline, foundational quality boost

**Secondary Plan:** Proceed **Phase 5 (Plan B)** if Phase 4 insufficient
- PageIndex reasoning + LlamaIndex Agent + Hybrid router
- Direct root-bias fix, higher quality ceiling

**Fallback:** Keep baseline as default, hybrid as optional backend
- Document quality gaps, plan Phase 6 reranking enhancement

---

### 8.3 Next Actions

**Immediate (Phase 4):**
1. Domain-aligned validation corpus (WS1)
2. Tree depth improvement (WS2)
3. Evidence-chain recovery (WS3)
4. Real validation + Level assessment (WS4)

**Conditional (Phase 5):**
1. PageIndexClient integration (WS1)
2. Reasoning backend + Agent (WS2)
3. Hybrid router + config (WS3)
4. Real validation + promotion decision (WS4)

**Frozen Constraints:**
- PostgreSQL registry source-of-truth
- Frozen provenance contracts
- Distribution-based thresholds
- Control package priority order

---

## References

1. `changes/compatibility-adapter-program/00-MASTER.md` - Frozen strategic decision
2. `changes/compatibility-adapter-program/01-ROADMAP.md` - Phase sequence
3. `changes/compatibility-adapter-program/research/psi-rag-skeleton-evaluation.md` - Psi-RAG research
4. `changes/compatibility-adapter-program/research/hiro-skeleton-evaluation.md` - HIRO research
5. `changes/compatibility-adapter-program/research/raptor-structure-evaluation.md` - RAPTOR research
6. `PageIndex功能分析.md` - PageIndex feature analysis
7. `PageIndex完整功能分析与集成方案.md` - PageIndex integration plan
8. `verification/quality-validation-20260528/level_assessment.json` - Current quality baseline
9. `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-RESEARCH.md` - Phase 4 research

---

**Generated by:** Architecture Research Team
**Approved by:** Control Package Compliance Check
**Status:** Ready for Phase 5 planning (conditional on Phase 4 completion)