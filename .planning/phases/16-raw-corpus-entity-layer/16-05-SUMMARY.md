---
phase: 16-raw-corpus-entity-layer
plan: 05
subsystem: entity
tags: [segmenter, token-aware, deterministic-id, code-point, unicode, fail-closed, tdd]
requires:
  - phase: 16-02
    provides: Frozen CorpusSpanInput, canonical_json/deterministic_id helpers over the E2b namespace.
provides:
  - Deterministic token-aware segmentation of CorpusSpanInput.normalized_text into frozen Segment values with exact full-span coverage, zero overlap, zero gap.
  - Exact deterministic segment_id from (parent_span_id, start, end, segmentation_version) only, with no model/extractor/tokenizer identity.
  - Injected fast-tokenizer-compatible offset boundary (attribute or mapping-key offset_mapping), canonicalized by sorting for shuffle-equivalent determinism.
  - Fail-closed handling of max_tokens <= 0 (bools not ints), empty segmentation_version, empty normalized_text, non-callable/malformed tokenizer output, and offset out-of-range/zero-length/overlap.
affects: [16-06, 16-07, 16-08]  # downstream candidate/candidate-flow phases consume segmentation_version + segment boundaries

tech-stack:
  added: []
  patterns:
    - "Injected fast-tokenizer boundary: tokenizer(text) returns offset_mapping as attribute or mapping key; offsets are Python code-point half-open [start, end) pairs; no truncation, no special tokens."
    - "Offset canonicalization by sorting -> shuffle-equivalent determinism; strict structural validation (int-not-bool, in-range, start < end, non-overlapping) fails closed."
    - "Segment closes at the start of the first excluded token (trailing tail closes at len(text)); inter-token whitespace attaches to the preceding segment while coverage stays exact."
    - "segment_id = deterministic_id('segment', canonical_json({parent_span_id, start, end, segmentation_version})) — identity carries provenance coordinates only."

key-files:
  created:
    - tests/llamaindex_runtime/entity/test_segmenter.py
    - llamaindex_runtime/entity/segmenter.py
  modified:
    - llamaindex_runtime/entity/__init__.py
  summary:
    - .planning/phases/16-raw-corpus-entity-layer/16-05-SUMMARY.md

key-decisions:
  - "Tokenizer boundary explicitly locally documented (HF-fast-tokenizer-compatible): consume authoritative code-point offsets; never recover positions by substring search."
  - "Boundary placement: close at the start of the first excluded token (inter-token whitespace precedes) so every segment contains whole tokens and coverage is exact."
  - "segment_id excludes model/extractor/tokenizer identity per the frozen identity contract; unique per (span, start, end, segmentation_version)."
  - "Reject bool silently as int everywhere (max_tokens and offset coordinates) via strict type() checks."

patterns-established:
  - "Private helpers _extract_offset_mapping/_validate_offsets/_segment_bounds/_segment_identity/_verify_exact_coverage isolate the tokenizer boundary, offset validity, boundary math, identity, and coverage invariant."
  - "Defensive _verify_exact_coverage fail-closed guard is structurally unreachable through the public API (single uncovered defensive line, 99% branch/statement coverage)."

requirements-completed: [R-OKF-06]

duration: "multi-round; initial TDD ~25min, subsequent hardening and verification recorded below"
completed: 2026-08-07
---

# Phase 16: Plan 05 Summary

**Deterministic token-aware segmenter that splits CorpusSpanInput.normalized_text into frozen Segment values with exact code-point full-span coverage, zero gap, zero overlap, and provenance-coordinate-only segment_id, built strictly test-first with a fully frozen public API**

## TDD Evidence

### Step A: RED

- Confirmed `llamaindex_runtime/entity/segmenter.py` did not exist before the run.
- Selector (exactly the frozen verify command):
  `rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_segmenter.py -q`
- Result: genuine missing-module collection failure.
  ```
  ERROR collecting tests/llamaindex_runtime/entity/test_segmenter.py
  ImportError while importing test module '...\test_segmenter.py'
  tests\llamaindex_runtime\entity\test_segmenter.py:34: in <module>
      from llamaindex_runtime.entity import Segment, segment_text
  E   ImportError: cannot import name 'Segment' from 'llamaindex_runtime.entity'
  1 error in 1.86s
  ```
- No implementation file existed during this run.

### Step B: GREEN

