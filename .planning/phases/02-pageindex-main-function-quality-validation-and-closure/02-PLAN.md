---
phase: 02-pageindex-main-function-quality-validation-and-closure
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/llamaindex_runtime/test_query_quality_validation.py
  - tests/llamaindex_runtime/test_tree_structure_quality.py
  - tests/llamaindex_runtime/test_evidence_chain_completeness.py
  - tests/llamaindex_runtime/test_level_assessment.py
  - verification/quality-validation-20260528/query_quality_report.json
  - verification/quality-validation-20260528/tree_structure_diagnosis.json
  - verification/quality-validation-20260528/evidence_chain_report.json
  - verification/quality-validation-20260528/level_assessment.json
  - verification/pageindex_main_status_board.html
autonomous: true
requirements:
  - QUAL-01
  - QUAL-02
  - QUAL-03
  - QUAL-04
must_haves:
  truths:
    - User can point to an automated report stating whether PageIndex query quality passes or fails against explicit thresholds.
    - User can point to an automated report stating whether the active tree structure is hierarchical enough for main-function readiness.
    - User can point to an automated report stating whether evidence-chain completeness meets node-chunk and heading-path thresholds.
    - User can point to one final readiness decision that says whether PageIndex remains Level 2 or qualifies for closure at Level 4+.
  artifacts:
    - path: tests/llamaindex_runtime/test_query_quality_validation.py
      provides: Automated query-quality validation cases and thresholds
    - path: tests/llamaindex_runtime/test_tree_structure_quality.py
      provides: Automated tree-hierarchy diagnosis and threshold checks
    - path: tests/llamaindex_runtime/test_evidence_chain_completeness.py
      provides: Automated evidence-chain completeness checks
    - path: tests/llamaindex_runtime/test_level_assessment.py
      provides: Automated closeout gate for Level judgment
    - path: verification/quality-validation-20260528/query_quality_report.json
      provides: Machine-readable query-quality results
    - path: verification/quality-validation-20260528/tree_structure_diagnosis.json
      provides: Machine-readable tree diagnosis results
    - path: verification/quality-validation-20260528/evidence_chain_report.json
      provides: Machine-readable evidence completeness results
    - path: verification/quality-validation-20260528/level_assessment.json
      provides: Machine-readable readiness decision
  key_links:
    - from: tests/llamaindex_runtime/test_query_quality_validation.py
      to: llamaindex_runtime/tree/reasoning_backend.py
      via: Real or fixture-backed retrieval execution and metric collection
      pattern: ReasoningTreeBackend|retrieve_tree_hits
    - from: tests/llamaindex_runtime/test_tree_structure_quality.py
      to: llamaindex_runtime/tree/pageindex_adapter.py
      via: Donor-output versus flattened-tree diagnosis
      pattern: _call_pageindex_md_to_tree|_flatten_embedded_tree
    - from: tests/llamaindex_runtime/test_evidence_chain_completeness.py
      to: registry-backed provenance tables
      via: version-scoped completeness metrics
      pattern: query_.*by_version
    - from: tests/llamaindex_runtime/test_level_assessment.py
      to: verification/quality-validation-20260528/*.json
      via: Aggregation of prior validation outputs into final readiness judgment
      pattern: Level_2|Level_3|Level_4
---

<objective>
Establish an executable quality-validation gate for PageIndex main-function readiness so the project can prove, with automated evidence, whether it is still only technically connected or truly ready to close as a quality-verified main path.

Purpose: Convert the current “Level 2: 能查但质量未验证” state into an explicit pass/fail decision backed by query-quality metrics, tree-structure diagnosis, evidence-chain completeness metrics, and a final closure rubric.
Output: Four automated validation test files, four machine-readable validation artifacts, and an updated status board reflecting the readiness decision.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@E:/github/rag/.planning/ROADMAP.md
@E:/github/rag/.planning/STATE.md
@E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-RESEARCH.md
@E:/github/rag/verification/pageindex_main_status_board.html
@E:/github/rag/verification/pageindex-whitebox-20260527/00-VERIFICATION-ARTICLE.md
@E:/github/rag/verification/pageindex-whitebox-20260527/01-VERIFICATION-SUMMARY.json
@E:/github/rag/verification/pageindex-whitebox-20260527/03-EVIDENCE.md
@E:/github/rag/llamaindex_runtime/client/pageindex_client.py
@E:/github/rag/llamaindex_runtime/tree/pageindex_adapter.py
@E:/github/rag/llamaindex_runtime/tree/reasoning_backend.py
@E:/github/rag/tests/llamaindex_runtime/test_phase8_promotion.py

<interfaces>
From llamaindex_runtime/client/pageindex_client.py:
```python
def index(
    self,
    file_path: str,
    mode: str = "auto",
    version_id: Optional[str] = None,
    write_to_registry: bool = True,
) -> str
```

From llamaindex_runtime/tree/pageindex_adapter.py:
```python
class PageIndexTreeAdapter:
    def index_tree(self, *, source_path: str, version_id: UUID, registry: Any) -> None
    def retrieve_tree_hits(self, *, query_text: str, version_id: UUID, registry: Any, limit: int | None = None) -> list[BackendHit]
    def _flatten_embedded_tree(
        self,
        embedded_tree: list[dict[str, Any]],
        version_id: UUID,
        parent_node_id: UUID | None = None,
        heading_prefix: str = "",
    ) -> list[dict[str, Any]]
```

From llamaindex_runtime/tree/reasoning_backend.py:
```python
class ReasoningTreeBackend(TreeBackendAdapter):
    def retrieve_tree_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int | None = None,
    ) -> list[BackendHit]
```

Current validated thresholds from source evidence and research:
```text
- Minimum test queries: 10
- Minimum query hit rate: 0.80
- Minimum top-1 relevance: 0.90
- Minimum stability: 0.85
- Minimum tree depth: 3 levels
- Minimum node-chunk mapping rate: 0.80
- Minimum heading_path completeness: 0.95
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create quality-validation test contracts and fixtures</name>
  <files>tests/llamaindex_runtime/test_query_quality_validation.py, tests/llamaindex_runtime/test_tree_structure_quality.py, tests/llamaindex_runtime/test_evidence_chain_completeness.py, tests/llamaindex_runtime/test_level_assessment.py</files>
  <behavior>
    - Test 1: Query-quality suite fails when fewer than 10 real queries are evaluated or hit-rate/relevance/stability thresholds are below the required values.
    - Test 2: Tree-quality suite fails when donor output or flattened output does not demonstrate at least 3 levels of hierarchy and clear level distribution.
    - Test 3: Evidence-chain suite fails when node-chunk mapping is below 0.80 or heading_path completeness is below 0.95.
    - Test 4: Level-assessment suite fails when any blocking metric remains below threshold but the final decision artifact claims Level 4 readiness.
  </behavior>
  <action>Create the four validation test files as the execution contract for QUAL-01 through QUAL-04. Reuse pytest integration patterns from existing `tests/llamaindex_runtime/test_phase8_promotion.py`. Encode the exact thresholds from Phase 2 research, and use immutable fixtures/data structures for query specs and expected outcomes. The query-quality file must define 10-15 representative query cases across factual, structural, heading-targeted, and evidence-sensitive retrieval. The tree-quality file must trace both donor-output depth and `_flatten_embedded_tree()` level distribution so execution can distinguish donor failure from flattening failure instead of collapsing both into a generic failure. The evidence-chain file must compute version-scoped completeness metrics using registry seam queries rather than hardcoded counts. The level-assessment file must aggregate prior result artifacts and enforce that Level 4 readiness is impossible unless all thresholds pass; do not allow subjective “looks good” shortcuts.</action>
  <verify>
    <automated>pytest E:/github/rag/tests/llamaindex_runtime/test_query_quality_validation.py E:/github/rag/tests/llamaindex_runtime/test_tree_structure_quality.py E:/github/rag/tests/llamaindex_runtime/test_evidence_chain_completeness.py E:/github/rag/tests/llamaindex_runtime/test_level_assessment.py -q</automated>
  </verify>
  <done>The repository has four focused validation test files, each with explicit pass/fail thresholds and no ambiguity about what must be proven for closeout.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Produce machine-readable validation artifacts for query, tree, and evidence quality</name>
  <files>verification/quality-validation-20260528/query_quality_report.json, verification/quality-validation-20260528/tree_structure_diagnosis.json, verification/quality-validation-20260528/evidence_chain_report.json</files>
  <behavior>
    - Test 1: Query-quality report records per-query results, aggregate metrics, pass/fail thresholds, and identified blocking factors.
    - Test 2: Tree-diagnosis report records donor hierarchy depth, flattened level distribution, and a diagnosis category of donor_issue, flattening_issue, config_issue, or pass.
    - Test 3: Evidence-chain report records node-chunk mapping totals/rates, heading_path totals/rates, and a clear overall pass/fail value.
  </behavior>
  <action>Implement the executable validation path that writes the three JSON artifacts from real validation runs, using the task-1 contracts as the guardrail. Query-quality output must include each test query, hit count, top-hit judgment, stability result, aggregate hit-rate/top-1/stability metrics, and a final verdict. Tree diagnosis must capture both raw donor-tree evidence and post-flattening evidence so the resulting artifact directly explains why the current system remains Level 2 if hierarchy is still missing. Evidence completeness must query registry-backed version data and emit both raw counts and threshold comparisons for node-chunk mapping and heading_path completeness. Keep the artifacts strictly machine-readable JSON so later gates can consume them without manual interpretation.</action>
  <verify>
    <automated>pytest E:/github/rag/tests/llamaindex_runtime/test_query_quality_validation.py E:/github/rag/tests/llamaindex_runtime/test_tree_structure_quality.py E:/github/rag/tests/llamaindex_runtime/test_evidence_chain_completeness.py -q</automated>
  </verify>
  <done>Three JSON artifacts exist, each generated by executable validation logic and each sufficient to answer one Phase 2 focus area without reading prose evidence manually.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Enforce the final readiness gate and publish the closeout decision</name>
  <files>verification/quality-validation-20260528/level_assessment.json, verification/pageindex_main_status_board.html</files>
  <behavior>
    - Test 1: Final level assessment reports Level 2, 3, or 4+ based only on measured artifact outputs and rejects contradictory states.
    - Test 2: Status board reflects the current readiness level, blocking factors, and closure recommendation consistently with the JSON assessment.
  </behavior>
  <action>Implement the final closeout gate that consumes the three prior JSON artifacts and produces `level_assessment.json` with the explicit readiness decision for QUAL-04. The gate must encode the source-backed progression: Level 2 means technically connected but quality unverified; Level 3 means query quality basically correct but not yet stable enough for closeout; Level 4 means tree depth, node-chunk mapping, heading completeness, and query-quality thresholds all pass. Update `verification/pageindex_main_status_board.html` so it displays the same verdict, the exact blocking metrics when failing, and the exact closure criteria when passing. Do not leave any “partial” wording that can be interpreted as approval; the board must say either not ready and why, or ready and why.</action>
  <verify>
    <automated>pytest E:/github/rag/tests/llamaindex_runtime/test_level_assessment.py -q</automated>
  </verify>
  <done>A single machine-readable readiness decision exists and the human-facing status board matches it exactly, making Phase 2 closure a measurable gate instead of an interpretive judgment.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| validation queries → ReasoningTreeBackend | Test query text crosses into LLM-guided retrieval and must not be treated as trusted instructions |
| verification code → registry data | Validation code reads persisted provenance data that may be incomplete, stale, or internally inconsistent |
| JSON artifacts → closeout decision | Machine-generated reports feed the final readiness gate; bad inputs here can create false closure |
| status board → human decision | Human closeout judgment depends on the published board, so mismatches or ambiguous wording can mislead release decisions |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | T | query-quality validation | mitigate | Use controlled test-query fixtures only, validate query inputs before LLM calls, and forbid free-form artifact mutation during metric collection |
| T-02-02 | I | evidence-chain reports | mitigate | Emit aggregate metrics and IDs needed for traceability, but do not dump full sensitive document bodies into JSON artifacts |
| T-02-03 | R | final readiness gate | mitigate | Make `test_level_assessment.py` assert that every decision is derivable from prior JSON artifacts and thresholds, preventing unverifiable manual overrides |
| T-02-04 | D | tree diagnosis execution | accept | Donor-path diagnosis may fail when external credentials or donor install are unavailable; surface this as a blocking factor rather than silently downgrading to pass |
| T-02-05 | T | status board publication | mitigate | Render board values directly from generated assessment data and test for consistency so the published verdict cannot drift from the machine-readable decision |
</threat_model>

<verification>
- `pytest E:/github/rag/tests/llamaindex_runtime/test_query_quality_validation.py -q`
- `pytest E:/github/rag/tests/llamaindex_runtime/test_tree_structure_quality.py -q`
- `pytest E:/github/rag/tests/llamaindex_runtime/test_evidence_chain_completeness.py -q`
- `pytest E:/github/rag/tests/llamaindex_runtime/test_level_assessment.py -q`
- `pytest E:/github/rag/tests/llamaindex_runtime/test_query_quality_validation.py E:/github/rag/tests/llamaindex_runtime/test_tree_structure_quality.py E:/github/rag/tests/llamaindex_runtime/test_evidence_chain_completeness.py E:/github/rag/tests/llamaindex_runtime/test_level_assessment.py -q`
</verification>

<success_criteria>
- At least 10 representative queries are executed and summarized with hit-rate, top-1 relevance, and stability metrics.
- Tree-quality output explicitly distinguishes donor-tree depth from flattening output and can prove whether 3+ levels exist.
- Evidence-chain output explicitly reports node-chunk mapping rate and heading_path completeness against 0.80 and 0.95 thresholds.
- Final level assessment declares one of: Level 2 not ready, Level 3 partially ready, or Level 4 ready for closeout.
- The HTML status board and `level_assessment.json` present the same readiness verdict and blocking factors.
</success_criteria>

<output>
After completion, create `E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md`

Before any commit or closeout handoff that modifies tracked code or verification artifacts, run the project-required GitNexus change-scope check so the resulting summary and ship decision can confirm that the changes only affect the expected validation/test surface.
</output>
