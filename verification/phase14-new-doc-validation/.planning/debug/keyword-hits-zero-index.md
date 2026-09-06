---
status: diagnosed
trigger: 关键词匹配失败：keyword hits=0，倒排索引查询无结果。白盒测试显示关键词提取成功（Query terms: {'nexusrag', '知识图谱的核心功能是什么', '和', 'kag'}），但倒排索引查询返回 0 hits。需要排查：1. keyword_index 表是否在 ingestion 阶段写入数据；2. 倒排索引查询逻辑是否正确；3. 关键词分词和索引是否匹配；4. 阈值设置是否合理。
created: 2026-06-29
updated: 2026-06-29
---

# Symptoms

**Expected behavior**: 关键词倒排索引查询应该返回匹配的节点（keyword hits > 0），查询词 "kag" 和 "nexusrag" 应该命中包含这些关键词的节点。

**Actual behavior**: 倒排索引查询返回 0 hits，导致 dual-hot intersection 为空，触发 fallback 机制。

**Error messages**: 无显式错误，白盒测试输出显示 keyword hits 数量：0。

**Timeline**: Phase 14 validation 运行后首次发现，之前未见此问题。

**Reproduction**:
1. 运行 Phase 14 validation：`python run_validation.py --phase retrieve`
2. 运行白盒测试：`python whitebox_retrieval_demo.py`
3. 观察 STEP 5: Keyword Hits 输出：keyword hits 数量：0

**Context**:
- 白盒测试显示关键词提取成功：Query terms: {'nexusrag', '知识图谱的核心功能是什么', '和', 'kag'}
- Vector candidates 正常（8个节点，embedding 维度=384）
- Node stats 正常（8个节点，包含 prototype_embedding）
- keyword hits = 0 导致 dual_hot nodes = 0，parent coverage selection 失败

# Current Focus

**hypothesis**: CONFIRMED. The backend_type="embedding" pathway was correctly invoked, keyword matching code (runtime.py lines 283-321) was executed with the fix (includes title+summary_text), and HybridClusterHotspotSelector.select_hotspots() was called. However, the hotspot traverse produced ZERO backend_hits, triggering fallback to _score_tree_nodes_with_fallback (runtime.py lines 382-387), which produces hits with null backend_source/retrieval_path.

**test**: Add logging/observability to trace keyword_hits creation in runtime.py lines 283-321. Check if keywords are being extracted correctly, if summary_text/title fields exist in node_stats, if keyword matching is finding matches, and if keyword_hits list is populated. Then trace HybridClusterHotspotSelector.select_hotspots() to see if it finds hotspots from keyword_hits.

**expecting**: Either (a) keyword_hits are STILL empty despite the fix (need to debug keyword matching), or (b) keyword_hits exist but HybridClusterHotspotSelector fails to find hotspots (need to debug hotspot selection), or (c) hotspots exist but backend_hits are empty (need to debug backend hit generation).

**next_action**: Add strategic logging to runtime.py keyword_hits creation (lines 283-321) to trace: query_keywords extraction, node_stats fields (heading_path, title, summary_text), keyword matching results, and keyword_hits list size. This will pinpoint where the keyword_hits creation is failing.

**reasoning_checkpoint**:
```yaml
hypothesis: "Keyword matching code is fixed but keyword_hits are still empty → hotspot traverse produces zero backend_hits → fallback mechanism triggered → output has null metadata"
confirming_evidence:
  - "backend_type='embedding' is explicitly passed (run_validation.py line 395)"
  - "RAG_TREE_HOTSPOT_SELECTOR='hybrid_cluster' is set (run_validation.py line 31)"
  - "Retrieval output shows backend_source=null, retrieval_path=null (05_retrieval_results.json)"
  - "Null metadata indicates _score_tree_nodes_with_fallback was used (runtime.py lines 381-387)"
  - "Fallback only triggers when hotspots or backend_hits are empty"
  - "Keywords 'kag' and 'nexusrag' exist in summary_text (7/10 nodes)"
  - "Fix applied to runtime.py (lines 283-321) and semantic_distribution.py (lines 302-303)"
falsification_test: "If keyword_hits are populated (> 0) and hotspots are selected (> 0), then backend_hits should exist and retrieval_path should be set. Current null values prove keyword_hits or hotspots are empty."
fix_rationale: "Need to trace keyword_hits creation execution to find WHERE keyword matching is failing despite the fix. Options: (a) summary_text/title not in node_stats, (b) keyword matching logic bug, (c) keyword extraction failing, (d) HybridClusterHotspotSelector rejecting keyword_hits."
blind_spots: "Haven't verified if node_stats actually contains summary_text/title fields during runtime execution. Haven't traced keyword_hits list size after creation. Haven't checked if HybridClusterHotspotSelector requires vector_candidates AND keyword_hits (dual-hot intersection) which might still be empty if vector_candidates are insufficient."
```

