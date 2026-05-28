---
phase: 02
extracted_date: 2026-05-28
---

# Phase 2 Learnings — PageIndex Quality Validation Framework

## Key Decisions

### Decision 1: Explicit Thresholds Replace Subjective Judgment

**Context:** Previous quality assertions ("主功能可用", "查得不错") were qualitative and unmeasurable.

**Decision:** Freeze explicit thresholds with numeric values:
- hit_rate ≥80%
- top1_relevance ≥90%
- stability ≥85%
- tree_depth ≥3 levels
- node_chunk_mapping ≥80%
- heading_path_completeness ≥95%

**Outcome:** Quality validation now has measurable gates. No "partial" or "mostly" shortcuts allowed.

**Lesson:** Always encode quality criteria as numeric thresholds before starting implementation. Qualitative assertions lead to premature closure.

### Decision 2: Level Progression Criteria Defined Upstream

**Context:** Phase 2 started with unclear Level progression (Level 2 → Level 4 gap undefined).

**Decision:** Define explicit Level criteria:
- Level 2: 能查但质量未验证
- Level 3: 查得基本对 (hit_rate passing)
- Level 4: 查得稳定好 (all thresholds passing)

**Outcome:** Fixture validation correctly determined Level 3. Real validation will use same criteria.

**Lesson:** Define success criteria before implementation, not after. Level gates should be frozen at planning phase.

### Decision 3: Diagnosis Capability Over Simple Pass/Fail

**Context:** Tree structure quality could have been simple "pass/fail" check.

**Decision:** Implement diagnosis that distinguishes donor_issue vs flattening_issue vs config_issue.

**Outcome:** Can identify WHERE the problem originates (PageIndex donor, flattening algorithm, or runtime config).

**Lesson:** Build diagnosis capability, not just verdict. Knowing WHY helps fix problems faster.

### Decision 4: Fixture Data Validates Infrastructure, Not Quality

**Context:** Initial concern that fixture data might be misleading for quality assessment.

**Decision:** Treat fixture-based validation as infrastructure correctness test, separate from real quality assessment.

**Outcome:** 31 tests passing proves validation framework works correctly. Real quality needs live data + LLM.

**Lesson:** Separate infrastructure validation from quality validation. Fixture proves framework; real data proves quality.

## Technical Patterns Established

### Pattern 1: Threshold-as-Constants

```python
# Good: Thresholds frozen in constants
MIN_HIT_RATE = 0.80
MIN_TOP1_RELEVANCE = 0.90
MIN_STABILITY = 0.85

# Bad: Thresholds scattered in assertions
assert hit_rate > 0.8  # Magic number, no provenance
```

**Lesson:** Define thresholds in one place, import everywhere. Enables threshold tuning without code search.

### Pattern 2: Level Assessment Derives from Artifacts

```python
# Good: Level derived from prior validation outputs
level = assess_level(query_report, tree_report, evidence_report)

# Bad: Level assigned subjectively
level = "Level_4"  # because "it looks good"
```

**Lesson:** Level determination must be artifact-driven, not opinion-driven. Blocking factors list explains WHY Level is low.

### Pattern 3: Machine-Readable JSON Artifacts

```json
{
  "overall_quality": "fail",
  "metrics": {"hit_rate": 0.5, "top1_relevance": 0.3},
  "blocking_factors": ["hit_rate below 80%"],
  "thresholds": {"hit_rate": 0.80, "top1_relevance": 0.90}
}
```

**Lesson:** JSON artifacts enable automation (dashboards, CI gates, regression tracking). Prose-only evidence is manual overhead.

## Process Insights

### Insight 1: TDD Pattern Applied to Validation Framework

- RED: Write tests expecting threshold enforcement
- GREEN: Implement threshold checks
- Result: 31 tests passing proves framework logic

**Lesson:** Validation infrastructure itself should be TDD-verified. Tests test the testing framework.

### Insight 2: Nyquist Compliance Built In

- Per-task verification: Each task has automated pytest command
- Sampling rate: Tests run after commit
- Feedback latency: <180 seconds

**Lesson:** Nyquist validation pattern applies to meta-validation (testing the validation framework).

### Insight 3: Separation of Concerns

Phase 2 did NOT:
- Fix tree structure (that's implementation work)
- Improve node-chunk mapping (that's data work)
- Run real LLM queries (that's quality work)

Phase 2 DID:
- Build measurement capability
- Define assessment criteria
- Provide diagnosis tools

**Lesson:** Validation phase should measure, not fix. Fixing belongs to execution phases.

## Anti-Patterns Avoided

### Anti-Pattern 1: Premature Quality Declaration

Previous trap: "主功能可用" asserted before systematic testing.

Phase 2 prevention: Require ALL thresholds to pass for Level 4. Single failure → Level 3 or lower.

**Lesson:** "Partial" quality is not quality. Either all gates pass or quality is unverified.

### Anti-Pattern 2: Threshold Drift

Risk: Thresholds might be lowered during implementation to "make tests pass".

Prevention: THRESHOLDS defined as constants, used consistently across test files, frozen at planning phase.

**Lesson:** Freeze thresholds upstream, not downstream. Implementation should meet thresholds, thresholds shouldn't meet implementation.

### Anti-Pattern 3: Diagnosis Shortcut

Risk: "Tree structure bad" verdict without explaining WHY.

Prevention: Diagnosis returns donor_issue / flattening_issue / config_issue with evidence.

**Lesson:** Diagnosis > verdict. Knowing WHERE problem originates enables targeted fixes.

## Recommendations for Next Phase

### Recommendation 1: Separate Real Quality Validation Phase

Phase 2 built framework. Phase 3 should execute real validation using:
- Live PostgreSQL registry data (not fixture)
- ReasoningTreeBackend with LLM calls
- 15-20 real business queries
- Manual relevance judgment for top-k hits

**Action:** Define Phase 3 as "PageIndex Real Quality Validation Execution" (distinct from framework building).

### Recommendation 2: Tree Structure Fix Before Real Validation

Current white-box shows only root-level nodes (Level 0). Real validation needs 3+ levels.

**Action:** Tree structure fix is prerequisite for meaningful quality assessment. Don't run quality tests on broken tree structure.

### Recommendation 3: Evidence Chain Completion

Current node-chunk mapping at 21.5%. Real validation requires >80% for Level 4.

**Action:** Fix span→chunk→node mapping before running quality validation. Low mapping rate makes retrieval coverage incomplete.

## Metrics Summary

| Metric | Value | Context |
|--------|-------|---------|
| Test files created | 4 | QUAL-01 through QUAL-04 covered |
| Tests passing | 31 | Infrastructure correctness verified |
| JSON artifacts | 4 | Machine-readable validation reports |
| Thresholds frozen | 7 | hit_rate, relevance, stability, depth, mapping, heading, count |
| Level gates | 3 | Level 2/3/4 progression defined |
| Commit created | d080850 | Phase 2 deliverables committed |
| Real quality blockers | 2 | Tree structure + node-chunk mapping |

## Conclusion

Phase 2 succeeded in establishing quality validation framework with:
1. Measurable thresholds (no qualitative shortcuts)
2. Level progression gates (Level 2 → 3 → 4)
3. Diagnosis capability (where problems originate)
4. Machine-readable artifacts (automation-friendly)
5. Nyquist-compliant validation (tests test the framework)

The framework is ready for real quality validation. Fixture-based testing confirms infrastructure works correctly. Next phase should use live data and LLM-based retrieval for real quality assessment.