- Implemented `llamaindex_runtime/entity/segmenter.py` (stdlib + `.contracts` only) and exported `Segment` + `segment_text` from `llamaindex_runtime/entity/__init__.py`.
- First GREEN run surfaced one wrong expected value in a NEW test authored in this step (`test_leading_whitespace_multi_segment_boundaries`): the fixture `"  猫猫  狗狗"` was miscounted as 9 code points when it is 8. The implementation was correct; the test expectation was corrected to `[(0, 6, "  猫猫  ", 1), (6, 8, "狗狗", 1)]` and an explicit `assert len(text) == 8` was added. This tightened, did not weaken, the assertion.
- GREEN selector result (same command): `68 passed in 1.69s`.

### Step C: REFACTOR

- Behavior-preserving cleanup only: extracted `_segment_identity` (frozen canonical payload) and `_verify_exact_coverage` (defensive coverage invariant) as private helpers; test assertions untouched.
- REFACTOR selector result (same command, distinct run): `68 passed in 1.90s`.

### Step D: Regression + coverage

- Regression: `pytest tests/llamaindex_runtime/entity -q` => `158 passed in 2.44s` (68 segmenter + contracts + merger).
- Coverage (focused): `pytest tests/llamaindex_runtime/entity/test_segmenter.py --cov=llamaindex_runtime.entity.segmenter --cov-branch --cov-report=term-missing -q`
  - Statement coverage: **99%** (94/95); Branch coverage: **99%** (54 branches, 1 partial). Both far above the 80% mandate.
  - The single uncovered line (163) is the defensive `raise` inside `_verify_exact_coverage`; it is structurally unreachable through the public API (validated offsets always yield boundaries starting at 0 and ending at len(text) with strictly increasing coordinates). Covering it would require inspecting private internals, which the frozen test contract forbids.

## Non-Live Execution Boundaries (confirmed)

- No modelscope/torch/transformers/tokenizers/sentencepiece/jieba imports anywhere; the segmenter source imports only stdlib + `.contracts`, verified both by static source guard tests and by a fresh-subprocess import test asserting none of the heavy modules appear in `sys.modules`.
- No Docker/PostgreSQL, no DATABASE_URL access, no network, no package installation, no real tokenizer/model, no ModelScope mirror, no RaNER inference, no live gate, no C2, no commit, no push.
- The subprocess import test forwards only `PYTHONPATH` and `PATH` to the child interpreter — no credential-bearing environment variables are read, printed, logged, or persisted.
- All sensitive env guards (`DATABASE_URL`, `FORMAL_RUNTIME_DATABASE_URL`, all `OKF_*` authorization flags) were unset in-process before every Bash command via `rtk env -u`.
- Scope strictly limited to the four-file allowlist: `tests/llamaindex_runtime/entity/test_segmenter.py` (created), `llamaindex_runtime/entity/segmenter.py` (created), `llamaindex_runtime/entity/__init__.py` (facade exports only), `16-05-SUMMARY.md` (this file). No pre-existing dirty work was modified.

## Files Created/Modified

- `tests/llamaindex_runtime/entity/test_segmenter.py` - RED tests pinning the frozen Segment shape, exact canonical segment_id, full-span coverage/adjacency, token budgets, shuffle-equivalence, Unicode code-point safety, repeated-text non-recovery, whitespace handling, fail-closed inputs, static forbidden-API/import guards, facade exports, and fresh-process heavy-import boundary.
- `llamaindex_runtime/entity/segmenter.py` - deterministic token-aware segmenter (frozen `Segment`, `segment_text`, private offset/tokenizer-boundary helpers).
- `llamaindex_runtime/entity/__init__.py` - exports `Segment` and `segment_text`; package import still never imports modelscope/torch/jieba/sentencepiece.

## Design Choices at the Tokenizer Boundary

