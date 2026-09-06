---
phase: 4
phase_name: "PageIndex Quality Improvement and Baseline Reconciliation"
project: "rag"
generated: "2026-05-31"
closed: "2026-06-07"
counts:
  decisions: 7
  lessons: 8
  patterns: 4
  surprises: 4
missing_artifacts:
  - "VERIFICATION.md"
  - "UAT.md"
---

# Phase 4 Learnings: PageIndex Quality Improvement and Baseline Reconciliation

## Decisions

### Unified Level 2 as Authoritative Baseline

Eliminated split-brain across planning artifacts by marking Phase 2 Level 3 as fixture-provisional (non-authoritative) and establishing Phase 3 Level 2 as the unified baseline for Phase 4 starting point.

**Rationale:** Phase 2 validation used fixture-based mock data that produced artificially high quality metrics (hit_rate 100%), while Phase 3 real validation with PostgreSQL/LLM/human judgment revealed true quality (hit_rate 5%). Planning artifacts did not explicitly distinguish fixture-provisional vs real-authoritative baselines, causing conflicting baseline narratives across STATE.md, workspace-memory.json, and validation outputs.
**Source:** 04-SUMMARY.md, STATE.md

---

### Selected PageIndex完整功能分析与集成方案.md as Aligned Corpus

Selected technical system document (PageIndex完整功能分析与集成方案.md) as aligned validation corpus with 4.1 keywords/query coverage, replacing mismatched competitive analysis document.

**Rationale:** Phase 3 validation used mismatched document/query domains - validation corpus was competitive analysis document, but business queries targeted technical system implementation. This caused 90% queries (18/20) to return irrelevant results. Selected corpus matches business query domain (技术系统实现与架构) with excellent keyword coverage: PageIndex (41 occurrences), 检索 (14), embedding (11), LLM (8), 树结构 (6).
**Source:** 04-PLAN-02.md, corpus_alignment_report.md, 04-SUMMARY.md

---

### Tree Depth NO FIX REQUIRED - Corrected Misconception

Decision: No tree depth fix required. Corrected Phase 3 misconception that tree structure was shallow (max_level 1). Actual tree has max_level_no=2, which means 3 levels (0-based counting).

**Rationale:** Phase 3 report incorrectly interpreted tree_max_level=2 as "only 2 levels". Actually means: deepest nodes at level_no=2 (3 levels total when counting from 0). Level computation logic verified correct: level_no = len(heading_path.split('/')) - 1. Threshold "tree depth >= 3" means max_level_no >= 2, which Phase 3 tree already satisfied.
**Source:** tree_depth_analysis_report.md, 04-SUMMARY.md

---

### Root-Bias Identified as Retrieval Behavior Issue

Root-bias (90% top1 hits were root node in Phase 3) identified as retrieval behavior + document structure issue, not tree depth issue.

**Rationale:** Tree had sufficient depth (3 levels), but ReasoningTreeBackend uses LLM reasoning that prefers broad context first (root node). Competitive analysis document structure: root mentions everything superficially, lacks specifics. Expected resolution after corpus alignment: technical system document has detailed subsections, LLM reasoning will match queries to specific sections, root-bias will naturally decrease.
**Source:** tree_depth_analysis_report.md, 04-SUMMARY.md

---

### Phase 4 CLOSED with Blockers Documented

Decision: Phase 4 closed with WS0/WS1 completion documented, WS2 retrieval completion documented, judgment integrity issue documented, and evidence-chain zeros identified for next phase. Authoritative Level 2 baseline preserved.

**Rationale:** WS0 (baseline reconciliation) and WS1 (corpus alignment + tree depth analysis) completed successfully. WS2 retrieval executed successfully (71 hits from aligned corpus), but critical validation integrity issue discovered (judgments collected for old corpus, not new corpus). Evidence-chain statistics show zeros (chunks=0, mapped_chunks=0, heading_path_rate=0), indicating incomplete ingestion pipeline. Invalid Level 3 assessment must be discarded. Phase 4 closed with blockers documented for next phase: evidence-chain verification + EvidenceContentResolver consolidation. Authoritative baseline remains Level 2 from Phase 3.
**Source:** 04-SUMMARY.md, STATE.md

---

### Frozen Thresholds Preserved Without Relaxation

Decision: All quality thresholds remain frozen from Phase 2 validation framework. No threshold relaxation allowed in Phase 4 Level assessment.

