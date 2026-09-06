# Compatibility Local Env Program — MASTER CONTROL

## Mission

Shift real validation and unified LLM access from session-scoped secret injection to a local `.env`-based configuration path, without changing frozen provenance contracts or reopening paused branches.

## Parent Inheritance

This child program inherits frozen donor strategy, paused branches, and immutable provenance constraints from:
- `../compatibility-adapter-program/00-MASTER.md`
- `../compatibility-real-validation-program/00-MASTER.md`

## Frozen Strategic Decision

1. local secrets should live in an untracked `.env` file, not in temporary shell session state
2. the repo may track only a safe template file such as `.env.example`
3. configuration should be centralized, not scattered across ad-hoc `os.getenv()` calls
4. this package exists to improve configuration hygiene, not to reopen donor strategy

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
- tracked `.env.example` template and local `.env` convention
- central LLM/runtime configuration consolidation
- real-validation de-sessionization

### Paused
- donor priority changes
- graph / multimodal reactivation
- donor-as-backend architecture
- promotion/defer strategy changes before new evidence exists

## Execution Rules

- Only work on the current phase described in `03-CURRENT-PHASE.md`.
- Never print or commit a real secret value.
- A tracked template file may be created or updated; the real `.env` file must remain local-only.
- Run GitNexus impact analysis before editing any function, class, or method.
- Use TDD for every implementation slice.
- After each slice: run targeted tests and `gitnexus analyze --embeddings --skills --verbose`.
- If a required change would alter frozen contracts or donor priority, stop and escalate.

## Program State

- package scaffolding: opened
- local env convention: pending
- config consolidation: pending
- real-validation handoff: pending
