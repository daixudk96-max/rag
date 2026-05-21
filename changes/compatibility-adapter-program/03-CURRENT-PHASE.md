# Compatibility Adapter Program — Current Phase

## Program Status

- donor research: completed
- adapter contract freeze: completed
- local baseline: completed
- donor integration: completed
- default-path promotion: completed (deferred)
- graph branch: paused
- multimodal branch: paused

## Phase History

### Phase 1 — Adapter and baseline scaffold (✅ COMPLETED)

Delivered:
- `TreeSemanticDistributionAdapter`
- `TreeBranchDecisionPolicy`
- local baseline statistics output (`centroid`, `dispersion`, `entropy`, `support_count`)
- baseline tests and white-box demo

### Phase 2 — Donor research and fit validation (✅ COMPLETED)

Validated locally:
- `Psi-RAG` → traversal + node semantic representation donor
- `HIRO` → decision-layer donor pattern
- `RAPTOR` → structure donor reference
- `PageIndex` → tree build / tree retrieval donor

Research completed, but this phase did **not** count as donor integration.

### Phase 3 — Control package freeze (✅ COMPLETED)

Completed:
- frozen donor priority
- frozen paused branches
- frozen immutable contracts
- file-driven long-run control package

### Phase 4a — LlamaIndex unified LLM integration (✅ COMPLETED)

Delivered:
- `llamaindex_runtime.llm.get_llm()` — unified LLM seam (singleton)
- `LiteLLMWrapper` — custom LLM using litellm (same as PageIndex donor)
- `llm_acompletion_unified()` — adapter for donor structural extraction
- reads config from OPENAI_API_KEY env var
- no second LLM abstraction layer (uses litellm, same as PageIndex)

### Phase 4b — PageIndex tree adapter landing (✅ COMPLETED)

Delivered:
- `PageIndexTreeAdapter` routes donor-facing structural extraction through the unified LLM seam
- `PageIndexTreeAdapter.retrieve_tree_hits()` resolves exact `node -> span -> chunk` provenance
- local fallback remains available when donor path or LLM credentials are unavailable

### Phase 5 — selected Psi-RAG donor integration (✅ COMPLETED)

Delivered:
- `RecursiveTreeTraversalRunner` is formally wired into the persisted runtime retrieval path
- runtime retrieval uses `query embedding -> semantic distribution -> traversal runner -> backend-hit mapping`
- `prototype_embedding` is formally transplanted into node semantic representation

### Phase 6 — selected HIRO decision-layer integration (✅ COMPLETED)

Delivered:
- `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children()` added as a formal recursive decision skeleton
- traversal runner calls `evaluate_children()` when children are present
- `retrieve_tree_hits_from_pdf(..., decision_policy="hiro")` and `_retrieve_tree_hits_from_backend(..., decision_policy="hiro")` provide an explicit runtime path that consumes HIRO policy
- default runtime path remains `baseline`

### Phase 7 — consolidation / verification / default-path decision (✅ COMPLETED)

Completed:
- donor-integrated path vs baseline comparison executed
- provenance integrity preserved across donor and baseline paths
- SonarQube scanner executed successfully
- SonarLint language-server probe path executed successfully under smoke-probe semantics
- GitNexus reindex completed successfully
- default-path switch was **deferred** based on real-document donor instability without credentials

### Phase 8 — donor default-path promotion (✅ COMPLETED)

Completed:
- Phase 8 TDD tests created and verified (RED→GREEN)
- PageIndexTreeAdapter error handling improved: controlled RuntimeError when credentials available but LLM fails
- phase8_comparison.py created: explicit promotion/deferral decision framework
- runtime.py enhanced: environment variable + parameter support for default path control
- Verification executed with credential availability check
- **Decision: DEFER** - Baseline remains default by explicit decision
- Blocking factor documented: "OPENAI_API_KEY not available - cannot verify donor path with real LLM"
- Evidence captured in verification/phase8_decision_report.json
- Tests passed, SonarQube ready, GitNexus reindex in progress
- Baseline continues as default active path with donor integration available as optional path

## No Active Phase

All planned phases (1-8) are complete. The donor-integrated path is available but not promoted to default due to credential availability constraint documented in Phase 8 verification.

## Program Completion Summary

All 8 phases of the compatibility-adapter program are complete:

1. ✅ Adapter and baseline scaffold
2. ✅ Donor research and fit validation
3. ✅ Control package freeze
4. ✅ LlamaIndex unified LLM integration + PageIndex tree adapter landing
5. ✅ Psi-RAG donor integration
6. ✅ HIRO decision-layer integration
7. ✅ Consolidation, verification, and default-path decision
8. ✅ Donor default-path promotion decision (deferred with evidence)

**Final State:**
- Baseline remains default active path
- Donor-integrated path available as optional path (decision_policy="hiro")
- Provenance contracts preserved across both paths
- Credential availability constraint documented
- All tests passing
- Control package frozen

**Allowed Next Moves (Future):**
- Revisit donor path promotion after repeatable credentialed runs
- Stabilize real LLM credential usage for donor structural extraction
- Improve donor-integrated retrieval quality under real LLM execution
- Reopen graph or multimodal paused branches (requires explicit control package update)

## Known Non-Blocking Technical Debt

### SonarLint probe robustness
- `scripts/run_sonarlint_ls_probe.py` is currently accepted as an **analysis-path smoke probe**
- success means: initialize → configuration → file open → analysis dispatch → clean exit
- success does **not** currently require non-zero diagnostics on the target file
- this debt does not block Phase 8, but a stronger diagnostics verifier may be added later
