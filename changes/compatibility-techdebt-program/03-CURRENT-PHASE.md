# Compatibility Tech-Debt Program — Current Phase

## Program Status

- debt inventory: opened
- SonarLint probe hardening: pending
- Phase 8 comparison hardening: pending
- backend-backed verification strengthening: pending
- close-out: pending

## Active Phase

### Phase 1 — SonarLint probe hardening (ACTIVE)

Goal:
- strengthen the SonarLint verifier so success means more than clean process exit when the protocol supports it
- if strict diagnostics assertion is still not feasible, downgrade nothing silently: document the exact blocker and provide the strongest deterministic probe the server currently allows

Exit criteria:
- a known-bad sample path is used intentionally
- success/failure semantics are explicit
- targeted tests pass
- the result is labeled either `diagnostics-aware` or `smoke-only` with evidence

## Upcoming Phases

### Phase 2 — Phase 8 comparison hardening
- continue hardening `verification/phase8_comparison.py`
- remove remaining framework-only ambiguity where feasible

### Phase 3 — Backend-backed verification strengthening
- replace placeholder verification claims with stronger measured signals where feasible

### Phase 4 — Debt close-out
- sync resolved debt status back to the parent package
