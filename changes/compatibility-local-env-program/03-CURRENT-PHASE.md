# Compatibility Local Env Program — Current Phase

## Program Status

- env contract/template freeze: completed
- RuntimeSettings extension: completed
- unified seam migration: completed
- real-validation handoff: active

## Active Phase

### Phase 4 — Real-validation handoff (ACTIVE)

Goal:
- sync the real-validation child package to the local `.env` workflow
- verify a no-session-mutation workflow is possible

Exit criteria:
- real-validation package reads from local .env (not session mutation)
- real-validation tests pass with RuntimeSettings-based config
- documentation updated to reflect local .env workflow
- no direct os.getenv(OPENAI_API_KEY) in real-validation code

## Completed Phases

### Phase 3 — Unified seam migration (COMPLETED)

Exit criteria achieved:
- unified LLM seam reads from RuntimeSettings.from_env_llm_only()
- local .env values flow through centralized config
- mock/fallback preserved when OPENAI_API_KEY absent
- real validation can run with local .env without session mutation
- LLM config independent of DATABASE_URL (from_env_llm_only helper)
- LiteLLMWrapper abstract methods implemented

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
