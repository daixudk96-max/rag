# Compatibility Tech-Debt Program — Roadmap Snapshot

## Mainline Route

### Line A — SonarLint verifier hardening
- goal: move from smoke-probe semantics toward deterministic diagnostics verification on known-bad samples
- scope: keep the language-server path, strengthen what counts as success

### Line B — Phase 8 comparison hardening
- goal: ensure validation output never overstates donor success and cleanly separates credential block vs runtime bug vs stub/fallback
- scope: comparison/reporting surfaces only, not a strategic rewrite

### Line C — Backend-backed verification strengthening
- goal: replace framework-only verification claims with real measured signals where feasible
- scope: provenance checks, baseline quality signals, and validation artifacts

### Line D — Close-out and parent sync
- goal: sync resolved debts back into the parent package while keeping unresolved debts explicit

## Phase Sequence

### Phase 1 — SonarLint probe hardening
- strengthen the SonarLint verifier contract
- prefer diagnostics-aware assertions over clean-exit-only acceptance when feasible

### Phase 2 — Phase 8 comparison hardening
- remove ambiguous success paths
- tighten decision/report assertions and classification

### Phase 3 — Backend-backed verification strengthening
- add stronger measured signals where current framework-level placeholders exist
- keep blast radius minimal and evidence-focused

### Phase 4 — Debt close-out
- update parent package debt notes
- clearly separate resolved debt from still-open debt

## Current Program Sequence

1. inherit frozen constraints from the parent package
2. strengthen verifiers before changing strategic claims
3. prefer the smallest fixes that turn ambiguous pass/fail into deterministic evidence
4. update the parent debt list only after each child phase is actually verified
