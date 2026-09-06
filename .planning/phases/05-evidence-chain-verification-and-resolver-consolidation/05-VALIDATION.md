---
phase: 5
slug: evidence-chain-verification-and-resolver-consolidation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-07
---

# Phase 5 — Validation Strategy

> Validation contract for evidence-chain verification and resolver consolidation.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pytest.ini |
| **Quick run command** | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_query_quality_validation.py -x` |
| **Full suite command** | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_query_quality_validation.py tests/llamaindex_runtime/test_evidence_chain_completeness.py -x` |
| **Estimated runtime** | ~240 seconds |

---

## Sampling Rate

- **After every task commit:** Run the plan-specific focused pytest command.
- **After every plan wave:** Run `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_query_quality_validation.py tests/llamaindex_runtime/test_evidence_chain_completeness.py -x`.
- **Before human judgment collection resumes:** Evidence-chain counts and validation integrity gate must pass.
- **Max feedback latency:** 240 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | REQ-01 | T-05-01 | Version ID is parsed as UUID and registry queries remain parameterized | unit/integration | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py -x` | ✅ | ⬜ pending |
| 05-01-02 | 01 | 1 | REQ-02 | T-05-01 | Validation counts are scoped to active_version_id, not global tables | integration | `PYTHONPATH=E:/github/rag pytest tests/verification/test_validation_integrity.py -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | REQ-03 | — | VectorLoader materialization is idempotent and safe for partial state | integration | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_vector_loader.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | REQ-04 | — | Heading-path metric uses the documented authoritative table | unit | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py -x` | ✅ | ⬜ pending |
| 05-03-01 | 03 | 3 | REQ-05/REQ-06 | — | Resolver preserves source-backed fallback cascade without changing ranking | unit | `PYTHONPATH=E:/github/rag pytest tests/llamaindex_runtime/test_evidence_content_resolver.py -x` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | REQ-07 | T-05-02 | Corpus mismatch blocks metric calculation and judgment collection | integration | `PYTHONPATH=E:/github/rag pytest tests/verification/test_validation_integrity.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/llamaindex_runtime/test_vector_loader.py` — covers VectorLoader idempotent invocation / materialization behavior.
- [ ] `tests/verification/test_validation_integrity.py` — covers corpus mismatch and active-version validation gates.
- [ ] `tests/llamaindex_runtime/test_evidence_content_resolver.py` — covers shared resolver fallback cascade.
- [ ] Existing pytest infrastructure covers execution; no framework install needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Human relevance judgment for 71 new corpus hits | REQ-07 | Requires human semantic relevance assessment | Only start after evidence-chain counts are non-zero/explainable and corpus integrity gate passes; then judge `verification/phase3-real-validation/judgment_template.csv` rows for the aligned corpus. |
| Final Level go/no-go | REQ-07 | Readiness decision must match metrics + human judgment | Compare `level_assessment.json`, `retrieval_results.json`, judgment CSV, and final report before changing authoritative baseline. |

---

## Validation Sign-Off

- [ ] Active-version counts are version-scoped for `canonical_spans`, `canonical_spans.heading_path IS NOT NULL`, `vector_chunks`, `vector_chunks.node_id IS NOT NULL`, `vector_chunk_spans`, and `tree_node_spans`.
- [ ] Validation scripts use the same DB/schema/version as ingestion.
- [ ] Vector chunk materialization path is proven or its blocker is documented.
- [ ] `heading_path` storage contract is documented and metrics use the authoritative table.
- [ ] EvidenceContentResolver preserves `canonical_spans.raw_text` → `vector_chunks.text_preview` → summary/title fallback.
- [ ] Retrieval/node selection ordering is unchanged by resolver extraction.
- [ ] Human judgment collection remains blocked until evidence-chain and corpus integrity gates pass.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 240s.
- [ ] `nyquist_compliant: true` set in frontmatter.

**Approval:** partial; Phase 5 targeted suite passed but DB-backed proof remains blocked