**Rationale:** Phase 2 established explicit quality thresholds: hit_rate ≥80%, top1_relevance ≥90%, stability ≥85%, tree_depth ≥3, node_chunk_mapping ≥80%, heading_path ≥95%. Level progression criteria frozen: Level 2 (unverified) → Level 3 (hit_rate passing) → Level 4 (all thresholds passing). Phase 4 Level assessment must use identical thresholds without relaxation to maintain validation integrity.
**Source:** 04-VALIDATION.md, STATE.md

---

### Evidence-Chain Restoration Execution Plan Documented

Decision: Complete WS2 execution plan documented with 5 tasks (database activation, corpus ingestion, evidence-chain statistics restoration, validation rerun, Level assessment) awaiting infrastructure activation.

**Rationale:** Evidence-chain statistics (chunks/mapped_chunks/heading_path) currently show zero values even though the database was reachable during the latest validation snapshots. This means the remaining issue is not simply infrastructure startup; the next phase must verify active_version-scoped DB counts, ingestion materialization, and metric-table/version alignment before claiming evidence-chain recovery. WS2 execution planning remains useful, but its assumptions must be checked against the current DB-backed zero snapshot.
**Source:** WS2-EVIDENCE-CHAIN-RESTORATION-PLAN.md, 04-SUMMARY.md

---

## Lessons

### Baseline Reconciliation Essential Before Quality Improvement

Baseline reconciliation is essential before quality improvement work. Split-brain across planning artifacts causes confusion and prevents accurate progress tracking.

**Context:** Phase 3 completion created split-brain: STATE.md and workspace-memory.json recorded Level 2, but level_assessment.json reported Level 3. This happened because Phase 2 fixture-based validation (Level 3) and Phase 3 real validation (Level 2) both generated level_assessment.json files, but planning artifacts did not distinguish fixture-provisional vs real-authoritative baselines. WS0 reconciliation eliminated split-brain by marking Phase 2 Level 3 as fixture-provisional and establishing Phase 3 Level 2 as unified baseline.
**Source:** 04-PLAN-01.md, 04-SUMMARY.md

---

### Corpus/Query Alignment More Important Than Tree Depth

Corpus/query alignment is more important than tree depth for retrieval quality. Domain mismatch has larger impact than structural depth.

**Context:** Phase 3 bottleneck analysis incorrectly prioritized tree depth (max_level 1) as major blocker. WS1 analysis revealed tree depth was actually sufficient (3 levels), but corpus/query domain mismatch (competitive analysis vs technical system queries) was the real root cause of 90% irrelevant hits. Corpus alignment (PageIndex技术文档) will have larger impact on hit_rate improvement than any tree depth fix.
**Source:** corpus_alignment_report.md, preparation_summary.md, 04-SUMMARY.md

---

### Tree Depth Misconceptions from 0-Based Level Numbering

Tree depth misconceptions can arise from 0-based level numbering vs human counting conventions. Level_no=2 means 3 levels, not 2 levels.

**Context:** Phase 3 report claimed "tree structure shallow (max_level: 1)" based on tree_max_level value from database query. Actually tree_max_level=2 means deepest nodes at level_no=2 (3 levels total when counting from level 0). PageIndex adapter uses 0-based level numbering: Level 0 (root), Level 1 (subsections), Level 2 (details). Threshold "tree depth >= 3" means max_level_no >= 2, which Phase 3 tree already satisfied. Misconception caused unnecessary focus on tree depth fix.
**Source:** tree_depth_analysis_report.md, 04-SUMMARY.md

---

### Root-Bias is Retrieval Behavior Issue

Root-bias (top1 hits dominated by root node) is retrieval behavior issue, not tree structure issue. LLM reasoning prefers broad context first.

**Context:** Phase 3 validation showed root node appeared in 18/20 queries (90%) as top1 hit. Initial assumption: tree structure too shallow, LLM cannot navigate deeper. WS1 analysis revealed tree depth was sufficient (3 levels), but ReasoningTreeBackend uses LLM reasoning that prefers starting from root (broad context). Competitive analysis document structure: root mentions everything superficially, lacks specifics. Root-bias cause: retrieval behavior + document structure, NOT tree depth. Expected resolution: corpus alignment with technical system document (detailed subsections) will naturally reduce root-bias.
**Source:** tree_depth_analysis_report.md, preparation_summary.md, 04-SUMMARY.md

---

### Infrastructure Blockers Halt Entire Validation Workflow

Infrastructure blockers can halt entire validation workflow. Database dependency prevents ingestion, evidence-chain restoration, and validation execution.

