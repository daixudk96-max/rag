# Phase 2: PageIndex Main-Function Quality Validation and Closure - Research

**Researched:** 2026-05-28
**Domain:** PageIndex quality verification, tree structure validation, evidence-chain completeness, main-function readiness assessment
**Confidence:** HIGH - Based on live verification evidence, real database state, and comprehensive codebase analysis

## Summary

Phase 2 focuses on transitioning PageIndex from technical integration success (Phase 1 bug fix completed) to quality-verified main-function readiness. The verification evidence reveals PageIndex currently operates at **Level 2: "能查但质量未验证"** (Can query but quality unverified) with critical gaps in tree structure, query quality validation, and evidence-chain completeness.

The white-box verification (2026-05-27) confirmed: database connectivity works, documents ingest successfully, embeddings generate completely (326/326), and evidence chain exists structurally. However, tree structure is oversimplified (only root nodes, no hierarchy), node-chunk mapping rate is critically low (21.5%), heading paths are incomplete (20% None), and no real query quality tests have been executed.

**Primary recommendation:** Implement systematic quality validation workflow: (1) diagnose and fix tree generation algorithm to produce hierarchical structure, (2) execute 10+ real query tests with quality metrics, (3) improve node-chunk mapping to >80%, (4) fix heading_path completeness to >95%, and (5) establish explicit quality grading criteria for main-function readiness.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Query quality validation | Test / Verification | API / Backend | Quality assessment requires systematic test execution and metrics collection, but retrieval implementation must support quality measurement |
| Tree structure generation | Tree Adapter | Backend | PageIndexTreeAdapter owns tree building logic, ReasoningTreeBackend consumes tree structure for retrieval |
| Evidence-chain completeness | Registry / Storage | Tree Adapter | Registry owns data persistence and provenance, Tree Adapter generates span-node-chunk mappings |
| Quality grading criteria | Verification / Documentation | Project Management | Explicit readiness criteria definition requires verification evidence synthesis and project-level acceptance standards |
| Tree navigation (LLM reasoning) | Backend (ReasoningTreeBackend) | API | ReasoningTreeBackend implements LLM-based tree navigation, API layer orchestrates backend selection |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUAL-01 | Query quality validation - execute real tests, measure hit rate, relevance, stability | Verification evidence shows query quality unverified; white-box test reveals theoretical capability but no execution. Need: systematic query test framework with quality metrics. |
| QUAL-02 | Tree structure quality - diagnose why only root nodes generated, fix to produce 3+ level hierarchy | Tree nodes table shows only level=0 nodes. PageIndexTreeAdapter._flatten_embedded_tree should produce hierarchy. Need: algorithm diagnosis and fix. |
| QUAL-03 | Evidence-chain completeness - achieve >80% node-chunk mapping, >95% heading_path completeness | Current: 21.5% node-chunk mapping (70/326), 80% heading_path (64/326 None). Registry evidence shows structural completeness but insufficient mapping coverage. |
| QUAL-04 | Final closeout criteria - define explicit Level 4+ grading standards | Verification document defines Level progression (L1-L5) but current at L2. Need: explicit criteria for L4 "查得稳定好" readiness with measurable thresholds. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=8.3.0 | Testing framework | Project standard for all integration/unit tests, supports markers for categorization [VERIFIED: pyproject.toml] |
| psycopg[binary] | >=3.2.0 | PostgreSQL driver | Registry storage backend, verified in live environment [VERIFIED: pyproject.toml] |
| sentence-transformers | — | Embedding generation | Verified: 326/326 embeddings generated successfully [VERIFIED: evidence chain] |
| python-dotenv | >=1.0.0 | Environment configuration | RuntimeSettings.from_env() standard, .env file exists [VERIFIED: .env.example] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| llama-index-core | — | LlamaIndex integration | Core RAG framework, used in retrieval pipeline |
| docling | — | Document processing | PDF/Markdown parsing, PageIndex adapter integration |
| llama-index-node-parser-docling | — | Node parsing | Docling integration for chunking |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest + manual verification scripts | pytest + pytest-benchmark + automated quality reports | pytest-benchmark adds performance regression tracking, but current focus is functional quality not performance |

