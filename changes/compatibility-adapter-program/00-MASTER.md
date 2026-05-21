# Compatibility Adapter Program — MASTER CONTROL

## Mission

Advance the compatibility-adapter program from donor research into real adapter integration without losing local provenance guarantees.

## Frozen Strategic Decision

The current mainline is:

1. keep local provenance contracts untouched
2. strengthen tree build / retrieval separately from tree-internal vector distribution
3. pause graph-two-in-one ambitions for now
4. pause multimodal enhancement for now

## Mandatory Read Order

1. `00-MASTER.md`
2. `01-ROADMAP.md`
3. `02-INTERFACES.md`
4. `03-CURRENT-PHASE.md`

## Immutable Contracts

Do not change the meaning of:
- `doc_id`
- `version_id`
- `span_id`
- `chunk_id`
- `node_id`
- `entity_id`
- `relation_id`
- `evidence_id`
- `QueryHit`

## Active vs Paused Lines

### Active
- Donor default-path promotion
- Credentialed real-document donor stabilization
- Baseline vs donor integrated path comparison

### Paused
- LightRAG graph branch as active implementation path
- RAG-Anything multimodal branch
- donor-as-backend architecture

## Donor Priority (Frozen)

- Tree build / retrieval: `PageIndex`
- Tree-internal vector distribution: `Psi-RAG` first, `HIRO` second, `RAPTOR` third
- Graph / graph-text: `LightRAG` only as a paused future branch
- Multimodal: `RAG-Anything` only as a paused future branch

## Execution Rules

- Only work on the current phase described in `03-CURRENT-PHASE.md`.
- If a task requires changing donor priority, stop and update the control package first.
- If a task pressures provenance contracts, stop and escalate.
- Prefer donor logic transplantation / adapter wrapping over full rewrites.
- Prefer local registry write-back over donor-native storage ownership.

## Program State

- donor research: completed
- local baseline: completed
- donor integration: completed
- default-path promotion: completed (deferred)
- graph branch: paused
- multimodal branch: paused

**All 8 phases complete.** Baseline remains default; donor-integrated path available as optional.

## Phase Gate Policy

A phase is complete only when:
- tests pass
- the phase exit criteria in `03-CURRENT-PHASE.md` are met
- the result does not require reopening a paused branch
- the result advances real adapter integration, not only additional research

## Known Non-Blocking Technical Debt

- `scripts/run_sonarlint_ls_probe.py` is currently accepted as an **analysis-path smoke probe**, not a strict diagnostics-asserting verifier.
- This debt is recorded in `03-CURRENT-PHASE.md` and does not block the current Phase 7 acceptance.
- It should be treated as follow-up hardening work, not as a reason to reopen donor-integration phases.

## Not Allowed

- merging tree retrieval, tree-internal vector distribution, and graph retrieval into one donor path
- letting donor projects own final IDs or source-of-truth storage
- reinterpreting paused branches as active without updating this file