**Context:** WS2 (evidence-chain restoration + validation rerun) execution plan is complete with 5 documented tasks, but cannot proceed because database infrastructure inactive (Docker Desktop not running). Cannot execute aligned corpus ingestion, cannot restore evidence-chain statistics (chunks/mapped_chunks/heading_path remain zero), cannot re-run quality validation, cannot determine final Level judgment (Level 3/4 assessment impossible without validation data). Entire WS2 workflow blocked by single infrastructure dependency.
**Source:** WS2-EVIDENCE-CHAIN-RESTORATION-PLAN.md, 04-SUMMARY.md

---

### Partial Completion with Blocker Documentation Allows Clean Closure

Partial completion with blocker documentation allows clean closure and immediate resumption after blocker resolution.

**Context:** Phase 4 achieved 82% completion (WS0/WS1 complete, WS2 retrieval complete). Instead of waiting indefinitely for human judgment collection, created comprehensive closure documentation: 04-SUMMARY.md documents WS0/WS1 completion, WS2 retrieval completion, judgment integrity issue, evidence-chain zeros, and closure recommendation. STATE.md updated to CLOSED status with blockers documented. After evidence-chain verification and resolver consolidation, human judgment collection can proceed with new corpus hits. Clean closure prevents project state ambiguity and enables efficient resumption.
**Source:** 04-SUMMARY.md, STATE.md

---

### Fixture-Based Validation Overestimates Quality

Fixture-based validation severely overestimates quality compared to real validation with actual data and human judgment.

**Context:** Phase 2 fixture-based validation: hit_rate 100%, top1_relevance 34.5%, stability 100%, Level 3 (fixture-provisional). Phase 3 real validation: hit_rate 5%, top1_relevance 10%, stability 0%, Level 2 (authoritative). 20x difference in hit_rate (100% vs 5%). Root cause: fixture data精心设计匹配查询, mock judgment relaxed, no real retrieval challenges. Real validation exposed true quality gaps. Proved: manual human judgment essential for accurate assessment, fixture-based validation unreliable for quality assessment.
**Source:** 04-SUMMARY.md, STATE.md, verification/phase3-real-validation/FINAL-REPORT.md

---

### Evidence-Chain Zeros Indicate Incomplete Ingestion Pipeline

Evidence-chain zeros (chunks=0, mapped_chunks=0, heading_path_rate=0) indicate incomplete ingestion pipeline that generates tree nodes but not chunk-level content.

**Context:** WS2 validation shows documents=2, tree_max_level=2, but chunks=0, mapped_chunks=0, heading_path_complete=0. Tree nodes were generated successfully, but no chunks were materialized. This suggests ingestion pipeline executes tree generation step but does not hydrate EvidenceContentResolver with chunk-level content. Preview/content-hydration mechanism needs verification. Evidence-chain thresholds (node_chunk_mapping >=80%, heading_path >=95%) cannot be assessed without full ingestion.
**Source:** 04-SUMMARY.md, validation_status.json

---

## Patterns

### Baseline Reconciliation Pattern

Pattern for eliminating split-brain across planning artifacts: (1) identify conflicting baseline narratives, (2) mark non-authoritative baselines with metadata, (3) establish unified baseline as authoritative, (4) update all planning artifacts consistently.

**When to use:** When project has multiple validation phases with different baseline assessments (fixture vs real, mock vs human judgment), and planning artifacts reference conflicting baselines causing confusion about current quality level.
**Source:** 04-PLAN-01.md, 04-SUMMARY.md

---

### Corpus Alignment Analysis Pattern

Pattern for corpus/query domain alignment: (1) analyze query keyword distribution, (2) identify domain mismatch (corpus domain vs query domain), (3) search for matching corpus candidates, (4) calculate keyword coverage score (keywords/query), (5) select corpus with highest coverage, (6) update configuration, (7) document alignment rationale.

**When to use:** When validation shows high percentage of irrelevant hits (>50% queries with no relevant results), indicating corpus/query domain mismatch. Use keyword coverage analysis to select matching corpus before quality optimization work.
**Source:** 04-PLAN-02.md, corpus_alignment_report.md

---

### Tree Depth Analysis Pattern

Pattern for investigating tree depth issues: (1) read validation_status.json tree_max_level value, (2) verify level_no computation logic in adapter code, (3) test level computation with heading_path examples, (4) check level numbering convention (0-based vs 1-based), (5) interpret threshold correctly (depth >= 3 means max_level_no >= 2 for 0-based), (6) diagnose root-bias cause separately from depth issue.

**When to use:** When validation reports tree depth threshold failure, or when tree structure is suspected as retrieval bottleneck. Prevent misconceptions by verifying level numbering convention before attempting depth fixes.
**Source:** tree_depth_analysis_report.md, 04-PLAN-02.md

---