**Installation:**

```bash
pip install pytest>=8.3.0 psycopg[binary]>=3.2.0 sentence-transformers python-dotenv>=1.0.0
```

**Version verification:** Verified from llamaindex_runtime/pyproject.toml [VERIFIED: 2026-05-28]

## Architecture Patterns

### System Architecture Diagram

```
Query Quality Validation Flow:
[Real Queries] → [ReasoningTreeBackend] → [LLM Navigation] → [Filtered Hits]
       ↓                ↓                       ↓                ↓
[Quality Metrics] ← [Registry Query] ← [Tree Structure] ← [PageIndexTreeAdapter]
       ↓
[Grading Assessment] → [Level Progression Judgment]
       ↓
[Main-Function Readiness Decision]

Evidence Chain Completeness Flow:
[Documents] → [PageIndexTreeAdapter] → [Tree Nodes + Spans]
      ↓              ↓                        ↓
[Canonical Spans] → [Vector Chunk Spans] → [Vector Chunks + Embeddings]
      ↓                                       ↓
[Heading Path Extraction]           [Node-Chunk Mapping]
      ↓                                       ↓
[Completeness Check: >95% heading_path, >80% node-chunk]
      ↓
[Evidence Chain Verification]
```

**Key flows:**
1. Query → Backend → Registry → Quality Metrics → Grading
2. Document → Tree Adapter → Registry → Evidence Chain → Completeness Check

### Recommended Project Structure

```
llamaindex_runtime/
├── tree/
│   ├── pageindex_adapter.py      # Tree structure generation (QUAL-02)
│   ├── reasoning_backend.py      # LLM navigation (QUAL-01)
│   └── backend_adapter.py        # Backend protocol
├── client/
│   └── pageindex_client.py       # Client integration, workspace management
├── registry/
│   ├── migrations/               # Schema for evidence chain
│   └── registry_writer.py        # Registry seam
└── config/
    └ RuntimeSettings.py         # Unified configuration

verification/
├── pageindex_main_status_board.html    # Current state visualization
├── pageindex-whitebox-20260527/        # White-box evidence
│   ├── 00-VERIFICATION-ARTICLE.md      # Full verification report
│   ├── 01-VERIFICATION-SUMMARY.json    # Structured metrics
│   └── 03-EVIDENCE.md                  # Evidence chain details
└── (NEW) quality-validation-20260528/  # Phase 2 validation artifacts
    ├── query_quality_report.json       # Query test results
    ├── tree_structure_diagnosis.md     # Tree generation analysis
    └ level_assessment.json             # Level grading judgment

tests/
├── llamaindex_runtime/
│   ├── test_phase8_promotion.py        # Integration tests
│   ├── test_real_retrieval_workflow.py # Workflow verification
│   └── (NEW) test_query_quality_validation.py  # QUAL-01 tests
│   └ (NEW) test_tree_structure_quality.py      # QUAL-02 tests
│   └ (NEW) test_evidence_chain_completeness.py # QUAL-03 tests
```

### Pattern 1: Quality Validation Pattern

**What:** Systematic query quality assessment with measurable thresholds.

**When to use:** When transitioning from "can query" (L2) to "quality verified" (L4).

**Example:**

