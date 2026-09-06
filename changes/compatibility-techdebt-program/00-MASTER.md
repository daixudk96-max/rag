# Compatibility Tech-Debt Program — MASTER CONTROL

## Mission

Resolve the remaining non-blocking technical debt left by `compatibility-adapter-program` without reopening paused branches or re-litigating completed donor-integration decisions.

## Parent Inheritance

This child program inherits frozen donor strategy, paused branches, and immutable provenance constraints from:
- `../compatibility-adapter-program/00-MASTER.md`
- `../compatibility-adapter-program/03-CURRENT-PHASE.md`

## Frozen Strategic Decision

1. harden accepted verifier/probe paths before reopening strategy questions
2. treat debt work as follow-up hardening, not as permission to restart donor research
3. allow only minimal bug fixes and verifier strengthening
4. do not reopen graph or multimodal branches

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
- SonarLint diagnostics-verifier hardening
- Phase 8 comparison/verifier hardening
- backend-backed verification signal strengthening

### Paused
- donor priority changes
- graph / multimodal reactivation
- donor-as-backend architecture
- broad feature work unrelated to technical debt

## Execution Rules

- Only work on the current phase described in `03-CURRENT-PHASE.md`.
- Run GitNexus impact analysis before editing any function, class, or method.
- Use TDD for every fix slice.
- After each slice: run targeted tests and `gitnexus analyze --embeddings --skills --verbose`.
- If a debt item requires contract change, donor-priority change, or paused-branch reentry, stop and escalate.

## Program State

- debt inventory: opened
- active hardening work: pending
- strategic re-evaluation: paused until debt work produces new evidence