### Infrastructure Blocker Documentation Pattern

Pattern for handling infrastructure blockers: (1) identify blocker (specific infrastructure dependency), (2) document complete execution plan for remaining tasks, (3) list blocker resolution steps (user actions required), (4) create closure summary documenting completion status and blockers, (5) update STATE.md to CLOSE-READY with blocker documentation, (6) enable immediate resumption after blocker resolution.

**When to use:** When infrastructure dependencies (database, credentials, services) prevent execution of validation or quality assessment tasks. Document execution plan ready for implementation, identify blocker clearly, allow clean closure without waiting indefinitely.
**Source:** WS2-EVIDENCE-CHAIN-RESTORATION-PLAN.md, 04-SUMMARY.md

---

## Surprises

### Tree Depth Misconception - Level_no=2 is 3 Levels

Tree depth misconception: Phase 3 report incorrectly interpreted tree_max_level=2 as "only 2 levels", but actual tree has 3 levels (0-based level numbering: level 0, 1, 2 = 3 levels total).

**Impact:** Unnecessary focus on tree depth fix in Phase 4 planning. WS1 investigation revealed misconception and corrected understanding: max_level_no=2 means deepest nodes at level_no=2, which corresponds to 3 hierarchical levels. Threshold "tree depth >= 3" was already satisfied. Saved effort by avoiding unnecessary tree depth fix work.
**Source:** tree_depth_analysis_report.md, 04-SUMMARY.md

---

### Fixture vs Real Quality Gap - 20x Difference

Surprising quality gap between fixture-based validation (Phase 2: hit_rate 100%) and real validation (Phase 3: hit_rate 5%) - 20x difference, not minor variation.

**Impact:** Proved fixture-based validation severely overestimates quality and is unreliable for readiness assessment. Changed validation strategy: Phase 4 must use real PostgreSQL data, real LLM retrieval, and human judgment for accurate Level assessment. Fixture validation useful for infrastructure correctness testing, but NOT for quality assessment.
**Source:** 04-SUMMARY.md, STATE.md

---

### Evidence-Chain Zeros Require DB-Backed Materialization Verification

Evidence-chain statistics (chunks, mapped_chunks, heading_path) all show zero values in validation_status.json despite a successful DB-backed retrieval snapshot.

**Impact:** The zeros cannot be dismissed as normal or purely infrastructure-related. They indicate a next-phase blocker: verify the active_version-scoped counts, ingestion materialization path, metric query scope, and heading_path storage contract before running final judgment collection or Level assessment.
**Source:** 04-SUMMARY.md, validation_status.json

---

### Root-Bias Cause - Retrieval Behavior Not Depth

Root-bias cause was retrieval behavior (LLM prefers broad context) + document structure (root mentions everything superficially), not tree depth issue as initially assumed.

**Impact:** Changed focus from tree depth fix to corpus alignment. WS1 analysis revealed tree depth was sufficient (3 levels), but ReasoningTreeBackend LLM reasoning prefers starting from root for broad context. Competitive analysis document structure amplified root-bias (root mentions all topics but lacks specifics). Expected resolution: corpus alignment with technical system document (detailed subsections) will naturally reduce root-bias without any code changes.
**Source:** tree_depth_analysis_report.md, preparation_summary.md, 04-SUMMARY.md

---

## Phase 4 Closure Status

**Workstream Completion:**
- WS0 (Baseline Reconciliation): ✅ COMPLETE
- WS1 (Corpus Alignment & Tree Depth Analysis): ✅ COMPLETE
- WS2 Retrieval: ✅ COMPLETE
- WS2 Judgments / Evidence-Chain / Level Assessment: ❌ CLOSED WITH BLOCKERS

**Blockers:** Human judgments were not collected for the new corpus hits, the invalid Level 3 assessment was discarded, and DB-backed evidence-chain metrics remain zero (`chunks=0`, `mapped_chunks=0`, `heading_path_rate=0`).

**Next Steps:** Start the next phase with evidence-chain verification, EvidenceContentResolver consolidation, active_version DB count checks, heading_path storage-contract verification, and then human judgment collection for the 71 new corpus hits.

**Phase 4 Closure Recommendation:** CLOSED with blockers documented. Phase 4 cleanly closes WS0/WS1/retrieval work while preserving authoritative Level 2 and carrying unresolved evidence-chain/judgment work into the next phase.

---

**Learnings Extracted:** 2026-05-31
**Extraction Source:** Phase 4 planning artifacts (PLAN files, SUMMARY, VALIDATION, STATE)
**Missing Artifacts:** VERIFICATION.md, UAT.md (optional, not found)