```python
# Source: verification/quality-validation pattern (recommended)
def validate_query_quality(
    test_queries: list[dict],
    version_id: UUID,
    registry: RegistryWriter,
    thresholds: dict[str, float] = {
        "hit_rate": 0.8,
        "top1_relevance": 0.9,
        "stability": 0.85,
    }
) -> dict:
    """Execute systematic query tests and compute quality metrics.

    Pattern:
    1. Run 10+ diverse queries (different types, complexity)
    2. Measure: hit count, top-hit relevance, query stability
    3. Compare against thresholds
    4. Generate quality report with pass/fail judgment

    Returns:
        {
            "overall_quality": "pass" | "fail",
            "metrics": {
                "hit_rate": 0.85,
                "top1_relevance": 0.88,
                "stability": 0.90,
                "test_count": 15,
            },
            "level_achieved": "Level_3" | "Level_4",
            "blocking_factors": [],
        }
    """
    results = []
    for query_spec in test_queries:
        # Execute query
        hits = retrieve_tree_hits_from_pdf(
            query=query_spec["query"],
            version_id=version_id,
            registry=registry,
        )

        # Compute metrics
        hit_count = len(hits)
        top1_relevant = assess_relevance(hits[0], query_spec["expected_answer"])
        stability = assess_stability(query_spec["query"], version_id, registry)

        results.append({
            "query": query_spec["query"],
            "hit_count": hit_count,
            "top1_relevant": top1_relevant,
            "stability": stability,
        })

    # Aggregate metrics
    metrics = aggregate_metrics(results)

    # Level judgment
    level_achieved = assess_level(metrics, thresholds)

    return {
        "overall_quality": "pass" if level_achieved >= "Level_3" else "fail",
        "metrics": metrics,
        "level_achieved": level_achieved,
        "blocking_factors": identify_blocking_factors(metrics, thresholds),
    }
```

### Pattern 2: Tree Structure Diagnosis Pattern

**What:** Debug tree generation algorithm to identify why hierarchy missing.

**When to use:** When tree nodes show only level=0 (root) nodes, no children.

**Example:**

```python
# Source: Recommended diagnosis pattern
def diagnose_tree_structure(
    source_path: str,
    version_id: UUID,
    registry: RegistryWriter,
) -> dict:
    """Diagnose PageIndexTreeAdapter tree generation issues.

    Pattern:
    1. Trace _flatten_embedded_tree execution
    2. Check heading_path construction (parent chain)
    3. Verify level_no computation from heading depth
    4. Inspect PageIndex donor output structure
    5. Identify: is donor producing hierarchy? is flattening losing children?

    Returns:
        {
            "diagnosis": "donor_issue" | "flattening_issue" | "config_issue",
            "evidence": {
                "donor_output": [...],  # Raw PageIndex structure
                "flat_nodes": [...],    # After flattening
                "heading_paths": [...], # Heading path distribution
                "level_distribution": {0: 2, 1: 0, 2: 0},  # Current: only level 0
            },
            "fix_recommendation": "...",
        }
    """
    from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

    adapter = PageIndexTreeAdapter()

    # Step 1: Capture donor output BEFORE flattening
    if source_path.endswith('.md'):
        embedded_tree = adapter._call_pageindex_md_to_tree(source_path)
    else:
        embedded_tree = adapter._call_pageindex_tree_parser_stub(source_path)

    # Step 2: Inspect donor structure
    donor_hierarchy_depth = compute_max_depth(embedded_tree)

    # Step 3: Apply flattening
    flat_nodes = adapter._flatten_embedded_tree(embedded_tree, version_id=version_id)

    # Step 4: Analyze level distribution
    level_dist = {}
    for node in flat_nodes:
        level = node.get("level_no", 0)
        level_dist[level] = level_dist.get(level, 0) + 1

    # Diagnosis
    if donor_hierarchy_depth == 1:
        diagnosis = "donor_issue"
        recommendation = "Fix PageIndex md_to_tree / tree_parser to generate hierarchy"
    elif len(level_dist) == 1 and 0 in level_dist:
        diagnosis = "flattening_issue"
        recommendation = "Fix _flatten_embedded_tree level_no computation"
    else:
        diagnosis = "unknown"
        recommendation = "Manual inspection required"

    return {
        "diagnosis": diagnosis,
        "evidence": {
            "donor_output": embedded_tree,
            "flat_nodes": flat_nodes,
            "level_distribution": level_dist,
            "donor_hierarchy_depth": donor_hierarchy_depth,
        },
        "fix_recommendation": recommendation,
    }
```

### Anti-Patterns to Avoid

