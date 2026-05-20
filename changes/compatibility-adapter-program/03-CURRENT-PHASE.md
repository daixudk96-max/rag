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

## Active Phase — Phase 4b: PageIndex tree adapter landing

## Mission
Wire donor-facing structural extraction to a single LlamaIndex-based LLM entry so PageIndex can run on real documents without introducing donor-owned model configuration.

## In Scope
1. confirm and document the local LlamaIndex unified LLM entry point to use
2. route donor-facing structural extraction (for example PageIndex TOC / structure detection) through that LLM entry
3. keep all provenance contracts unchanged
4. avoid creating a second project-specific LLM abstraction layer
5. prepare the tree donor integration phases to consume the unified LLM path

## Explicitly Out of Scope
- reopening the `LightRAG` graph branch
- reopening the `RAG-Anything` multimodal branch
- donor-as-backend architecture
- replacing PostgreSQL registry as source-of-truth
- rewriting the whole runtime around donor-native IDs
- introducing donor-owned independent LLM configuration stacks

## Exit Criteria
This phase is complete only when all of the following are true:
- PageIndexTreeAdapter calls unified LLM seam (no donor-owned LLM config)
- structural tree build runs on real PDF documents
- real-document tree parsing produces UUID node_ids
- white-box demo shows provenance preservation
- tests pass and reindex succeeds
- local baseline remains available as fallback

## Expected Next Phases After Phase 4a

### Phase 4b — `PageIndexTreeAdapter` landing
- make the structural tree path runnable through the local `TreeBackendAdapter` seam
- preserve local `tree_nodes` / `tree_node_spans` write-back
- prove white-box traceability back to local `span_id`

### Phase 5 — selected `Psi-RAG` donor integration
- wire the accepted traversal / semantic-representation donor pieces into the active adapter lane
- keep local baseline path alive as fallback

### Phase 6 — selected `HIRO` decision-layer integration
- wire the accepted recursive decision skeleton into the branch decision layer
- keep thresholds distribution-based, not distance-based

### Phase 7 — consolidation / verification / default-path decision
- run end-to-end white-box verification
- compare donor-integrated path against local baseline
- decide whether the integrated path is ready to become the default active path

## Allowed Next Moves
- add or adjust the unified LLM seam usage
- add or adjust tree adapter code
- add or adjust tree semantic distribution code
- add or adjust branch decision policy code
- add tests, demos, and verification scripts for the integrated path
- add white-box reporting for provenance and donor behavior

## Forbidden During This Phase
- changing donor priority
- reopening paused branches
- changing immutable provenance contracts
- introducing donor-owned final storage
- declaring program complete based only on research outcomes
