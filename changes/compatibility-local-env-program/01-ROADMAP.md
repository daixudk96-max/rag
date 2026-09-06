# Compatibility Local Env Program — Roadmap Snapshot

## Mainline Route

### Line A — Local env convention
- introduce a tracked template for local secret/config values
- keep the actual `.env` file untracked and local-only

### Line B — RuntimeSettings consolidation
- extend the existing runtime settings seam so LLM config stops living in ad-hoc direct env reads
- keep default behavior stable where no real key is present

### Line C — Unified LLM seam migration
- migrate `llamaindex_runtime/llm/__init__.py` off direct `OPENAI_API_KEY` access toward centralized settings
- support local `.env` loading for real validation

### Line D — Validation handoff
- make the real-validation package depend on local file-based config instead of shell session mutation

## Phase Sequence

### Phase 1 — Env contract and template freeze
- define the env variables to support
- create/update the tracked template file
- ensure git ignore rules are safe

### Phase 2 — RuntimeSettings extension
- add LLM-specific settings fields
- validate new configuration inputs cleanly

### Phase 3 — Unified seam migration
- load local `.env` values into the unified LLM path
- preserve mock/fallback behavior when no real key exists

### Phase 4 — Real-validation package sync
- update real-validation prompts and artifacts to use the local env convention
- verify a no-session-mutation workflow is possible

## Current Program Sequence

1. freeze the local env contract first
2. centralize configuration second
3. migrate the unified seam third
4. only then rerun real validation from the child validation package