- **"有数据即完成" trap:** Confusing structural existence (tables have data) with functional quality (tree hierarchy works). Current state: tables populated but tree oversimplified.
- **"能查即查好" trap:** Confusing "can query" (L2) with "quality verified" (L4). Evidence: embeddings exist but no quality tests executed.
- **"Evidence链存在即完整" trap:** Confusing structural chain presence with mapping completeness. Evidence: spans→chunks→nodes chain exists but 21.5% node-chunk mapping.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Query quality metrics framework | Manual test execution + spreadsheet analysis | pytest + quality_validation pattern (pattern above) | Systematic, reproducible, threshold-based automation |
| Tree structure debugging | Ad-hoc logging + manual inspection | diagnose_tree_structure pattern (pattern above) | Structured diagnosis with evidence capture |
| Level progression assessment | Subjective "feels good enough" judgment | Explicit Level criteria (L1-L5 from verification doc) | Measurable thresholds prevent premature closure |

**Key insight:** Quality validation requires systematic evidence collection, not anecdotal "it seems to work" assertions.

## Runtime State Inventory

> Phase involves quality validation and tree structure diagnosis - no rename/migration operations. Runtime state check skipped per protocol.

**Verification:** Phase 2 is validation/diagnosis phase, not rename/refactor/migration. No runtime state inventory required.

## Common Pitfalls

### Pitfall 1: Premature Quality Declaration

**What goes wrong:** Declaring "quality verified" without systematic test execution and metrics.

**Why it happens:** White-box verification shows "data exists" →误判为 "功能正常". Evidence: verification document explicitly warns against this trap.

**How to avoid:** Require explicit quality metrics: hit_rate >80%, top1_relevance >90%, stability >85%, test_count >=10.

**Warning signs:** "主功能可用"声明 without query test report; Level judgment without metrics backing.

### Pitfall 2: Tree Generation Silent Failure

**What goes wrong:** PageIndexTreeAdapter falls back to stub without error when LLM unavailable, producing oversimplified tree.

**Why it happens:** ImportError handling in _call_pageindex_md_to_tree (line 332) and _call_pageindex_tree_parser_stub (line 231) returns stub instead of raising.

**How to avoid:** Check OPENAI_API_KEY availability before indexing; raise controlled RuntimeError if credentials available but execution fails (Phase 8 pattern already implemented in adapter).

**Warning signs:** Tree nodes table shows only level=0 nodes; heading_path all "(root)" or identical; node count much lower than expected.

### Pitfall 3: Evidence Chain Illusion

**What goes wrong:** Assuming evidence chain "complete" because spans/chunks exist structurally.

**Why it happens:** Tables have data (326 spans, 326 chunks, 198 node_spans) →误判为"映射完整". Evidence: 70/326 node-chunk mapping (21.5%) shows most chunks unreachable via tree.

**How to avoid:** Compute explicit completeness metrics: node-chunk mapping rate, heading_path non-None rate, span coverage per node.

**Warning signs:** Vector chunks count >> tree nodes count; node_spans count << vector_chunk_spans count; heading_path column has many None values.

## Code Examples

Verified patterns from codebase:

### Query Quality Validation (Recommended Implementation)

```python
# Source: Recommended based on verification evidence
# File: tests/llamaindex_runtime/test_query_quality_validation.py (NEW)

import pytest
from uuid import UUID

@pytest.mark.integration
class TestQueryQualityValidation:
    """Systematic query quality tests for QUAL-01."""

    def test_query_quality_metrics_collection(
        self,
        version_id: UUID,
        registry: RegistryWriter,
    ) -> None:
        """Test that query execution produces quality metrics.

        Pattern:
        1. Execute 10+ queries
        2. Collect: hit_count, top1_relevance, stability
        3. Verify metrics meet thresholds
        """
        test_queries = [
            {"query": "市场概况", "expected_answer": "...", "type": "factual"},
            {"query": "技术架构", "expected_answer": "...", "type": "structural"},
            # ... 8 more queries
        ]

        from llamaindex_runtime.tree.quality_validation import validate_query_quality

        report = validate_query_quality(
            test_queries=test_queries,
            version_id=version_id,
            registry=registry,
            thresholds={
                "hit_rate": 0.8,
                "top1_relevance": 0.9,
                "stability": 0.85,
            }
        )

        # Verify quality judgment
        assert report["overall_quality"] in ["pass", "fail"]
        assert report["metrics"]["test_count"] >= 10

        # If pass, must meet thresholds
        if report["overall_quality"] == "pass":
            assert report["metrics"]["hit_rate"] >= 0.8
            assert report["metrics"]["top1_relevance"] >= 0.9
            assert report["metrics"]["stability"] >= 0.85
```

