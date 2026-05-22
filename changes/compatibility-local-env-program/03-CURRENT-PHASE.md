# Compatibility Local Env Program — Current Phase

## Program Status

- env contract/template freeze: completed
- RuntimeSettings extension: completed
- unified seam migration: active
- real-validation handoff: pending

## Active Phase

### Phase 3 — Unified seam migration (ACTIVE)

Goal:
- migrate the unified LLM path off direct session-only secret dependency
- support local .env loading for real validation
- preserve mock/fallback behavior when no real key exists

Exit criteria:
- unified LLM seam reads from RuntimeSettings instead of direct os.getenv
- local .env values flow through centralized config
- mock/fallback preserved when OPENAI_API_KEY absent
- real validation can run with local .env without session mutation

## Completed Phases

### Phase 2 — RuntimeSettings extension (COMPLETED)

Exit criteria achieved:
- RuntimeSettings class has LLM-specific fields (openai_api_key, llm_model, llm_temperature, openai_base_url)
- config.py reads from local .env via from_env()
- validation tests pass (12 tests, all GREEN)
- existing runtime behavior unchanged when LLM absent

### Phase 1 — Env contract and template freeze (COMPLETED)

Exit criteria achieved:
- tracked template file exists: .env.example committed
- ignore rules allow template tracked, real .env local-only
- all planned variables listed explicitly (13 variables)
- placeholder values filled where possible
- secret slots obvious local-fill placeholders

## Upcoming Phases

### Phase 4 — Real-validation handoff
- sync the real-validation child package to the local `.env` workflow
