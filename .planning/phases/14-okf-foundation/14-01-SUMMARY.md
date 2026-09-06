---
phase: 14-okf-foundation
plan: 01
subsystem: okf
tags: [contracts, sidecar, canonical-hash, config, bundle-skeleton, tdd]
requires: []
provides:
  - SpanSidecar schema v1 load/dump with fail-fast boundary validation
  - RawFrontmatterContract with named-field error messages
  - canonical_hash for T3 structural comparison (ignores Markdown body reflow)
  - OKF_BUNDLE_ROOT config key with env override and default
  - okf_bundle/ skeleton with AGENT.md policy
affects:
  - llamaindex_runtime/okf/sidecar.py
  - llamaindex_runtime/okf/canonical_hash.py
  - llamaindex_runtime/okf/contracts.py
  - llamaindex_runtime/config.py (additive okf_bundle_root field)
  - okf_bundle/AGENT.md
  - okf_bundle/index.md
  - okf_bundle/log.md
  - okf_bundle/templates/raw.md
  - okf_bundle/templates/entity.md
  - tests/llamaindex_runtime/okf/test_okf_sidecar.py
  - tests/llamaindex_runtime/okf/test_okf_canonical_hash.py
  - tests/llamaindex_runtime/okf/test_okf_contracts.py
  - tests/llamaindex_runtime/okf/test_okf_config.py
tech-stack:
  added:
    - stdlib json/yaml for deterministic serialization
    - dataclasses frozen=True for immutable contracts
  patterns:
    - fail-fast boundary validation with field-named errors
    - canonical serialization: sorted-key JSON, separator-stable, ensure_ascii=False
key-files:
  created:
    - llamaindex_runtime/okf/sidecar.py
    - llamaindex_runtime/okf/canonical_hash.py
    - llamaindex_runtime/okf/contracts.py
    - tests/llamaindex_runtime/okf/test_okf_sidecar.py
    - tests/llamaindex_runtime/okf/test_okf_canonical_hash.py
    - tests/llamaindex_runtime/okf/test_okf_contracts.py
    - tests/llamaindex_runtime/okf/test_okf_config.py
    - okf_bundle/AGENT.md
    - okf_bundle/index.md
    - okf_bundle/log.md
    - okf_bundle/raw/.gitkeep
    - okf_bundle/entities/.gitkeep
    - okf_bundle/concepts/.gitkeep
    - okf_bundle/synthesis/.gitkeep
    - okf_bundle/templates/raw.md
    - okf_bundle/templates/entity.md
  modified:
    - llamaindex_runtime/config.py (additive okf_bundle_root field)
decisions:
  - SpanRecord.page_no allows null (document-level spans without page coordinates)
  - canonical_hash excludes Markdown body; span identity sourced solely from sidecar
  - frontmatter I/O adapted from ogham-mcp (MIT): one trailing newline, CRLF-compatible read
metrics:
  duration: "2026-07-13..2026-07-14 execution and verification"
  tasks_completed: 3
  tests_passed: 72 non-live OKF + 21 config regression
  coverage_total: 85%
  coverage_modules:
    sidecar: 96%
    contracts: 87%
    canonical_hash: 92%
    config: 64%
---

# Phase 14 Plan 01: OKF Foundation Contracts Summary

Sidecar schema v1, raw frontmatter contract, canonical structural hash, OKF_BUNDLE_ROOT config key, and bundle skeleton — TDD contracts for Phase 14-03 serializer and 14-04 rebuild.

## One-Liner

SpanSidecar schema v1 with fail-fast validation, RawFrontmatterContract with named-field errors, canonical_hash for T3 structural comparison (body-excluded), additive OKF_BUNDLE_ROOT config, and okf_bundle/ skeleton with AGENT.md policy.

## Deliverables

### Task 1: RED tests for sidecar, frontmatter contract, canonical hash

**Status:** COMPLETE

- Created `tests/llamaindex_runtime/okf/` package with three test files
- test_okf_sidecar.py: round-trip, schema_version gate, missing spans, negative page_no rejection, null/zero page_no acceptance
- test_okf_contracts.py: valid frontmatter, missing required field naming, non-raw type rejection, YAML I/O round-trip, CRLF handling
- test_okf_canonical_hash.py: frontmatter order independence, span text/offset/page/heading sensitivity, determinism, 64-char hex output, locked concatenation formula verification

### Task 2: Implement sidecar.py, contracts.py, canonical_hash.py

**Status:** COMPLETE

- sidecar.py: SpanRecord (frozen dataclass) with from_dict boundary validation; page_no must be null or non-negative integer; offset must be non-negative integer; heading_path must be list of strings; span_id UUID validation; SpanSidecar with schema_version=1 gate; dump writes UTF-8 JSON with one trailing newline
- contracts.py: RawFrontmatterContract with six required fields (type, doc_id, version_id, source_checksum, docling_version, generated_by); type must be 'raw'; source_checksum must be lowercase SHA256 hex; dump_raw_frontmatter preserves insertion order and Unicode; load_raw_frontmatter handles CRLF and prevents newline accumulation
- canonical_hash.py: canonical_serialize for sorted-key stable JSON; canonical_hash computes SHA256 over frontmatter_dict + spans_list (body excluded)

### Task 3: OKF_BUNDLE_ROOT config key + bundle skeleton + AGENT.md

**Status:** COMPLETE