### Tree Structure Diagnosis

```python
# Source: llamaindex_runtime/tree/pageindex_adapter.py (existing diagnosis needed)
# Pattern: Trace donor output → flattening → level distribution

def diagnose_tree_hierarchy_issue(source_path: str) -> dict:
    """Diagnose why tree only has level=0 nodes.

    Evidence from verification: tree_nodes has 2 nodes, both level=0.
    Expected: 3+ levels for hierarchical document structure.
    """
    from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter
    import uuid

    adapter = PageIndexTreeAdapter()
    version_id = uuid.uuid4()

    # Capture donor output BEFORE flattening
    if source_path.endswith('.md'):
        donor_tree = adapter._call_pageindex_md_to_tree(source_path)
    else:
        donor_tree = adapter._call_pageindex_tree_parser_stub(source_path)

    # Inspect donor hierarchy
    def count_depth(tree: list, level: int = 0) -> int:
        max_depth = level
        for node in tree:
            if node.get("nodes"):
                max_depth = max(max_depth, count_depth(node["nodes"], level + 1))
        return max_depth

    donor_max_level = count_depth(donor_tree)

    # Apply flattening
    flat_nodes = adapter._flatten_embedded_tree(donor_tree, version_id=version_id)

    # Analyze level distribution
    level_counts = {}
    for node in flat_nodes:
        lvl = node.get("level_no", 0)
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    return {
        "donor_max_level": donor_max_level,
        "flat_level_distribution": level_counts,
        "diagnosis": (
            "donor_issue" if donor_max_level == 0
            else "flattening_issue" if len(level_counts) == 1
            else "unknown"
        ),
    }
```

### Evidence Chain Completeness Check

