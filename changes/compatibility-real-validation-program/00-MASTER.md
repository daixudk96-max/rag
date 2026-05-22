# Compatibility Real-Validation Program — MASTER CONTROL

## Mission

Run a real credentialed donor validation pass after the Phase 8 script/test cleanup, using a real document and a real session-scoped `OPENAI_API_KEY`, without changing frozen contracts or reopening paused branches.

## Parent Inheritance

This child program inherits frozen donor strategy, paused branches, and immutable provenance constraints from:
- `../compatibility-adapter-program/00-MASTER.md`
- `../compatibility-adapter-program/03-CURRENT-PHASE.md`

## Frozen Strategic Decision

1. validation comes before new feature work
2. allow only minimal bug fixes if the real validation exposes a clear defect
3. Phase 4 Migration: secrets now live in local .env (not session-scoped), never print or persist them
4. RuntimeSettings.from_env_llm_only() provides LLM config without DATABASE_URL requirement
5. do not reopen graph or multimodal branches during validation work

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
- session-scoped credential gate
- real donor execution on a real document
- artifact capture and failure classification
- independent second-person review after the first run

### Paused
- donor priority changes
- graph / multimodal reactivation
- donor-as-backend architecture
- broad feature work unrelated to validation

## Execution Rules

- Only work on the current phase described in `03-CURRENT-PHASE.md`.
- Do not print the secret value; only report `set` / `missing`.
- Use a real validation document and a real query, not the default sample stub, for the credentialed run.
- If code changes become necessary, run GitNexus impact analysis first and use TDD for the smallest possible fix.
- After each slice: run targeted tests and `gitnexus analyze --embeddings --skills --verbose`.
- Keep the current Phase 8 `DEFER` decision in place unless fresh evidence truly changes the picture.

## Program State

- validation package: opened
- real credentialed donor run: pending
- independent review: pending
