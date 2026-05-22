# Compatibility Local Env Program — Current Phase

## Program Status

- env contract/template freeze: completed
- RuntimeSettings extension: active
- unified seam migration: pending
- real-validation handoff: pending

## Active Phase

### Phase 2 — RuntimeSettings extension (ACTIVE)

Goal:
- extend the central settings seam with LLM configuration fields
- ensure all LLM config stops living in ad-hoc direct env reads
- preserve default behavior when no real key is present

Exit criteria:
- RuntimeSettings class has LLM-specific fields
- config.py reads from local .env when available
- validation tests confirm new configuration inputs work cleanly
- existing runtime behavior unchanged when LLM key absent

## Completed Phases

### Phase 1 — Env contract and template freeze (COMPLETED)

Exit criteria achieved:
- tracked template file exists: .env.example committed
- ignore rules allow template tracked, real .env local-only
- all planned variables listed explicitly (13 variables)
- placeholder values filled where possible
- secret slots obvious local-fill placeholders

## Upcoming Phases

### Phase 3 — Unified seam migration
- move the unified LLM path off direct session-only secret dependency

### Phase 4 — Real-validation handoff
- sync the real-validation child package to the local `.env` workflow