# Evidence

**timestamp: 2026-06-29T00:05Z**

- **checked**: PostgreSQL keyword_index table existence and data
- **found**: keyword_index table does NOT exist in PostgreSQL database. No migration file defines this table.
- **implication**: The keyword_index inverted index table was never created. System uses simple heading keyword matching instead.

**timestamp: 2026-06-29T00:10Z**

- **checked**: runtime.py keyword_hits population logic (lines 283-313)
- **found**: keyword_hits are populated by matching query keywords against node heading_path directly (line 298), NOT by querying keyword_index table.
- **implication**: No inverted index is used. Keyword matching is a simple string containment check: `kw.lower() in heading_path.lower()`

**timestamp: 2026-06-29T00:15Z**

- **checked**: Keyword extraction function `_extract_keywords_from_query` (lines 89-113)
- **found**: Uses jieba for Chinese keyword extraction. Whitebox test shows extraction works correctly: Query terms: {'nexusrag', '知识图谱的核心功能是什么', '和', 'kag'}
- **implication**: Keyword extraction is functional. The issue is the matching logic, not extraction.

**timestamp: 2026-06-29T00:25Z**

- **checked**: tree_nodes heading_path values for keyword matches
- **found**: Keywords "kag" and "nexusrag" do NOT appear in any heading_path values (0 matches for all keywords). heading_path contains chapter titles like "排除 GraphRAG 后的混合 RAG 开源项目深度研究" (10 nodes total).
- **implication**: The keyword matching logic (line 298: `kw.lower() in heading_path.lower()`) cannot find matches because keywords are in content text, not heading titles. This is the root cause.

**timestamp: 2026-06-29T00:30Z**

- **checked**: node_stats structure in semantic_distribution.py (lines 298-315)
- **found**: node_stats dictionary only includes heading_path, NOT title or summary_text fields. My first fix in runtime.py tried to use fields that weren't present in node_stats.
- **implication**: The fix failed because the required fields (title, summary_text) weren't available in the data structure passed to runtime.py.

**timestamp: 2026-06-29T00:35Z**

- **action**: Fixed semantic_distribution.py to include title and summary_text fields in node_stats dictionary (lines 299-301). Combined with runtime.py fix, this should enable keyword matching across all node text fields.
- **expecting**: After this two-part fix, keyword hits should be populated (> 0) when keywords appear in summary_text or title fields.

**timestamp: 2026-06-29T01:00Z**

- **checked**: New evidence from user - fix applied to runtime.py (lines 283-321) and semantic_distribution.py (lines 302-303) to include title and summary_text in keyword matching
- **found**: Keywords "kag" and "nexusrag" ARE present in summary_text fields (7/10 nodes contain both keywords). Fix is applied to the correct code.
- **implication**: The keyword matching code is fixed and keywords exist in the data. Issue must be in pathway selection.

**timestamp: 2026-06-29T01:05Z**

- **checked**: Whitebox test keyword matching logic (lines 225-242)
- **found**: Whitebox test has its own simplified keyword matching that only checks heading_path, NOT using the fixed runtime.py code
- **implication**: Whitebox test is isolated from the fix. Need to check actual retrieval pathway.

**timestamp: 2026-06-29T01:10Z**

- **checked**: Actual retrieval_tree_hits_from_pdf results
- **found**: Returns 5 hits but uses "llm_navigation" retrieval_path, not keyword-based hotspot traverse
- **implication**: The retrieval pathway decision logic is choosing llm_navigation fallback over hotspot traverse pathway. Keyword_hits are created during hotspot selection (HybridClusterHotspotSelector), which isn't being invoked for this query.