- **Explicit locally documented boundary:** injected callable `tokenizer(text)` mirrors a HuggingFace fast tokenizer called with `return_offsets_mapping=True`, no truncation, no special tokens. Its result must expose `offset_mapping` either as an attribute or as a mapping key (BatchEncoding-style); entries are Python Unicode code-point half-open `[start, end)` pairs.
- **Authoritative offsets, no substring recovery:** positions are consumed directly from `offset_mapping`; no `str.find`/`str.index`/substring search or ModelScope split-length API is used (static-guard tested).
- **Shuffle-equivalent determinism:** offsets are structurally validated (int-not-bool, in-range, `start < end`, non-overlapping/duplicate-rejecting) then sorted canonically, so repeated, reversed, or shuffled-but-valid tokenizer output yields byte-identical segments.
- **Boundary placement:** each segment closes at the start of the first excluded token (trailing tail closes at `len(text)`), so every segment holds whole tokens and inter-token whitespace attaches to the preceding segment while coverage remains exact.
- **Identity:** `segment_id = deterministic_id("segment", canonical_json({"parent_span_id": span.span_id, "start": start, "end": end, "segmentation_version": segmentation_version}))` — provenance coordinates only; unique per segment; independent of tokenizer/model/extractor.

## Issues Encountered

- One new-test expectation miscounted code points in the leading-whitespace fixture during the GREEN run (documented above). Corrected the expectation; no implementation change was required. No other issues.

## Next Phase Readiness

- `Segment` + `segment_text` are frozen and exported; downstream phases (16-06 candidate flow and beyond) can consume `segmentation_version` and segment boundaries with exact code-point coordinates.
- 16-05 boundary respected: no candidates were created and 16-06 behavior was not implemented.

---

# Coordinator-Inspection Hardening (appended after completion)

## Gap found by coordinator inspection

`segment_text` invoked the injected tokenizer position-only (`tokenizer(text)`).
A real HuggingFace **fast** tokenizer defaults to emitting **no** `offset_mapping`
unless requested, so the future 16-07 tokenizer would return no offsets and
16-05 would fail in actual integration. The original RED/GREEN/REFACTOR history
above is preserved as recorded; this section documents the follow-up TDD repair.

## Repair TDD evidence (four-file allowlist only)

### Repair RED (new focused regression test only)

- Added `_RecordingTokenizer` — a strict fake that **requires** the keyword-only
  fast-tokenizer contract (`return_offsets_mapping`, `add_special_tokens`,
  `truncation`, no defaults) and records each call. Added the focused test
  `test_tokenizer_invoked_with_required_fast_tokenizer_kwargs`.
- Ran only that test against the pre-fix implementation:
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py -q -k "tokenizer_invoked_with_required_fast_tokenizer_kwargs"`
- Result (genuine RED):
  ```
  TypeError: _RecordingTokenizer.__call__() missing 3 required keyword-only
  arguments: 'return_offsets_mapping', 'add_special_tokens', and 'truncation'
  1 failed, 68 deselected in 2.50s
  ```

### Repair GREEN

- `segment_text` now invokes the tokenizer with the exact frozen keyword contract
  `_TOKENIZER_KWARGS = {"return_offsets_mapping": True, "add_special_tokens": False, "truncation": False}`.
- Added `_validate_tokenizer`: rejects non-callable tokenizers and any tokenizer
  explicitly advertising `is_fast is False` (slow tokenizer) **before** any call
  (fail-closed fast-only boundary; the slow tokenizer is never invoked).
- Added the `Segment` value-object invariant `end - start == len(text)` (a
  validation change, not a field change) with direct fail-closed tests.
- All existing fake tokenizers in the test suite now expose `is_fast = True` and
  accept/validate the exact keyword-only contract via explicit keyword-only
  parameters plus `assert` on exact values (no blanket `**kwargs` acceptance).
- Full focused selector result (all segmenter tests):
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py -q` =>
  `73 passed in 1.75s` (68 original + 5 new hardening tests).

### New hardening tests added (exact kwarg verification)

1. `test_tokenizer_invoked_with_required_fast_tokenizer_kwargs` — the recording
   fake proves `segment_text` passes all three exact keywords with the exact
   values and the full `text`.
2. `test_slow_tokenizer_advertising_is_fast_false_fails_closed` — a tokenizer
   with `is_fast = False` raises `ValueError("...fast tokenizer...")` and is
   never invoked.
3. `test_tokenizer_full_text_no_truncation_and_no_special_tokens` — the recorded
   call receives the full normalized text (truncation=False) and every segment
   slices back exactly.
4. `test_special_token_zero_length_offset_fails_closed` — a `(0,0)` special-token
   offset is rejected (`start < end`), so CLS/SEP can never leak into segment
   coordinates.
5. `test_segment_rejects_text_length_mismatch_with_interval` — `Segment` fails
   closed when `len(text) != end - start` in either direction.