- config.py: added `okf_bundle_root: str = "okf_bundle"` to RuntimeSettings; from_env reads OKF_BUNDLE_ROOT with process environment precedence
- Bundle skeleton: okf_bundle/{raw,entities,concepts,synthesis}/.gitkeep
- AGENT.md: three-section policy (Always/Ask first/Never) declaring raw/ machine-generated, sidecar files are span identity source, human edits go to entities/concepts/synthesis
- index.md: frontmatter with okf_version: "0.1" plus directory links
- log.md: empty header section for changelog
- templates/raw.md: frontmatter template matching RawFrontmatterContract plus recommended title/timestamp fields
- templates/entity.md: frontmatter template with OKF extension fields (aliases, canonical_entity_id, entity_type, relations, mentions)

## Verification Results

### Complete Non-Live OKF Suite

```
python -m pytest tests/llamaindex_runtime/okf/ -q -m "not integration"
72 passed, 4 deselected, 2 warnings
```

This includes the expanded boundary-remediation coverage for required sidecar keys and scalar/container types, constructor invariants, dataclass instance/class normalization, frontmatter I/O, configuration, and migration runner fail-closed behavior.

### Config Regression Suite

```
python -m pytest tests/llamaindex_runtime/okf/test_okf_config.py tests/llamaindex_runtime/test_runtime_settings_env_file_loading.py tests/llamaindex_runtime/test_config_llm_settings.py -q
21 passed, 2 warnings
```

232 total config-related regression tests passed across broader suite.

### Coverage

Phase 14-01 implementation-module scope: 85%

| Module | Coverage |
|--------|----------|
| sidecar.py | 96% |
| contracts.py | 87% |
| canonical_hash.py | 92% |
| config.py | 64% |

### Static Verification

- Isolated mypy (`--follow-imports=skip`) on `sidecar.py`, `canonical_hash.py`, and `run_migrations.py`: **Success, no issues found**
- Ruff on the Wave 1 Python scope: **No issues found**
- `compileall`: **passed**
- `git diff --check`: **passed**

### Independent Review Gate

Four independent Opus reviews returned **APPROVE**:

- General code/plan compliance: 0 CRITICAL / 0 HIGH / 0 MEDIUM
- Python correctness/test isolation: 0 CRITICAL / 0 HIGH; its parser observation is Phase 14-03 scope, and schema-version acceptance is already exercised by round-trip coverage
- Database: 0 CRITICAL / 0 HIGH; one non-blocking performance index and one LOW behavioral-test enhancement explicitly deferred to Phase 16 pre-population schema hardening
- Security: 0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW

Current-status correction (2026-07-17): the Phase 14 closeout/verification artifacts contain no credential or `DATABASE_URL` values, and protected variables were isolated as recorded. This does not assert that no `DATABASE_URL`-class examples exist anywhere in historical planning artifacts.

### Canonical Hash Determinism

Locked concatenation formula verified:
```
SHA256(canonical_serialize(frontmatter_dict) + canonical_serialize(spans_list))
```

Example hash: `ac9aa2f37b49182b921c0bab2fbd6359b00eb01c171d9b7ec1ac7d9ac492f8c2`

### Page Number Validation

- `page_no=-1` → ValueError: "page_no must be a non-negative integer or null"
- `page_no=None` → ACCEPTED (document-level spans without page coordinates)
- `page_no=0` → ACCEPTED (valid first-page coordinate)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added page_no non-negative validation**

- **Found during:** Task 2 implementation
- **Issue:** Plan interface showed `page_no: 3` but did not explicitly state validation for negative values; negative page numbers would be meaningless in document coordinates
- **Fix:** Added explicit validation in SpanRecord.from_dict: `page_no must be null or a non-negative integer`
- **Files modified:** llamaindex_runtime/okf/sidecar.py
- **Tests added:** test_sidecar_rejects_negative_page_number, test_sidecar_accepts_null_and_zero_page_numbers

### Config GitNexus HIGH Warning

GitNexus `detect-changes` reported HIGH risk due to 20 files with uncommitted changes, including RuntimeSettings modifications. The Phase 14 changes are additive (single `okf_bundle_root` field) and do not alter existing behavior. The HIGH rating reflects overall working-tree breadth unrelated to this plan. Mitigation: surgical additive edit preserved existing hunks; focused config regression suite (21 passed) confirmed no behavioral regression.

### Pre-existing Untracked Files Not Modified

- `llamaindex_runtime/okf/parser.py` — pre-existing parser module; NOT modified by 14-01
- `llamaindex_runtime/okf/__init__.py` — pre-existing package initializer; NOT modified by 14-01

These files existed before Phase 14 and remain untouched. Plan 14-01 scope is strictly the three contract modules (sidecar.py, canonical_hash.py, contracts.py), additive config field, and bundle skeleton.

### Database Coverage Ownership

Live PostgreSQL verification belongs primarily to Plan 14-02, but the complete Wave 1 disposable-database run also exercised all OKF tests: **76 passed, 2 warnings**. See `14-02-SUMMARY.md` for migration and root-runner evidence.

## Threat Model Compliance

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-14-01 | mitigate | schema_version gate in SpanSidecar.from_dict; canonical_hash detects content drift |
| T-14-02 | accept | AGENT.md declares raw/ policy; enforcement deferred to 14-04 round-trip gate |

## Known Stubs

None. All contract modules are fully implemented with GREEN tests.

## Deferred Issues

None for Plan 14-01. Phase 14-03 parser work remains intentionally outside this plan.

## Output

All deliverables complete and independently approved. No commit made; unrelated dirty working-tree files remain untouched.