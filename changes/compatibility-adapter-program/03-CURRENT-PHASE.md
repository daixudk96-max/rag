# Compatibility Adapter Program — Current Phase

## Program Status

- donor research: completed
- adapter contract freeze: completed
- local baseline: completed
- donor integration: active
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
- all 10 tests GREEN
- regression tests GREEN (PageIndex adapter tests)
- commit checkpoint created

Exit criteria met:
- single LlamaIndex-based LLM integration path selected and documented
- donor-facing structural extraction can use unified seam
- no ambiguous LLM ownership/configuration
- tests pass
- preserves provenance contracts
- no second LLM abstraction layer

### Phase 4b — PageIndex tree adapter landing (✅ COMPLETED)

Delivered:
- `PageIndexTreeAdapter` routes donor-facing structural extraction through the unified LLM seam
- `PageIndexTreeAdapter.retrieve_tree_hits()` now resolves exact `node -> span -> chunk` provenance
- `BackendHit` no longer uses placeholder `chunk_id=None`
- local fallback remains available when donor path or LLM credentials are unavailable
- PageIndex adapter and provenance tests GREEN

Exit criteria status:
- PageIndexTreeAdapter calls unified LLM seam: ✅
- structural tree build path is wired for real PDFs: ✅
- UUID node_ids preserved: ✅
- white-box provenance path demonstrated: ✅
- tests pass and reindex succeeds: ✅
- local baseline remains available: ✅

### Phase 5 — selected Psi-RAG donor integration (✅ COMPLETED)

Delivered:
- `RecursiveTreeTraversalRunner` is formally wired into the persisted runtime retrieval path
- runtime retrieval now uses `query embedding -> semantic distribution -> traversal runner -> backend-hit mapping`
- exact `chunk -> span -> node -> doc_id/version_id` provenance is preserved in traversal hits
- Psi-RAG-style `prototype_embedding` is formally transplanted into node semantic representation
- traversal now consumes `prototype_embedding` as the preferred semantic similarity signal
- local fallback scoring path remains available when embeddings are unavailable or traversal yields no hits

Completion rationale:
- no longer just a local traversal-like class; production retrieval consumes the transplanted traversal path
- no longer just centroid statistics; donor-style prototype embedding is part of node semantic representation

### Phase 6 — selected HIRO decision-layer integration (✅ COMPLETED)

Delivered:
- `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children()` added as a formal recursive decision skeleton
- traversal runner now calls `evaluate_children()` when children are present
- child aggregation decides between `drill_down`, `keep_parent`, and `prune`
- `retrieve_tree_hits_from_pdf(..., decision_policy="hiro")` and `_retrieve_tree_hits_from_backend(..., decision_policy="hiro")` now provide an explicit runtime path that consumes HIRO policy
- default runtime path remains `baseline`, but HIRO is no longer doc-only or test-only

Completion rationale:
- this is now a formal recursive decision-layer transplant, not just conceptual inspiration
- Phase 6 is considered complete because runtime can explicitly consume HIRO without changing the default path

### Phase 7 — consolidation / verification / default-path decision (✅ COMPLETED)

Verification completed:
- end-to-end white-box comparison script run: `verification/phase7_comparison.py`
- donor-integrated path vs baseline path comparison executed
- provenance integrity preserved across donor and baseline paths: ✅
- SonarQube scanner executed successfully against local SonarQube: ✅
- SonarLint language-server probe path executed successfully against repository file path: ✅
- GitNexus reindex completed successfully: ✅
- scripts added for repeatable Sonar execution:
  - `scripts/run_sonar_scanner.ps1`
  - `scripts/run_sonarlint_ls_probe.py`

SonarLint probe acceptance semantics:
- probe success means the local SonarLint language-server can initialize, accept configuration, open the target file, and dispatch analysis successfully
- the current probe does not require a non-zero diagnostics count on the demo file to pass
- this keeps the documented claim aligned with the script's actual exit-code contract (`0` = analysis path stable, not `>0 diagnostics`)

## Final Default-Path Decision

Decision: **do not switch the integrated donor path to the default active path yet**.

Why:
- the integrated PageIndex donor path still depends on a working LLM credential (`OPENAI_API_KEY`) for real structural extraction
- in the current local environment, donor structural parsing falls back to the stub path when the LLM credential is absent
- provenance is preserved and integration seams are now in place, but the environment-sensitive donor path is not yet stable enough to replace the local baseline as the default

Current recommendation:
- keep the local baseline/default path active
- treat the donor-integrated path as an opt-in / validation path until LLM credentialed real-document operation is consistently available

## Program Outcome After Phase 7

- donor integration: completed through Phase 7 verification
- default-path promotion: deferred
- graph branch: still paused
- multimodal branch: still paused

## Outstanding Technical Debt

### SonarLint probe robustness (non-blocking)

Current status:
- `scripts/run_sonarlint_ls_probe.py` is accepted as an **analysis-path smoke probe**
- success means: initialize → configuration → file open → analysis dispatch → clean exit
- success does **not** currently require non-zero diagnostics on the target file

Known debt:
- JSON-RPC message handling is still more fragile than desired under high event volume
- probe output can show noisy runtime behavior (for example duplicate configuration-scope events)
- the script is suitable for smoke verification, but is not yet a strict diagnostics-asserting verifier

Follow-up expectation:
- future hardening may upgrade the probe from smoke-path validation to deterministic diagnostics assertion
- this debt does **not** block the current Phase 7 acceptance or the baseline-default decision

## Allowed Next Moves
- stabilize credentialed real-document donor operation
- improve donor-integrated retrieval quality under real LLM execution
- revisit default-path promotion only after repeatable real-document runs

## Forbidden Still Applies
- changing donor priority
- reopening paused branches without updating control package
- changing immutable provenance contracts
- introducing donor-owned final storage
- declaring the donor-integrated path as default without stable real-document evidence