### Repair regression + coverage

- Full entity directory regression:
  `pytest tests/llamaindex_runtime/entity -q` => `163 passed in 2.13s`
  (was 158 before hardening; +5 new tests).
- Focused branch coverage:
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py --cov=llamaindex_runtime.entity.segmenter --cov-branch --cov-report=term-missing -q`
  => `73 passed`; **99% statements (101/102), 99% branches (58/59 partial)**.
  The single uncovered line (184) is the defensive `raise` in
  `_verify_exact_coverage`, structurally unreachable through the public API.
- Static source guards re-verified: no `str.find`/`.find(`/`str.index`/
  `.index(`/`split_max_length`, and no modelscope/torch/transformers/tokenizers/
  sentencepiece/jieba imports in `segmenter.py`; fresh-process heavy-import
  boundary still passes.

## Final tokenizer call contract (frozen, documented in segmenter.py)

```
tokenizer(text, return_offsets_mapping=True, add_special_tokens=False, truncation=False)
```

- `return_offsets_mapping=True` — a fast tokenizer otherwise emits no offsets.
- `add_special_tokens=False` — no CLS/SEP `(0,0)` offsets can appear.
- `truncation=False` — the full normalized text is always tokenized.
- Fail-closed guards: non-callable tokenizer; `is_fast is False` (slow
  tokenizer, rejected before invocation); missing `offset_mapping`; malformed /
  out-of-range / zero-length / overlapping offsets.
- The injected boundary stays pure: no transformers/tokenizers import, no
  network, no model. 16-06 typed errors were not introduced.

## Repair boundaries confirmed

No DB, Docker, PostgreSQL, network, model/tokenizer, ModelScope mirror, RaNER
inference, live gate, C2, commit, or push. No credential-bearing environment
variables read/printed/logged/persisted; every Bash command unset the guard env
vars in-process and was prefixed with `rtk`. Only the original four-file
allowlist was touched.

---

# Round-2 Coordinator-Inspection Hardening (appended after Round 1)

## Gap found by second coordinator inspection

1. **Offset-coverage fail-open:** `_validate_offsets` accepted an empty offset
   list for any non-empty text, and accepted offset lists that left
   non-whitespace prefix/middle/suffix code points uncovered. A tokenizer
   returning `[]` for `"abc"` (or only `[(0, 1)]` for `"abc"`) produced one
   whole-text segment with `token_count` 0/1, silently defeating the max-token
   truncation protection.
2. **Mutable module-level contract dict:** `_TOKENIZER_KWARGS` was a mutable
   module-level dict and could be modified at runtime to re-enable
   truncation/special tokens, violating the project immutability rule.

The Round-1 history above is preserved truthfully as recorded; this section
documents the Round-2 TDD repair on the same four-file allowlist.

## Round-2 repair TDD evidence

### Round-2 RED (focused new tests only)

Added six fail-closed tests plus one over-strictness guard and one static
guard. Ran the six fail-closed tests against the pre-fix implementation:

`pytest tests/llamaindex_runtime/entity/test_segmenter.py -q -k "non_whitespace or token_count_zero"`

Result (genuine RED — all six `DID NOT RAISE`, the fail-open):
```
6 failed, 74 deselected in 2.75s
FAILED test_segment_token_count_zero_requires_whitespace_only_text
FAILED test_empty_offsets_for_non_whitespace_text_fails_closed
FAILED test_uncovered_non_whitespace_prefix_fails_closed
FAILED test_uncovered_non_whitespace_middle_gap_fails_closed
FAILED test_uncovered_non_whitespace_suffix_fails_closed
FAILED test_tokenizer_truncating_non_whitespace_tail_fails_closed
```

### Round-2 GREEN

- Added `_validate_offset_coverage(offsets, text)`: a pure single code-point
  scan of the normalized text. Every code point not covered by at least one
  validated token interval must be whitespace; otherwise `ValueError("tokenizer
  must cover every non-whitespace code point")`. Empty offsets are legitimate
  only when the entire text is whitespace, preserving the existing
  whitespace-only behavior. Uses authoritative token coordinates only — no
  `find`/`index`/substring coordinate recovery. Keeps shuffled-order
  determinism and the existing overlap policy (overlap/duplicate still rejected
  in `_validate_offsets`).
- Removed the mutable `_TOKENIZER_KWARGS` dict; the tokenizer is now invoked
  with explicit keyword arguments at the call site
  (`return_offsets_mapping=True, add_special_tokens=False, truncation=False`).
  Added static guard `test_segmenter_source_uses_immutable_explicit_tokenizer_kwargs`
  asserting `_TOKENIZER_KWARGS` is absent and the exact keyword values appear in
  source.
- Strengthened `Segment.__post_init__`: `token_count == 0` is accepted only for
  whitespace-only `Segment.text`; otherwise `ValueError`. Seven-field shape
  unchanged (validation-only change). Added direct test
  `test_segment_token_count_zero_requires_whitespace_only_text`.
- Full focused selector result: `pytest tests/llamaindex_runtime/entity/test_segmenter.py -q` => `81 passed in 1.96s` (73 prior + 8 new).

### Round-2 new tests added

1. `test_empty_offsets_for_non_whitespace_text_fails_closed` — `[]` on `"abc"` fails closed.
2. `test_uncovered_non_whitespace_prefix_fails_closed` — `[(2, 3)]` on `"abc"` fails closed.
3. `test_uncovered_non_whitespace_middle_gap_fails_closed` — `[(0, 1), (2, 3)]` on `"abc"` fails closed.
4. `test_uncovered_non_whitespace_suffix_fails_closed` — `[(0, 1)]` on `"abc"` fails closed.
5. `test_tokenizer_truncating_non_whitespace_tail_fails_closed` — `[(0, 5)]` on `"hello world"` fails closed.
6. `test_whitespace_gaps_and_edges_remain_allowed` — leading `" abc"`, trailing `"abc "`, and middle-gap `"a b"` remain legal (over-strictness guard).
7. `test_segment_token_count_zero_requires_whitespace_only_text` — zero-token `Segment` requires whitespace-only text.
8. `test_segmenter_source_uses_immutable_explicit_tokenizer_kwargs` — static guard pinning explicit kwargs and absence of `_TOKENIZER_KWARGS`.

### Round-2 regression + coverage

- Full entity directory regression:
  `pytest tests/llamaindex_runtime/entity -q` => `171 passed in 2.00s` (was 163 after Round 1; +8 new tests).
- Focused branch coverage:
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py --cov=llamaindex_runtime.entity.segmenter --cov-branch --cov-report=term-missing -q`
  => `81 passed`; **99% statements (118/119), 99% branches (74/75 partial)**.
  The single uncovered line (212) is the defensive `raise` in
  `_verify_exact_coverage`, structurally unreachable through the public API
  (validated offset coverage always yields boundaries starting at 0 and ending
  at `len(text)`).
- Static source guards re-verified: no `str.find`/`.find(`/`str.index`/
  `.index(`/`split_max_length`/`_TOKENIZER_KWARGS`, and no
  modelscope/torch/transformers/tokenizers/sentencepiece/jieba imports in
  `segmenter.py`; fresh-process heavy-import boundary still passes.

## Final tokenizer call contract (unchanged, now explicit at call site)

```
tokenizer(text, return_offsets_mapping=True, add_special_tokens=False, truncation=False)
```

- The exact keyword values are pinned inline at the call site (immutable, not a
  mutable module-level dict).
- Offset-coverage invariant added: every non-whitespace code point is covered by
  at least one validated token interval; empty offsets are legal only for
  all-whitespace text. This closes the silent-truncation fail-open.
- All prior fail-closed guards remain: non-callable tokenizer; `is_fast is
  False` (slow tokenizer, rejected before invocation); missing `offset_mapping`;
  malformed / out-of-range / zero-length / overlapping offsets; `max_tokens <= 0`;
  empty `segmentation_version`; empty `normalized_text`; `token_count == 0`
  requires whitespace-only text; `len(text) != end - start` rejected.
- The injected boundary stays pure: no transformers/tokenizers import, no
  network, no model. 16-06 typed errors were not introduced.

## Round-2 boundaries confirmed

No DB, Docker, PostgreSQL, network, model/tokenizer, ModelScope mirror, RaNER
inference, live gate, C2, commit, or push. No credential-bearing environment
variables read/printed/logged/persisted; every Bash command unset the guard env
vars in-process and was prefixed with `rtk`. Only the original four-file
allowlist was touched.

---
*Phase: 16-raw-corpus-entity-layer*
*Plan: 05*
*Completed: 2026-08-07*
*Coordinator hardening appended: 2026-08-07 (Round 1: tokenizer call contract; Round 2: offset-coverage fail-open + immutable kwargs)*
*Round 3 appended: 2026-08-07 (behavior-preserving test-maintainability refactor)*

---

# Round-3 Behavior-Preserving Test-Maintainability Refactor (appended after Round 2)

## Trigger

`tests/llamaindex_runtime/entity/test_segmenter.py` had grown to **1184 physical
lines**, violating the project hard rule that source files stay under 800 lines.
The plan requires the test artifact to remain `test_segmenter.py`, so the
refactor consolidated within that single file. This was a REFACTOR-only pass:
production behavior was not changed unless a test-compaction issue exposed a
real defect (exactly one such defect was found and is documented below).

All Round-1 / Round-2 RED-GREEN-hardening history above is preserved truthfully
as recorded; this section documents the Round-3 compaction.

## Refactor techniques applied (no behavior weakened, no coverage deleted)

1. **Shared `_segment` call helper** — `_segment(text=None, *, max_tokens=2,
   tokenizer=_DEFAULT_TOKENIZER, segmentation_version="seg-1", span=None)` wraps
   the 5-line `segment_text(...)` invocation that ~35 test bodies repeated,
   removing ~90 duplicated lines.
2. **Shared `_assert_raises` fail-closed helper** — `_assert_raises(text,
   offsets, match, *, max_tokens=2)` collapses the repeated
   `with pytest.raises(...): _segment(..., tokenizer=_FixedTokenizer(offsets))`
   pattern.
3. **Consolidated fake tokenizers** — the four structurally-identical fakes now
   share `_FastTokenizer` (keyword-only contract enforced once in
   `_require_fast_kwargs`); each subclass implements only `_offsets_for(text)`.
4. **Parametrized structurally-identical invalid-input tests** — Segment field
   validation (9 cases), text-length mismatch (2), repeated-text coordinates
   (2), max_tokens (9), segmentation_version (5), non-callable tokenizer (4),
   tokenizer-output-without-offsets (2), offset-mapping-not-a-sequence (4),
   malformed offset entries (6), malformed/out-of-range/zero-length/reversed/
   overlapping/duplicate offsets (7), uncovered non-whitespace coverage (5),
   and whitespace gaps/edges (3) are all data-driven.
5. **Removed repetitive section-banner comments and module docstring** — the
   10 section banners and the long module docstring were replaced by terse
   prose and the parametrization decorators; contract intent is carried by the
   test names, inline comments, and helper docstrings.
6. **Merged adjacent single-assertion tests** — e.g. the two repeated-text
   tests and the three uncovered-prefix/middle/suffix tests became
   parametrized cases of one test each.

## Defect exposed by the refactor (fixed in the test helper, not production)

The compaction of the tokenizer non-callable case into `_segment(tokenizer=bad)`
initially used `None` as the helper's "use default" sentinel. Because `None` is
itself one of the required invalid tokenizer values (production
`_validate_tokenizer` must reject it), `_segment(tokenizer=None)` silently
swallowed it and substituted the default char tokenizer — a real refactor
defect (one focused test failed: `test_tokenizer_non_callable_fails_closed[None]`
with `DID NOT RAISE`). Fixed by introducing a module-level sentinel
`_DEFAULT_TOKENIZER = object()` so the helper distinguishes "argument omitted"
from `tokenizer=None`; `None` now flows through to `segment_text` and fails
closed exactly as before. This was a test-helper fix only — production
`segmenter.py` was not modified during Round 3.

## Round-3 evidence

- Physical line counts (project hard rule is <=800 physical lines):
  - `tests/llamaindex_runtime/entity/test_segmenter.py`: **1184 -> 727** (-457 lines, -38.6%)
  - `llamaindex_runtime/entity/segmenter.py`: 265 (unchanged, <=800)
  - `llamaindex_runtime/entity/__init__.py`: 55 (unchanged, <=800)
- Focused selector: `pytest tests/llamaindex_runtime/entity/test_segmenter.py -q`
  => **92 passed in 1.70s** (parametrization expanded 81 test cases to 92; all
  original contracts present).
- Full entity regression: `pytest tests/llamaindex_runtime/entity -q`
  => **182 passed in 1.94s** (was 171 before Round 3; +11 from expanded cases).
- Focused branch coverage:
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py --cov=llamaindex_runtime.entity.segmenter --cov-branch --cov-report=term-missing -q`
  => **92 passed**; **99% statements (119 stmts, 1 miss), 99% branches (74
  branches, 1 partial)** — identical to the Round-2 result. The single
  uncovered line (212) remains the structurally-unreachable defensive `raise`
  in `_verify_exact_coverage`.

## Substantive contracts preserved (all verified by the 92 passing cases)

Public keyword-only signature; frozen seven-field `Segment` shape; Segment
validation (empty ids, non-int coordinates, bool-as-int rejection,
`0 <= start < end`, non-empty text, `end - start == len(text)`, non-empty
version, non-negative `token_count`, `token_count == 0` requires whitespace-only
text); exact canonical `segment_id`; short/long segmentation; full-span
coverage/adjacency; token budgets; determinism including shuffled-offset
equivalence; Unicode code-point safety (astral + combining, no surrogate
split); repeated-text non-recovery; whitespace handling (leading/trailing/
inter-token preserved, preceding-segment attachment, whitespace-only -> single
zero-token segment); all fail-closed budget/version/span/tokenizer/offset
cases; the explicit fast-tokenizer kwargs; slow-tokenizer rejection before
invocation; special zero-length offsets; full non-whitespace coverage and
truncation protection; forbidden-API/import static guards; facade exports; and
in-process + fresh-subprocess heavy-import boundaries.

## Round-3 boundaries confirmed

No DB, Docker, PostgreSQL, network, model/tokenizer, ModelScope mirror, RaNER
inference, live gate, C2, commit, or push. No credential-bearing environment
variables read/printed/logged/persisted; every Bash command unset the guard env
vars in-process and was prefixed with `rtk`. Only the original four-file
allowlist was touched (`test_segmenter.py` refactored; `segmenter.py` and
`__init__.py` untouched; this SUMMARY updated). Production behavior of
`segment_text`/`Segment` is byte-for-byte unchanged from the Round-2 state.

---

# Final Coordinator Acceptance

Phase 16-05 is accepted as **stable** on the basis of fresh coordinator
verification run independently after the Round-3 refactor and the Round-1 /
Round-2 hardening:

## Fresh coordinator evidence

- Focused selector: `pytest tests/llamaindex_runtime/entity/test_segmenter.py -q`
  => **92 passed in 1.52s**.
- Full entity regression: `pytest tests/llamaindex_runtime/entity -q`
  => **182 passed in 1.77s**.
- Focused branch coverage:
  `pytest tests/llamaindex_runtime/entity/test_segmenter.py --cov=llamaindex_runtime.entity.segmenter --cov-branch --cov-report=term-missing -q`
  => **119 statements / 1 miss, 74 branches / 1 partial, 99%**; the single
  uncovered defensive line is **line 212** (`_verify_exact_coverage`), which is
  structurally unreachable through the public API.
- File hygiene (physical lines): `segmenter.py` 265, `entity/__init__.py` 55,
  `test_segmenter.py` 727, `16-05-SUMMARY.md` 444 before this append; all
  allowlist files remain at or below the 800-line hard rule, with zero trailing
  whitespace and a final newline.

## Combined review verdict

One combined Sonnet review: **APPROVE** with **0 CRITICAL, 0 HIGH, 0 MEDIUM**,
and **4 optional LOW** findings. **No implementation change was required**; no
code or test content changed after that single review. The four optional LOW
categories are recorded for awareness (not claimed as fixed):

1. Runtime proof omits `transformers`/`tokenizers` imports although the static
   source guard and transitive-import review are clean.
2. No direct invalid-value case for `Segment.end`; the shared coordinate-validation
   branch is exercised through `Segment.start` cases.
3. Duration wording was corrected by this documentation edit (the frontmatter
   `duration` field no longer implies the whole effort took 25 minutes).
4. Tokenizer exceptions propagate out of `segment_text` and fail closed (by
   design; documented, not wrapped).

## Boundaries preserved

Blocked / not executed throughout: DB, Docker, PostgreSQL, network, model/
tokenizer, ModelScope mirror, RaNER inference, live gate, C2, commit, and push.
No credential-bearing environment variables were read, printed, logged, or
persisted; every Bash command unset the guard env vars in-process and was
prefixed with `rtk`. Only the four-file allowlist was touched.
