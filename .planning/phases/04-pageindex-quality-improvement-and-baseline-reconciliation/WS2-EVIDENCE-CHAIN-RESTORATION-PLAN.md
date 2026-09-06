# WS2 Evidence-Chain Restoration and Real Revalidation - Execution Plan

**Created:** 2026-05-31
**Phase:** 4 - PageIndex Quality Improvement and Baseline Reconciliation
**Wave:** WS2
**Status:** READY FOR EXECUTION

---

## Executive Summary

WS0 baseline reconciliation completed successfully (2026-05-31). All planning artifacts now agree on Level 2 as the authoritative baseline.

**WS2 Goal:** Restore real evidence-chain statistics (chunks/mapped_chunks/heading_path) and re-run real quality validation with aligned corpus using frozen thresholds.

**Current Blocker:** Database not running (Docker Desktop inactive), preventing real ingestion and validation.

---

## Current State Analysis

### Evidence-Chain Gap Diagnosis

| Metric | Current (Fake) | Expected (Real) | Gap | Root Cause |
|--------|----------------|-----------------|-----|------------|
| **chunks** | 0 | 200-400 | Missing | Database not running, no ingestion executed |
| **mapped_chunks** | 0 | 160-320 (80%+) | Missing | No node-chunk mapping generated |
| **mapped_chunks_rate** | 0.0% | ≥80% | Threshold failure | Evidence chain incomplete |
| **tree_max_level** | 2 | ≥3 | 1 level short | Shallow tree structure |
| **heading_path_complete** | 0 | 190-380 (95%+) | Missing | No heading extraction executed |
| **heading_path_rate** | 0.0% | ≥95% | Threshold failure | Provenance incomplete |

**Validation Status File:** `verification/phase3-real-validation/validation_status.json` contains fake zero-values, not reflecting real database state.

### Corpus Alignment Status

**Aligned Corpus Identified:** ✅
- File: `PageIndex完整功能分析与集成方案.md` (13KB technical document)
- Domain: PageIndex implementation, tree structure, LLM, retrieval, embedding
- Location: `E:\github\rag\PageIndex完整功能分析与集成方案.md`
- `.env` configuration: `REAL_VALIDATION_DOCUMENT_PATH` points to aligned corpus

**Alignment Analysis:**
- Previous corpus: 竞品分析文档 (competitor analysis) → mismatched query domain (90% irrelevant)
- New corpus: PageIndex技术系统文档 → aligned with business queries (技术系统实现与架构)
- Keyword coverage: ~4.1 keywords/query (high alignment score)
- Expected impact: Dramatic improvement in hit relevance

### Database Infrastructure Status

**Database:** ❌ NOT RUNNING
- Docker Desktop: Inactive (connection error confirmed)
- PostgreSQL container: Not accessible
- `.env` DATABASE_URL: `postgresql://postgres:postgres@localhost:5432/rag` (configured but unreachable)

**Impact:** Cannot execute real ingestion, cannot restore evidence chain, cannot re-run validation.

---

## WS2 Execution Sequence

### Prerequisites

1. **Database Startup Required**
   - Docker Desktop must be running
   - PostgreSQL container must be active
   - Connection test must pass

2. **Aligned Corpus Available**
   - ✅ File exists: `PageIndex完整功能分析与集成方案.md`
   - ✅ `.env` configured: `REAL_VALIDATION_DOCUMENT_PATH` points to aligned corpus

### Task Breakdown

#### Task WS2-01: Database Infrastructure Activation

**Action:**
```bash
# Start Docker Desktop (manual step - user action required)
# Then execute:
docker run --name rag-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=rag \
  -p 5432:5432 \
  -d pgvector/pgvector:pg15

# Run migrations
python run_migrations.py

# Verify connection
python verification/phase3-real-validation/run_validation.py
```

**Expected Output:**
- Database connection successful
- Tables created: documents, document_versions, tree_nodes, canonical_spans, vector_chunk_spans, vector_chunks
- `validation_status.json` shows: `connection_status: "Connected successfully"`

**Acceptance Criteria:**
- Docker container running
- Migration successful
- Connection test passes

