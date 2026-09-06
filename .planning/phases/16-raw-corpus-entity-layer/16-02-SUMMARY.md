# Phase 16-02 SUMMARY — E2b Frozen Pure Contract Layer

**Status:** COMPLETE (TDD RED -> GREEN -> REFACTOR + edge-case hardening) + Supplemental Repair (nullable model provenance)
**Date:** 2026-08-06
**Plan:** `.planning/phases/16-raw-corpus-entity-layer/16-02-PLAN.md`
**Selector (all runs, identical):**
`rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_contracts.py -q`

## TDD Evidence

| Stage | Result | Detail |
|---|---|---|
| **RED** | 1 collection error (FAIL) | `ModuleNotFoundError: No module named 'llamaindex_runtime.entity'` at `tests\llamaindex_runtime\entity\test_contracts.py:23`. No implementation file existed; only the test file was written. 1.33s. |
| **GREEN** | 35 passed | Minimal implementation of `llamaindex_runtime/entity/contracts.py` + `__init__.py` + test package `__init__.py`. 0.99s. |
| **REFACTOR** | 35 passed | Behavior-preserving cleanup only: renamed `_nonempty_string` -> `_require_nonempty_scalar`, extracted `_PROVENANCE_FIELD_NAMES` constant, added `_freeze_projection` helper, docstrings. **Test assertions unchanged between GREEN and REFACTOR.** 0.71s. |
| **Post-REFACTOR hardening** | 38 passed, **100%** coverage (158/158) | Added 3 edge-case tests after REFACTOR (invalid coordinate types, non-finite/non-float confidence, unknown input_kind). Existing GREEN/REFACTOR assertions untouched. 1.48s. |

Coverage on `llamaindex_runtime/entity/contracts.py`: `Stmts 158, Miss 0, Cover 100%`.

## Supplemental Repair (2026-08-06): Nullable Model Provenance

**Exact frozen rule adopted** (authority: `.planning/research/PHASE16-CHINESE-NER-MODEL-SELECTION-2026-07-13.md` §3.2 DTO + §4.11, `16-08-PLAN.md` Task 2, `16-07-PLAN.md` Task 1, `16-BOUNDARY.md` D8):

- `model_id: str | None`, `model_revision: str | None`, `artifact_digest: str | None`, `runtime_compatibility_id: str | None` are **conditionally nullable** on `MentionCandidate`.
- `source == "model"` (RaNER) candidates **require complete, digest-valid model provenance**: `model_id` and `model_revision` non-empty strings, `artifact_digest` a valid lowercase SHA-256 digest. `runtime_compatibility_id` may be `None` (pre-smoke unresolved) or a non-empty string; only a separately-authorized offline-mirror smoke freezes it.
- Non-model sources (`dictionary`/`rule`/`frontmatter`) **must carry no model provenance at all** — all four fields `None`; any present value is rejected as forged/partial provenance.
- `source` (`model|dictionary|rule|frontmatter`) stays a distinct literal domain from D3 `confidence_kind`; neither set was changed.

**Repair TDD evidence (same selector):**

| Stage | Result | Detail |
|---|---|---|
| **RED** | 7 failed, 38 passed | Added focused tests for supplementary nullable provenance (dictionary/rule/frontmatter), pre-smoke unresolved `runtime_compatibility_id`, complete-provenance requirement, malformed digest/empty rejection, and non-model provenance forgery rejection; adjusted two existing tests (`test_mention_provenance_fields_are_mandatory` trimmed to always-mandatory fields; `test_query_mention_rejects_frontmatter_source` now isolates the frontmatter check behind a valid supplementary candidate). Failures were `ValueError: model_revision/model_id must be a non-empty string` — the old all-non-null contract. 3.38s. |
| **GREEN** | 45 passed | Implemented `_validate_model_provenance()` in `llamaindex_runtime/entity/contracts.py`; moved `model_id/model_revision/artifact_digest/runtime_compatibility_id` out of the always-mandatory `_PROVENANCE_FIELD_NAMES` and changed their annotations to `str | None`. 2.55s. |
| **REFACTOR** | 45 passed | Behavior-preserving: extracted `_MODEL_PROVENANCE_FIELDS` tuple and replaced the long non-model `or` chain with `any(getattr(self, name) is not None for name in _MODEL_PROVENANCE_FIELDS)`. **Assertions unchanged between GREEN and REFACTOR.** 1.74s. |

Final coverage on `llamaindex_runtime/entity/contracts.py`: `Stmts 173, Miss 0, Cover 100%`.

## Changed Paths (plan-16-02 scope only)

- `llamaindex_runtime/entity/__init__.py` (new) — contracts-only safe facade.
- `llamaindex_runtime/entity/contracts.py` (new) — frozen E2b contract layer; **edited in supplemental repair** for nullable model provenance.
- `tests/llamaindex_runtime/entity/__init__.py` (new) — test package init.
- `tests/llamaindex_runtime/entity/test_contracts.py` (new) — 45 RED/GREEN/REFACTOR tests; **edited in supplemental repair**.
- `16-02-SUMMARY.md` (this file).

