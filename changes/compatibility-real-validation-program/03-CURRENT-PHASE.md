# Compatibility Real-Validation Program — Current Phase

## Program Status

- validation package: opened
- validation input freeze: pending
- credentialed donor execution: pending
- rerun / bug-fix loop: pending
- independent review: pending

## Active Phase

### Phase 1 — Validation input freeze with local .env (ACTIVE)

Goal:
- verify the local .env credential status as `set` or `missing` (via RuntimeSettings.from_env_llm_only())
- choose one real validation document and one real query
- choose one output artifact path for the fresh validation result

Exit criteria:
- secret value is never printed (local .env file kept untracked)
- credential status recorded as `set` or `missing` from RuntimeSettings.from_env_llm_only()["openai_api_key"]
- one real document path is fixed (from .env REAL_VALIDATION_DOCUMENT_PATH)
- one real query is fixed (from .env REAL_VALIDATION_QUERY)
- one output artifact path is fixed
- if credentials missing, stop and report blocker (no session mutation required)

## Upcoming Phases

### Phase 2 — Credentialed donor execution
- run the real donor validation pass
- determine whether the path is truly credentialed or still stub/fallback

### Phase 3 — Minimal bug-fix loop if needed
- only if real validation exposes a concrete code bug
- rerun the exact same validation after the fix

### Phase 4 — Review and recommendation
- summarize whether the parent package should keep `DEFER`
- require an independent second-person review before any promotion claim
