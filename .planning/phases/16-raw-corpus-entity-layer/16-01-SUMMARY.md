<!-- generated-by: gsd-doc-writer -->
---
phase: 16-raw-corpus-entity-layer
plan: 01
type: execute
requirements: [R-OKF-04, R-OKF-06]
key-files:
  created:
    - tests/llamaindex_runtime/test_runtime_settings_phase16.py
    - tests/llamaindex_runtime/test_phase16_markers.py
  modified:
    - llamaindex_runtime/config.py
    - llamaindex_runtime/pyproject.toml
    - tests/conftest.py
---

# Phase 16-01 Summary — RAG_ENTITY_EXTRACTOR default-off control plane and ner/live_ner/disposable_db test infrastructure

**Status: DELIVERED (TDD).** Phase 16-01 wired the C1 default-off control plane (`RAG_ENTITY_EXTRACTOR=off|raner`) and the test-infrastructure markers/extra that keep heavy entity dependencies out of the default config/entity import boundary, per [16-01-PLAN.md](16-01-PLAN.md). Marker registration alone does not exclude tests from default collection; live-test exclusion requires an explicit `-m` filter, and Wave 0 created no `live_ner`/`disposable_db` test module. Red-Green was demonstrated with the new selectors and relevant existing config regression selectors. **No live work, no model download/inference, no DB/Docker/network, no commit/push.**

## TDD Evidence

### RED (new selectors, before implementation)