Within the 16-02 intended delta, no other file was modified, and no Wave 1+ plan, config, dependency, migration, adapter, repository, or runner was touched. This statement is scope-relative to this plan's own work: it is neither a clean-worktree assertion nor a claim that unrelated pre-existing diffs exist elsewhere in the working tree.

## Public API Summary

- `E2B_NAMESPACE` = `uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2b")` (distinct from `E2A_NAMESPACE`).
- `canonical_json`, `canonical_json_sha256` — **re-exported by identity** from `llamaindex_runtime/okf/e2a_contracts.py` (verified `is`-identical in tests; behavior never copied/diverged).
- `deterministic_id(kind, natural_key)` — E2b-namespace-scoped `uuid5`, rejects empty/non-str.
- `InputKind`, `ConfidenceKind`, `MentionSource` Literal types + `INPUT_KINDS`, `CONFIDENCE_KINDS`, `MENTION_SOURCES` frozensets.
- `CorpusSpanInput` (frozen) — `document_id/version_id/span_id/document_revision/input_revision/normalized_text/normalization_version/projection`; `input_kind="corpus_span"`; `input_id == span_id`; **enforces `input_revision == document_revision` FIELD VALUE (never literal `"document_revision"`)**; projection required and deep-frozen.
- `QueryTextInput` (frozen) — `query_id/query_revision/input_revision/normalized_text/normalization_version`; `input_kind="query_text"`; `input_id == query_id`; **enforces `input_revision == query_revision` FIELD VALUE (never literal `"query_revision"`)**; **no corpus document/sidecar projection fields by construction**.
- `ExtractionInput = CorpusSpanInput | QueryTextInput` (discriminated union).
- `MentionCandidate` (frozen) — full provenance set (`extractor_id/version`, `schema_version`, `normalization_version`, `segmentation_version`, `label_map_digest`, `source`, `confidence_kind`, `raw_label`, `canonical_label`, `entity_type`), plus **conditionally nullable** `model_id`/`model_revision`/`artifact_digest`/`runtime_compatibility_id` (see Supplemental Repair: complete+digest-valid for `source=="model"`, all `None` for supplementary sources). Exact Unicode code-point half-open invariant `0 <= char_start < char_end <= len(normalized_text)` and `normalized_text[char_start:char_end] == mention_text` enforced in `__post_init__` with **no substring recovery**. Corpus mentions require span_id + document/sidecar projection + `input_id == span_id` + `input_revision == document_revision`; query mentions forbid all of those and forbid `frontmatter` source. `confidence is None` only when `confidence_kind == "unavailable"` (bidirectional).

## Boundary Compliance

- **No heavy imports:** `test_importing_entity_package_imports_no_heavy_dependencies` asserts `modelscope`, `torch`, `jieba` are absent from `sys.modules` after importing `llamaindex_runtime.entity`. Reused validation primitives (`_uuid`, `_digest`, `_unicode_scalar`, `_frozen_mapping`) are imported from `llamaindex_runtime/okf/e2a_contract_primitives.py` (stdlib-only chain).
- **No live/model/DB/network/persistence/merger/adapter code:** plan delivers pure frozen DTOs only. Selector unset all listed DB/authorization variables via `env -u`; nothing was read, printed, or persisted.
- **Revision equality is field-value equality** in all three DTOs; tests explicitly reject implementations that hard-code the literal strings `"document_revision"` / `"query_revision"` (e.g. `document_revision="abc-v2"` requires `input_revision="abc-v2"`).

## Design Notes

- `MentionCandidate` carries a `normalized_text` field beyond the plan's explicit minimum field enumeration because the frozen slice-back invariant is enforced in `__post_init__` and must remain downstream-verifiable (BOUNDARY: candidate field list is "至少包含"/at least).
- `query_text` mention candidates reject `frontmatter` source per BOUNDARY ("query 来源只允许 model/dictionary/rule，不得制造 frontmatter 来源").
- `confidence_kind` ladder and `source` value sets are pinned exactly to the frozen D3 contract; `source` remains the four-value `model|dictionary|rule|frontmatter` literal and is not conflated with `confidence_kind`.
- Model provenance (`model_id`/`model_revision`/`artifact_digest`) is all-or-nothing: it is validated as complete and digest-bound for `source=="model"` candidates and entirely absent for supplementary candidates; `runtime_compatibility_id` is unresolved (`None`) until a separately-authorized mirror smoke freezes it.

## Status Scope

This summary documents plan 16-02 (frozen pure contract layer) plus its scoped repair. It does **not** claim Wave 0 completion, Phase 16 completion, any live/model/DB execution, or any adapter/merger/repository readiness.

## Blockers

None. No external service, model download, package installation, git operation, or credential access was required or performed.