```python
# Source: verification evidence pattern
# Pattern: Compute node-chunk mapping rate, heading_path completeness

def check_evidence_chain_completeness(
    version_id: UUID,
    registry: RegistryWriter,
) -> dict:
    """Compute evidence chain completeness metrics.

    Evidence from verification:
    - 326 vector_chunks (all embeddings generated)
    - 70 chunks mapped to nodes (21.5%)
    - 64 heading_path None (20%)

    Thresholds:
    - Node-chunk mapping >80%
    - Heading_path non-None >95%
    """
    # Query from registry
    chunks = registry.query_vector_chunks_by_version(version_id)
    nodes = registry.query_tree_nodes_by_version(version_id)
    spans = registry.query_canonical_spans_by_version(version_id)

    # Compute metrics
    chunks_mapped = sum(1 for c in chunks if c.get("node_id") is not None)
    chunks_total = len(chunks)
    mapping_rate = chunks_mapped / chunks_total if chunks_total > 0 else 0.0

    spans_with_heading = sum(1 for s in spans if s.get("heading_path") is not None)
    spans_total = len(spans)
    heading_rate = spans_with_heading / spans_total if spans_total > 0 else 0.0

    return {
        "node_chunk_mapping": {
            "mapped": chunks_mapped,
            "total": chunks_total,
            "rate": mapping_rate,
            "threshold": 0.8,
            "pass": mapping_rate >= 0.8,
        },
        "heading_path_completeness": {
            "non_none": spans_with_heading,
            "total": spans_total,
            "rate": heading_rate,
            "threshold": 0.95,
            "pass": heading_rate >= 0.95,
        },
        "overall_pass": mapping_rate >= 0.8 and heading_rate >= 0.95,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| "能跑即完成" (can run = done) | Level progression L1-L5 grading | 2026-05-27 (verification doc) | Explicit quality levels prevent premature closure |
| Structural existence check | Completeness metrics (mapping rate, heading rate) | 2026-05-27 (white-box evidence) | Quantified thresholds replace qualitative judgment |
| Anecdotal quality assertion | Systematic test execution with metrics | Phase 2 target | Evidence-backed quality declaration |

**Deprecated/outdated:**
- "主功能可用" without Level judgment: replaced by explicit Level grading (L1-L5)
- "Evidence chain完整" assertion without metrics: replaced by quantified completeness rates

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PageIndex donor md_to_tree should produce hierarchical structure | Tree Diagnosis | If donor only produces flat structure, adapter cannot fix; requires donor modification |
| A2 | ReasoningTreeBackend LLM navigation will produce filtered hits with quality metrics | Query Quality | If LLM judgment unreliable, quality validation may fail; need fallback mechanism |
| A3 | Node-chunk mapping issue is in PageIndexTreeAdapter generation, not Registry persistence | Evidence Chain | If Registry FK constraints prevent mapping, requires schema fix not adapter fix |

**Verification needed:** All assumptions need diagnosis evidence (A1: donor output inspection, A2: LLM judgment stability testing, A3: Registry constraint check).

## Open Questions

1. **Why does PageIndex md_to_tree produce only root nodes?**
   - What we know: Tree nodes table shows only level=0 nodes (verification evidence)
   - What's unclear: Is it donor issue (md_to_tree itself) or adapter issue (_flatten_embedded_tree)?
   - Recommendation: Execute diagnose_tree_structure pattern to trace donor output vs flattened output.

2. **What is the explicit Level 4 "查得稳定好" criteria?**
   - What we know: Verification doc defines Level progression conceptually (L1-L5)
   - What's unclear: Explicit numeric thresholds for L4 readiness
   - Recommendation: Define thresholds: hit_rate >80%, stability >85%, tree depth >=3, mapping >80%, heading >95%.

3. **Is 10 query tests sufficient for quality validation?**
   - What we know: Verification recommends 10+ tests (line 145)
   - What's unclear: Optimal test count for statistical significance
   - Recommendation: Start with 10, validate confidence interval, increase if variance high.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL + pgvector | Registry storage | ✓ (Docker) | pg16 | — |
| pytest | Test framework | ✓ | >=8.3.0 | — |
| sentence-transformers | Embedding generation | ✓ | — | — |
| OPENAI_API_KEY | LLM reasoning | ⚠ (exists but unverified) | — | Stub fallback (Phase 8 pattern) |
| PageIndex donor repo | Tree generation | ⚠ (external dependency) | — | Stub fallback |

**Missing dependencies with no fallback:**
- None blocking core validation execution

**Missing dependencies with fallback:**
- OPENAI_API_KEY: If unavailable, adapter uses stub (but quality validation requires real LLM)
- PageIndex donor: If unavailable, adapter uses stub (but tree diagnosis requires real donor output)

**Recommendation:** Configure OPENAI_API_KEY and verify PageIndex donor installation for quality validation execution.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8.3.0 [VERIFIED: pyproject.toml] |
| Config file | pytest.ini (markers: integration) [VERIFIED: pytest.ini] |
| Quick run command | `pytest tests/llamaindex_runtime/test_phase8_promotion.py -x` |
| Full suite command | `pytest tests/ -m integration` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-01 | Query quality validation - execute real tests, measure metrics | integration | `pytest tests/llamaindex_runtime/test_query_quality_validation.py -v` | ❌ Wave 0 (NEW) |
| QUAL-02 | Tree structure diagnosis - trace donor vs flattening, fix hierarchy | integration | `pytest tests/llamaindex_runtime/test_tree_structure_quality.py -v` | ❌ Wave 0 (NEW) |
| QUAL-03 | Evidence chain completeness - achieve >80% mapping, >95% heading | integration | `pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py -v` | ❌ Wave 0 (NEW) |
| QUAL-04 | Level grading assessment - explicit L4 criteria verification | integration | Manual assessment + `pytest tests/llamaindex_runtime/test_level_assessment.py -v` | ❌ Wave 0 (NEW) |

**Existing infrastructure:**
- test_phase8_promotion.py: Integration tests for donor path (VERIFIED)
- test_real_retrieval_workflow.py: Workflow verification (VERIFIED)
- pytest configuration with integration marker (VERIFIED)

### Sampling Rate

- **Per task commit:** `pytest tests/llamaindex_runtime/test_{specific_test}.py -x`
- **Per wave merge:** `pytest tests/ -m integration --tb=short`
- **Phase gate:** Full integration suite green + quality validation report generated

### Wave 0 Gaps

- [ ] `tests/llamaindex_runtime/test_query_quality_validation.py` — covers QUAL-01 (query quality metrics)
- [ ] `tests/llamaindex_runtime/test_tree_structure_quality.py` — covers QUAL-02 (tree hierarchy diagnosis)
- [ ] `tests/llamaindex_runtime/test_evidence_chain_completeness.py` — covers QUAL-03 (mapping/heading completeness)
- [ ] `tests/llamaindex_runtime/test_level_assessment.py` — covers QUAL-04 (Level grading criteria)
- [ ] `verification/quality-validation-20260528/` — validation artifacts directory
- [ ] Framework install: pytest >=8.3.0 already installed (VERIFIED)

**Test infrastructure foundation exists.** Phase 2 requires creating 4 new test files for quality validation requirements.

## Security Domain

> Security enforcement enabled (default). Include security considerations for quality validation phase.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (validation phase, no auth changes) |
| V3 Session Management | no | — (validation phase, no session changes) |
| V4 Access Control | no | — (validation phase, no access control changes) |
| V5 Input Validation | yes | Query validation before LLM calls (prevent prompt injection) |
| V6 Cryptography | no | — (validation phase, no crypto changes) |
| V9 Logging and Monitoring | yes | Quality validation metrics logging (audit trail) |

### Known Threat Patterns for PageIndex Quality Validation

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection in query validation tests | Tampering | Sanitize query input before LLM calls; use controlled test queries only |
| Data leakage in quality reports | Information Disclosure | Anonymize query results in reports; avoid logging sensitive content |
| Test coverage manipulation (selective passing) | Tampering | Require full suite execution; automated threshold enforcement |

**Security consideration:** Quality validation tests use real queries and LLM calls. Ensure query input validation prevents prompt injection, and quality reports anonymize sensitive content.

## Sources

### Primary (HIGH confidence)

- verification/pageindex-whitebox-20260527/00-VERIFICATION-ARTICLE.md - Live white-box verification report (database state, tree structure, evidence chain)
- verification/pageindex-whitebox-20260527/01-VERIFICATION-SUMMARY.json - Structured metrics (Level 2 status, gap inventory)
- verification/pageindex-whitebox-20260527/03-EVIDENCE.md - Evidence chain details (span/chunk/node counts)
- llamaindex_runtime/tree/pageindex_adapter.py - Tree generation adapter (donor integration, flattening logic)
- llamaindex_runtime/tree/reasoning_backend.py - LLM navigation backend (query reasoning workflow)
- llamaindex_runtime/client/pageindex_client.py - Client integration (workspace management, Registry seam)
- tests/llamaindex_runtime/test_phase8_promotion.py - Existing integration test pattern
- tests/test_real_retrieval_workflow.py - Workflow verification pattern
- pyproject.toml - pytest configuration, dependencies
- pytest.ini - Test markers configuration

### Secondary (MEDIUM confidence)

- verification/pageindex_main_status_board.html - Status visualization (Level progression definition)
- .planning/STATE.md - Project state (Phase 1 complete, Phase 2 active)
- .planning/ROADMAP.md - Phase 2 goal definition

### Tertiary (LOW confidence)

- None - All claims verified from live evidence or codebase inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified from pyproject.toml, pytest.ini, live environment
- Architecture: HIGH - Verified from codebase inspection, verification evidence
- Pitfalls: HIGH - Identified from verification document explicit warnings

**Research date:** 2026-05-28
**Valid until:** 30 days (tree structure diagnosis may reveal new architecture insights)