#### Task WS2-02: Aligned Corpus Ingestion

**Action:**
```bash
# Ingest aligned corpus with PageIndex workflow
python scripts/run_pageindex_real_retrieval_workflow.py
```

**Script Behavior:**
- Reads `REAL_VALIDATION_DOCUMENT_PATH` from `.env` (PageIndex完整功能分析与集成方案.md)
- Executes PageIndex ingestion pipeline
- Generates tree structure with hierarchical nodes
- Creates vector chunks with embeddings
- Establishes node-chunk mappings
- Extracts heading_path for provenance

**Expected Evidence Chain:**
- tree_nodes: 30-50 nodes (hierarchical, not just root nodes)
- tree_max_level: ≥3 levels (WS1 tree depth fix must complete first)
- vector_chunks: 200-400 chunks
- mapped_chunks: 160-320 chunks (80%+ mapping rate)
- heading_path_complete: 190-380 spans (95%+ completeness)
- embeddings: All chunks embedded successfully

**Acceptance Criteria:**
- `validation_status.json` shows real statistics (not zeros)
- tree_max_level ≥ 3
- mapped_chunks_rate ≥ 80%
- heading_path_rate ≥ 95%

#### Task WS2-03: Evidence-Chain Statistics Restoration

**Action:**
After ingestion, the `validation_status.json` file will automatically reflect real statistics:

```python
# Run validation.py to capture real evidence-chain state
python verification/phase3-real-validation/run_validation.py
```

**Expected validation_status.json update:**
```json
{
  "database_url_configured": true,
  "connection_status": "Connected successfully",
  "data_available": true,
  "stats": {
    "documents": 1,
    "active_versions": 1,
    "chunks": 250,  // Real value (not 0)
    "mapped_chunks": 200,  // Real value (not 0)
    "mapped_chunks_rate": 0.80,  // Real rate (not 0.0)
    "tree_max_level": 3,  // Real depth (not 2)
    "heading_path_complete": 240,  // Real value (not 0)
    "heading_path_rate": 0.96  // Real rate (not 0.0)
  }
}
```

**Acceptance Criteria:**
- No zero-values in stats section
- mapped_chunks_rate ≥ 80%
- heading_path_rate ≥ 95%
- tree_max_level ≥ 3

#### Task WS2-04: Real Quality Validation Re-execution

**Action:**
```bash
# Execute validation with aligned corpus
python verification/phase3-real-validation/run_validation.py

# Generate judgment template
# Template will be populated with hits from aligned corpus

# Manual human judgment (user action required)
# Open judgment_template.csv, fill relevance scores, save as judgment_completed.csv

# Calculate metrics
python verification/phase3-real-validation/calculate_metrics.py
```

**Frozen Thresholds (Phase 2 preserved):**
- hit_rate ≥ 80%
- top1_relevance ≥ 90%
- stability ≥ 85%
- tree_depth ≥ 3
- node_chunk_mapping ≥ 80%
- heading_path_completeness ≥ 95%

**Expected Quality Improvement:**
- hit_rate: From 5% → 60-80% (corpus alignment impact)
- top1_relevance: From 10% → 70-90% (tree depth + corpus alignment)
- stability: From 0% → 80-85% (consistent retrieval behavior)

**Acceptance Criteria:**
- retrieval_results.json generated with hits from aligned corpus
- judgment_completed.csv filled with human relevance scores
- level_assessment.json generated with metrics comparison

#### Task WS2-05: Level Assessment and Go/No-Go Decision

**Action:**
After `calculate_metrics.py` execution, review level_assessment.json:

```json
{
  "assessment_date": "2026-05-31T...",
  "validation_date": "2026-05-31T...",
  "version_id": "...",
  "query_count": 20,
  "metrics": {
    "hit_rate": 0.75,  // Real metric from aligned corpus
    "top1_relevance": 0.85,  // Real metric from human judgment
    "stability": 0.82  // Real metric from consistency check
  },
  "thresholds": {
    "hit_rate": 0.8,  // Frozen from Phase 2
    "top1_relevance": 0.9,  // Frozen from Phase 2
    "stability": 0.85  // Frozen from Phase 2
  },
  "level": {
    "level": "Level_3" | "Level_4",  // Real determination
    "level_description": "...",
    "passed_thresholds": {...},
    "blocking_factors": [...]  // Empty if Level 4
  }
}
```