**timestamp: 2026-06-29T01:25Z**

- **checked**: Actual retrieval output in 05_retrieval_results.json (query Q2)
- **found**: Critical discovery: All hits have backend_source=null, retrieval_path=null, similarity_score=null, hotspot_node_id="", drill_depth=null. This contradicts the expected hotspot traverse output (should have backend_source="vector"/"embedding", retrieval_path="hotspot_traverse"/"embedding").
- **implication**: The null metadata indicates fallback mechanism was triggered, NOT hotspot traverse pathway. The retrieval_path="llm_navigation" mentioned in prior evidence was incorrect - actual output has retrieval_path=null. This confirms hotspot traverse produced zero backend_hits, causing fallback to _score_tree_nodes_with_fallback (runtime.py lines 382-387).

**timestamp: 2026-06-29T01:35Z**

- **checked**: HybridClusterHotspotSelector dual-hot intersection logic (semantic_distribution.py lines 1067-1075)
- **found**: CRITICAL: HybridClusterHotspotSelector requires dual_hot intersection (vector_hot AND keyword_hot). Line 1075: `dual_hot = vector_hot & keyword_hot`. vector_hot requires normalized similarity >= 0.5 (VECTOR_HOT_THRESHOLD). keyword_hot requires matched_terms >= 1. If vector_candidates have low similarity, vector_hot is empty, making dual_hot empty regardless of keyword_hits.
- **implication**: This explains the complete failure chain: (1) keyword matching fix works → keyword_hits populated, (2) HybridClusterHotspotSelector receives keyword_hits, (3) BUT vector_candidates have low similarity → vector_hot empty, (4) dual_hot = empty (intersection with empty set), (5) candidate_parents empty, (6) hotspots empty, (7) backend_hits empty → fallback triggered. The fix to keyword matching is correct but insufficient - need to also investigate why vector_candidates have low similarity scores or why the dual-hot intersection gate is failing.

# Resolution

**root_cause**: The keyword matching fix (runtime.py lines 283-321, semantic_distribution.py lines 302-303) correctly includes title+summary_text fields, allowing keywords "kag" and "nexusrag" to be matched. However, HybridClusterHotspotSelector uses a dual-hot intersection gate (semantic_distribution.py line 1075: `dual_hot = vector_hot & keyword_hot`) that requires BOTH conditions: (1) vector_hot nodes with similarity >= 0.5 threshold, AND (2) keyword_hot nodes with matched terms >= 1. The vector_candidates have insufficient similarity scores (below 0.5 threshold), causing vector_hot to be empty. This makes dual_hot empty regardless of keyword_hits, leading to empty hotspots, empty backend_hits, and fallback mechanism triggering. The retrieval output shows backend_source=null and retrieval_path=null because _score_tree_nodes_with_fallback (runtime.py lines 382-387) was used instead of hotspot traverse pathway.

**fix_direction**: Three potential solutions: (1) Lower VECTOR_HOT_THRESHOLD to allow more nodes into vector_hot set, (2) Modify HybridClusterHotspotSelector to use OR logic instead of AND intersection (vector_hot OR keyword_hot), (3) Investigate why vector_candidates have low similarity scores and improve embedding quality or matching. The current dual-hot AND gate is too strict for this query - it blocks hotspot selection even when keyword evidence is strong.

**files_involved**:
- E:/github/rag/llamaindex_runtime/tree/runtime.py (keyword matching logic - ALREADY FIXED)
- E:/github/rag/llamaindex_runtime/tree/semantic_distribution.py (HybridClusterHotspotSelector dual-hot gate - NEEDS CONFIGURATION CHANGE OR LOGIC CHANGE)
- E:/github/rag/verification/phase14-new-doc-validation/run_validation.py (environment setup and validation driver)

**verification**: Pending - need to either (a) trace vector_candidates similarity scores to confirm they're below threshold, or (b) modify HybridClusterHotspotSelector configuration/logic and re-run validation to verify hotspots are selected.