Command (all database/auth variables cleared, `rtk`-prefixed):

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/test_runtime_settings_phase16.py tests/llamaindex_runtime/test_phase16_markers.py -q --no-header -p no:cacheprovider
```

Result: **23 failed, 2 passed in 2.44s**. Failures were the intended RED signal: missing `VALID_ENTITY_EXTRACTORS` / `rag_entity_extractor` / `__post_init__` validation / `from_env` read, missing `ner` optional extra, and missing `live_ner` / `disposable_db` markers in pyproject.toml and conftest.py.

### GREEN (new selectors, after minimal implementation)

Same command re-run: **25 passed in 0.86s**.

### Regression (existing config selectors, after implementation)

```
rtk env <same -u list> pytest tests/llamaindex_runtime/test_runtime_settings_env_file_loading.py tests/llamaindex_runtime/test_unified_llm_runtime_settings.py tests/llamaindex_runtime/test_backend_harness.py tests/llamaindex_runtime/test_runtime_packaging.py -k runtime_settings -q --no-header -p no:cacheprovider
```

Result: **18 passed, 36 deselected in 13.10s** (all relevant config/packaging `runtime_settings` tests green).

```
rtk env <same -u list> pytest tests/llamaindex_runtime/test_config_llm_settings.py tests/llamaindex_runtime/okf/test_okf_config.py -q --no-header -p no:cacheprovider
```

Result: **14 passed in 0.70s**.

```
rtk env <same -u list> pytest tests/llamaindex_runtime/test_backend_harness.py -q --no-header -p no:cacheprovider
```

Result: **6 passed in 0.53s** (pyproject optional-dependency/marker static validation still green).

```
rtk env <same -u list> pytest tests/llamaindex_runtime/test_runtime_packaging.py -q --no-header -p no:cacheprovider
```

Result: **33 passed, 2 warnings in 333.32s** (full packaging/lazy-import/network-free suite green). This broader packaging selector may import torch elsewhere, so by itself it is NOT proof of the default config/entity import boundary; the boundary-specific subprocess selector in `test_runtime_settings_phase16.py` asserts that constructing `RuntimeSettings` / importing `llamaindex_runtime.entity` imports no `torch`/`modelscope`/`transformers`/`sentencepiece`.

```
rtk proxy pytest --markers
```

Result: `@pytest.mark.live_ner`, `@pytest.mark.disposable_db` present; pre-existing `@pytest.mark.live_st` and `@pytest.mark.integration` preserved (runtime registration confirmed).

### REFACTOR

No refactor pass was required; the minimal implementation already matched the project's existing `VALID_*` ClassVar + `__post_init__` + `from_env` convention in `config.py`, the existing `[tool.pytest.ini_options] markers` list in pyproject.toml, and the existing `config.addinivalue_line` pattern in conftest.py. All tests re-ran green after the change (no refactor-only rerun was needed).

## Deliverables

### 1. Control-plane switch

**File:** `llamaindex_runtime/config.py`

- `VALID_ENTITY_EXTRACTORS: ClassVar[frozenset[str]] = frozenset({"off", "raner"})` alongside the existing `VALID_*` ClassVars.
- New field `rag_entity_extractor: str = "off"` (default off; zero model/generative-LLM cost on the enabled baseline, R-OKF-04).
- `__post_init__` validation rejects any value outside `off|raner` with a `ValueError` ("Unsupported entity extractor: ...") before any entity code/model package could be imported.
- `from_env()` reads `rag_entity_extractor=os.getenv("RAG_ENTITY_EXTRACTOR", "off")` preserving the existing process-env-over-`.env`-file precedence (no change to any other setting's semantics). No C2 `RAG_COREF_RESOLVER` switch was added (out of scope here).

### 2. Optional ner extra and pytest markers

**File:** `llamaindex_runtime/pyproject.toml`

- `[project.optional-dependencies] ner = ["modelscope>=1.39,<2", "sentencepiece"]` (bare minimal surface; no torch/transformers direct deps — they arrive transitively via modelscope and are never imported on the default path).
- `[tool.pytest.ini_options] markers` extended with `live_ner` and `disposable_db` (existing `live_st` preserved).

**File:** `tests/conftest.py`

- `pytest_configure` registers the same two markers via `config.addinivalue_line`, matching the existing `live_st`/`integration` pattern.

### 3. Tests

**Files:** `tests/llamaindex_runtime/test_runtime_settings_phase16.py`, `tests/llamaindex_runtime/test_phase16_markers.py`

- Accepted/rejected values: default `off`, `off`/`raner` accepted, `uie`/`hanlp`/`deepke`/`""`/`base-news` rejected with `ValueError`.
- `from_env()` behavior: reads `raner`, defaults to `off` when unset (cwd-isolated), rejects invalid env value, process-env-wins-over-`.env`-file, `.env`-file-loaded-when-process-absent (precedence preserved).
- No heavy import at config construction: subprocess selector proves constructing `RuntimeSettings` imports no `modelscope`/`torch`/`sentencepiece` and emits no stderr.
- Marker/extra static validation: reads pyproject.toml markers and optional-dependencies and conftest registrations so a typo is caught statically.

## Test totals

- New selectors: **25 passed** (`test_runtime_settings_phase16.py` + `test_phase16_markers.py`).
- Existing config regression selectors (runtime-settings env-file / unified-LLM / backend-harness / packaging `-k runtime_settings` / config-llm / okf-config): **18 + 14 + 6 + 33 = 71 passed**, 36 deselected.
- All commands cleared the listed database/auth variables and were `rtk`-prefixed; environment values were never printed.

## Changed paths (the plan's intended delta)

The list below describes only the 16-01 plan's intended delta (the files it created and the specific hunks it added). It is NOT a clean-worktree assertion and does not claim that no unrelated pre-existing diffs exist in the working tree. In particular, `llamaindex_runtime/config.py`, `llamaindex_runtime/pyproject.toml`, and `tests/conftest.py` may carry unrelated pre-existing diffs that are neither created by nor attributed to Wave 0.

- `llamaindex_runtime/config.py` — added `VALID_ENTITY_EXTRACTORS`, `rag_entity_extractor` field, `__post_init__` validation, `from_env()` read.
- `llamaindex_runtime/pyproject.toml` — `ner` optional extra + `live_ner`/`disposable_db` markers.
- `tests/conftest.py` — `live_ner`/`disposable_db` marker registration.
- `tests/llamaindex_runtime/test_runtime_settings_phase16.py` — new focused switch/env/no-import tests.
- `tests/llamaindex_runtime/test_phase16_markers.py` — new focused marker/extra static tests.
- `.planning/phases/16-raw-corpus-entity-layer/16-01-SUMMARY.md` — this summary.

Within the 16-01 intended delta, no other files were touched. This statement is scope-relative to this plan's own work: it is neither a clean-worktree assertion nor a claim that unrelated pre-existing diffs elsewhere are absent.

## Decisions Made

- Followed the existing `VALID_*` ClassVar + `__post_init__` + `from_env` convention in `config.py` rather than a new config mechanism.
- Marker strings in pyproject.toml and conftest.py are kept identical so the static assertion and the runtime `--markers` output agree.
- No C2 `RAG_COREF_RESOLVER` switch was added; that is scoped to the C2 entry plan.

## Deviations from Plan

None — plan executed exactly as written (TDD applied despite `type: execute` per coordinator instruction). No commit/push was performed; within the 16-01 intended delta, this summary is the only output artifact besides the plan's file delta.

## Non-claims

- No quality/Level claim; no production readiness; no external database, Docker, network, or model download; no model download/inference. The default config/entity import boundary (subprocess no-import selector) imports no `torch`/`modelscope`/`sentencepiece`; the broader packaging selector is not claimed as whole-suite import proof.
- `live_ner` and `disposable_db` tests do not exist yet (Wave 0 created no live test module); marker registration alone does not exclude anything — live-test exclusion requires an explicit `-m` filter.
- The `ner` extra is not installed by default; the default config/entity import boundary (asserted by the subprocess no-import selector) does not import modelscope/torch/sentencepiece.

## Next Phase Readiness

- 16-02 (extractor contracts) can consume `VALID_ENTITY_EXTRACTORS` / `rag_entity_extractor` with the fail-fast default-off contract in place.
- 16-05/16-06/16-07 (segmenter / RaNER adapter / read-only mirror + `ner` extra) can rely on the `ner` optional extra and the `live_ner` marker being registered (live-test exclusion via an explicit `-m` filter).
- Any disposable-DB plan can use the `disposable_db` marker; its own authorization gate names the specific variable.