**Go/No-Go Decision:**
- **GO (Level 4):** All 6 thresholds passing → System ready for main-function closure
- **NO-GO (Level 3):** 1-2 thresholds failing → Quality improved but not ready for closure
- **NO-GO (Level 2):** 3+ thresholds failing → Major quality gaps remain

**Acceptance Criteria:**
- level_assessment.json reflects real metrics (not fixture-based)
- Level determination based on frozen thresholds (no relaxation)
- FINAL-REPORT.md updated with new closeout decision

---

## Dependencies

### WS1 Tree Depth Fix (Parallel)

WS2 requires tree_depth ≥ 3. If WS1 has not completed tree structure fix, WS2 validation will still fail tree depth threshold.

**WS1 Status Check:**
- Inspect `PageIndex完整功能分析与集成方案.md` structure
- Verify PageIndex adapter generates hierarchical tree (not flat)
- Check tree_nodes table after ingestion: expect nodes with level_no=1,2,3

**If WS1 incomplete:**
- WS2 will expose tree depth failure in level_assessment
- Decision: Continue WS2 to gather evidence, then fix tree depth in subsequent iteration

### Frozen Thresholds (Phase 2)

All thresholds must remain frozen. No relaxation allowed.

**Validation:** Check that `calculate_metrics.py` uses identical thresholds from Phase 2:
```python
thresholds = {
    "hit_rate": 0.8,
    "top1_relevance": 0.9,
    "stability": 0.85,
}
```

---

## Expected Outcomes

### Success Scenario (Level 3/4)

- Evidence chain restored: chunks/mapped_chunks/heading_path show real values
- Corpus aligned: Technical system document matches business queries
- Quality improved: hit_rate 60-80%, top1_relevance 70-90%
- Level assessment: Level 3 or Level 4 (based on frozen thresholds)
- Closeout decision: GO (if Level 4) or NO-GO with specific blockers (if Level 3)

### Partial Success (Level 2→3 transition)

- Evidence chain restored
- Corpus alignment successful
- Quality improved but thresholds not all passing
- Level assessment: Level 3 (hit_rate passing, others failing)
- Closeout decision: NO-GO with specific blocker list (e.g., "top1_relevance: 85% (need ≥90%)")

### Failure Scenario (Level 2 persistent)

- Evidence chain still incomplete
- Tree depth still shallow
- Corpus alignment failed
- Level assessment: Level 2 (quality unchanged)
- Closeout decision: NO-GO with comprehensive blocker list

---

## Final Deliverables

### Required Artifacts

1. **validation_status.json** - Real evidence-chain statistics (no zeros)
2. **retrieval_results.json** - Hits from aligned corpus validation
3. **judgment_completed.csv** - Human relevance scores for aligned corpus hits
4. **level_assessment.json** - Real Level determination with frozen thresholds
5. **FINAL-REPORT.md** - Updated closeout decision with go/no-go judgment

### Summary Document

Create: `E:/github/rag/.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md`

Content:
- WS0 baseline reconciliation record
- WS1 corpus alignment + tree depth status
- WS2 evidence-chain restoration + validation rerun results
- Final Level assessment
- Go/No-Go closeout decision
- Remaining blockers (if NO-GO)
- Phase 4 closure recommendation

---

## Execution Status

**Current Status:** READY FOR EXECUTION (pending database startup)

**Blocker:**
- Database not running (Docker Desktop inactive)
- User action required: Start Docker Desktop, run PostgreSQL container

**Next Action:**
1. User starts Docker Desktop
2. User runs database setup commands
3. Agent executes WS2-01 through WS2-05 tasks
4. Agent generates FINAL-REPORT.md and closeout decision

---

**Plan Created:** 2026-05-31
**Ready for:** WS2 execution (pending infrastructure activation)