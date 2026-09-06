# Phase 16-03 SUMMARY — Deterministic, Versioned In-Memory Candidate Merger

**Status:** COMPLETE (TDD RED -> GREEN -> REFACTOR + facade/import regression)
**Date:** 2026-08-06
**Plan:** `.planning/phases/16-raw-corpus-entity-layer/16-03-PLAN.md`
**Selector (identical for RED / GREEN / REFACTOR runs):**
`rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_merger.py -q`

> Note on verification tooling: the selector above is the plan's exact automated
> command. rtk's compact pytest wrapper reports an aggregate summary line
> (e.g. "Pytest: No tests collected" for both error collections and passing
> runs) and only persists a detailed log when the run FAILS. To record exact
> pass counts and timings, the same command's body was also executed via
> `rtk proxy ... python -m pytest tests/llamaindex_runtime/entity/test_merger.py -q`
> (raw passthrough of the identical selector semantics). This is a measurement
> detail, not a behavior change.

## TDD Evidence

| Stage | Result | Detail |
|---|---|---|
| **RED** | 1 collection error (FAIL) | `ImportError: cannot import name 'CandidateOutcome' from 'llamaindex_runtime.entity'` at `tests\llamaindex_runtime\entity\test_merger.py:29`. `llamaindex_runtime/entity/merger.py` did not exist yet; only the test file was written. **No implementation file existed in this stage.** 1.92s. |
| **GREEN** | 37 passed | Minimal implementation of `llamaindex_runtime/entity/merger.py` + facade append in `__init__.py`. 1.16s. |
| **REFACTOR** | 37 passed | Behavior-preserving cleanup only: extracted `_ordered_occurrences`, `_sweep_scope`, `_make_outcome` helpers; introduced `OccurrenceKey`/`SelectedEntry` type aliases; removed a placeholder-scope init block; docstring polish. **Test assertions unchanged between GREEN and REFACTOR.** 1.26s. |

Coverage on `llamaindex_runtime/entity/merger.py`: `Stmts 108, Miss 1, Cover 99%`. The single uncovered line is the defensive chained-displacement orphan fallback inside `_attribute_loser` (a pathological case where a winner was itself later displaced, so a losing candidate no longer overlaps any final winner; it still attributes deterministically to the scope's first retained winner).

### Test-data correction between RED and GREEN (transparent)

Between the RED capture and the GREEN run, three test cases in `test_merger.py` were
corrected because they contained test-data errors, not merger bugs:

1. `test_strict_containment_loser_nested` / `test_strict_containment_container_wins_on_priority`
   used `mention_text="猫猫今天开"` with `char_start=0, char_end=6`, but
   `_NORMALIZED[0:6] == "猫猫今天开会"` (6 code points), violating the frozen
   slice-back invariant `normalized_text[char_start:char_end] == mention_text`
   in `MentionCandidate.__post_init__` (16-02). Fixed the fixture text to
   `"猫猫今天开会"`. This is a fixture-data fix, not a behavior change.
2. `test_importing_entity_package_imports_no_heavy_dependencies` asserted
   `psycopg not in sys.modules`. `psycopg` is imported by the project's
   `conftest.py` during collection (it is a declared dependency of the package,
   unrelated to the entity layer), so the assertion was over-strict and not a
   property of `llamaindex_runtime.entity`. The frozen heavy-import boundary is
   `modelscope`/`torch`/`jieba` only (matching `test_contracts.py`); the test
   was narrowed to that boundary.

These corrections happened during test authoring, before the GREEN selector
passed; they changed no merger behavior and the test file was frozen unchanged
between GREEN and REFACTOR.

## Facade / Import Regression (Phase D)

`rtk proxy rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED python -m pytest tests/llamaindex_runtime/entity/test_contracts.py -q`

- **Result: 45 passed, 1.27s.** The 16-02 contract suite still passes after the
  facade extension (append-only `__init__.py`); `test_importing_entity_package_imports_no_heavy_dependencies`
  confirms no `modelscope`/`torch`/`jieba` import leaks.
- Combined entity directory (`tests/llamaindex_runtime/entity/`): **82 passed, 1.40s** (37 merger + 45 contracts).

## Changed Paths (plan-16-03 scope only)

- `llamaindex_runtime/entity/merger.py` (new) — deterministic versioned in-memory merger.
- `llamaindex_runtime/entity/__init__.py` (edited) — append-only facade extension exporting `merge_mentions`, `MergedMentions`, `CandidateOutcome`, `OutcomeStatus`, `OUTCOME_STATUSES`; all 16-02 exports preserved unchanged.
- `tests/llamaindex_runtime/entity/test_merger.py` (new) — 37 RED/GREEN/REFACTOR tests.
- `.planning/phases/16-raw-corpus-entity-layer/16-03-SUMMARY.md` (this file).

No other file was modified. No plan, config, dependency, migration, adapter,
repository, runner, or Wave 0 file was touched. This statement is
scope-relative to this plan's own work.

## Public API Summary

- `merge_mentions(raw_candidates: Sequence[MentionCandidate], *, merger_version: str) -> MergedMentions`
  — pure, deterministic, versioned. Rejects empty/non-str `merger_version`
  (`ValueError: merger_version must be a non-empty string`) and rejects any
  non-`MentionCandidate` entry with the offending index. Never mutates or
  reorders the caller's sequence (test pins identity of original elements).
- `MergedMentions` (frozen) — `selected: tuple[MentionCandidate, ...]`,
  `outcomes: Mapping[OccurrenceKey, CandidateOutcome]`, `merger_version: str`.
  `outcomes` is a `MappingProxyType` covering EVERY occurrence (one entry per
  occurrence, including identical duplicate occurrences). The type exposes no
  save/write/insert/upsert/delete/commit/repository/connection/cursor/DML
  method.
- `CandidateOutcome` (frozen) — `status: OutcomeStatus`, `reason: str`
  (non-empty for every non-selected outcome, `""` for selected),
  `occurrence_key: OccurrenceKey`, `winner_occurrence_key: OccurrenceKey | None`.
- `OutcomeStatus` Literal + `OUTCOME_STATUSES` frozenset — exactly
  `{"selected", "duplicate", "grouped", "suppressed", "nested", "overlap"}`.
- `OccurrenceKey = tuple[object, ...]` — deterministic per-occurrence identity:
  `(normalized_full_candidate_sort_key, global_ordinal)`. Identical duplicate
  occurrences are safely distinguished by the ordinal.

## Frozen Semantics Delivered

- **Source-kind priority (never numeric cross-kind confidence):**
  `frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`.
  Only `confidence_kind` participates in ranking; `confidence` numeric values
  are never compared across kinds (the sort key places `confidence_kind` before
  `confidence`). `unavailable` is retainable: it is selected whenever it does
  not lose an actual interval conflict, and loses only to a higher-priority
  candidate on a real overlap (tested both ways).
- **Classification:** identical full-candidate-value occurrences → first
  deterministic occurrence `selected`, later `duplicate`; same exact interval +
  same canonical_label/entity_type with differing provenance → winner `selected`,
  loser `grouped`; same exact interval + incompatible canonical_label/entity_type
  → loser `suppressed`; strict containment (either direction) → loser `nested`;
  partial overlap → loser `overlap`; disjoint intervals → each `selected`.
  Every non-selected outcome has a non-empty deterministic `reason` and a
  `winner_occurrence_key` referencing a retained `selected` occurrence.
- **Scope isolation:** candidates are resolved independently per
  `(input_kind, input_id, input_revision, segment_id)`; nothing is ever merged
  across inputs, revisions, or segments (tested for distinct inputs and distinct
  segments/revisions).
- **Determinism:** stable total order = (normalized sort key incl. canonical
  projection fingerprint, original position). Shuffled input is
  byte-equivalent (`test_shuffle_determinism_byte_equivalent` runs 5 shuffled
  seeds against a canonical JSON fingerprint; `test_selected_values_are_stable_under_input_permutation`
  and `test_result_reconstructable_from_raw_candidates_and_version` pin forward/
  reverse and list/tuple equivalence).
- **Query-origin:** `input_kind == "query_text"` candidates flow through the same
  pure request-scoped `MergedMentions`; tests assert the result and both DTOs
  expose none of the persistence-method names, and `query_text` never carries a
  document/sidecar projection by construction (16-02 contract).

## Boundary Compliance

- **No heavy imports:** `merger.py` imports only the stdlib plus
  `.contracts`. The facade/import regression re-verifies `modelscope`, `torch`,
  `jieba` are absent from `sys.modules` after importing `llamaindex_runtime.entity`.
- **No live/model/DB/network/persistence:** the merger is pure in-memory; the
  module and its results expose no DML/repository/connection/cursor surface.
  The selector unset all listed DB/authorization variables via `env -u`;
  nothing was read, printed, or persisted. No Docker, PostgreSQL, network,
  model mirror, package install, or C2 entry was used.
- **No durable candidate audit:** per D2, all candidate state lives in memory;
  no tables, merge-log writes, or any persistence artifact are created.

## Design Notes

- Identical duplicate occurrences are represented safely by an occurrence key
  that pairs the full normalized candidate value with a deterministic global
  ordinal, so `outcomes` is a genuine per-occurrence (not per-value) map.
- The plan's "sort by (input_id, span_id, char_start, char_end, source)" sketch
  is realized as a full normalized sort key that additionally includes
  `confidence_kind`/`source`/`extractor`/model provenance and the canonical
  projection fingerprint, making selection value-injective and byte-deterministic
  under shuffle; the plan's exact-field sketch was not sufficient for
  byte-identical shuffle reconstruction.
- A single defensive fallback covers chained displacement (a winner later
  displaced by a higher-priority candidate) so every non-selected outcome still
  references a retained winner; it is the only uncovered line (99% coverage).

## Status Scope

This summary documents plan 16-03 only (pure in-memory merger). It does **not**
claim Phase 16 completion, any live/model/DB execution, adapter/repository
readiness, or the separately-authorized resolver (D3) that later consumes the
merged selected set.

## Blockers

None. No external service, model download, package installation, git
operation, or credential access was required or performed.

---

## Phase 16-03 REPAIR — No Orphan Attribution + Non-Numeric Same-Kind Tie-Break (2026-08-06)

**Reason:** a stable-delta Sonnet review of the delivered merger found two defects in the
original selection/attribution logic. This appended repair section **supersedes** the parts of
the original Design Notes, the 99% coverage claim, and the pre-repair "Frozen Semantics
Delivered"/selection descriptions that described displace-on-higher-priority selection and the
defensive orphan fallback. The original historical evidence above is preserved unchanged.

### Defects corrected

1. **HIGH — orphan overlap attribution (chained displacement).** The original sweep displaced a
   retained winner whenever a higher-priority candidate overlapped it. A loser attributed earlier
   could then be classified against a final retained winner it no longer overlaps. Example:
   dictionary [0,10), model [2,4), frontmatter [8,11): model first lost nested to dictionary,
   dictionary later lost to frontmatter, and model was falsely classified `overlap` against the
   disjoint frontmatter [8,11).
2. **MEDIUM (upgraded to required by frozen D3) — numeric same-kind ordering.** The original
   `_candidate_sort_key` placed the raw numeric `confidence` field directly in the sort tuple, so
   within an equal `confidence_kind` a lower numeric score (e.g. 0.5) ranked above a higher one
   (0.9). Phase 16 frozen D3 states the ladder is explicitly non-numeric and conflicts must never
   be ordered by a numeric score.

### Corrected selection algorithm

- Candidates are processed in deterministic **winner-rank order** — the total
  structural order `(D3 confidence-kind priority, SHA-256 structural digest,
  canonical candidate payload)`.
- A candidate is **accepted only when it overlaps no already-retained winner**; there is **no later
  displacement**, so the retained set is monotonic.
- Because a candidate is rejected only when it overlaps an already-retained winner, and that winner
  is never removed, **every rejected occurrence provably has a real retained overlapping winner** —
  no outcome can reference a disjoint winner (orphan eliminated).
- Each loser is attributed to the **highest-ranked overlapping retained winner** (min winner-rank
  key). Classification is unchanged: exact duplicate -> `duplicate`; same interval compatible ->
  `grouped`; same interval incompatible -> `suppressed`; strict containment -> `nested`; partial
  overlap -> `overlap`. Six outcomes preserved; no seventh status added.

### Non-numeric same-kind tie-break (pinned, total structural order)

- For equal `confidence_kind`, the winner rank is the **SHA-256 digest of the OKF canonical JSON of
  the complete candidate representation** (all scalar fields in frozen order + the projection
  mapping; `json.dumps` with `sort_keys=True`, compact separators, `ensure_ascii=False`).
- The raw numeric `confidence` is included **only as opaque data** inside that canonical
  serialization; it is **never compared as a magnitude** and never used ascending/descending as a
  score.
- The winner-rank key is a **true deterministic total structural order**
  `(priority, sha256_digest, canonical_candidate_payload)`. The canonical payload is the pure
  collision fallback for **DISTINCT values**: two distinct candidates always rank deterministically
  even on a SHA-256 digest collision. Payload equality is exactly full candidate equality.
- Duplicate detection uses **exact canonical payload equality** (== full candidate equality), never
  rank-key equality, so a digest collision between distinct values can never mislabel them
  `duplicate`.
- A **stable global occurrence ordinal** distinguishes only **truly identical duplicate
  occurrences** (equal canonical payloads / equal rank keys). It is **NOT** the fallback for
  distinct digest collisions.
- The rule is pinned by `test_candidate_fingerprint_tie_break_rule_is_pinned`: the base
  `_mention()` candidate must digest to
  `b29f1d6de55565583a6ef3e1f540d51e50e93c81bc209fa6b4ce8fa1cd5e7574`, and same-kind pairs are
  ranked by fingerprint.
- Two fixed same-kind pairs assert **opposite numeric directions** (so any always-higher or
  always-lower numeric comparator fails at least one pair):
  `test_same_kind_pairs_with_opposite_numeric_directions_follow_structural_rank` uses pair A
  (confidence 0.1 vs 0.2, **higher** 0.2 wins by fingerprint `09469724…` < `bd6eca7c…`) and pair B
  (confidence 0.1 vs 0.5, **lower** 0.1 wins by fingerprint `bd6eca7c…` < `f8dc500b…`).
- A controlled SHA-256 digest collision (monkeypatched constant digest) proves the payload fallback:
  `test_distinct_values_with_digest_collision_still_rank_by_payload` (distinct values keep distinct
  rank keys and are never `duplicate`, shuffle byte identity preserved) and
  `test_identical_duplicates_still_detected_under_digest_collision` (truly identical values are
  still `selected` + `duplicate`).

### TDD evidence (repair)

| Stage | Command | Result |
|---|---|---|
| **RED** | `rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_merger.py -q` | **3 failed, 39 passed (2.21s)**. Failures: `test_chained_displacement_loser_never_orphan_to_disjoint_winner` (`assert 1 == 2` — old sweep selected only 1; model [2,4) orphaned), `test_every_non_selected_outcome_references_real_overlapping_winner` (disjoint/orphan winner reference), `test_same_kind_confidence_values_are_not_ordered_numerically` (`assert hi in result.selected` — old code selected the 0.1 lower-confidence candidate). |
| **GREEN** | same selector | **42 passed (1.35s)**. Implemented winner-rank accept-only-if-no-overlap selection, non-numeric fingerprint tie-break, orphan fallback removed. |
| **REFACTOR** | same selector | **42 passed (1.23s)**. Behavior-preserving cleanup only: removed the now-dead `_priority` helper; clarified the winner-rank invariant docstring. **Test assertions unchanged between GREEN and REFACTOR.** |
| Contracts regression | `rtk env -u … pytest tests/llamaindex_runtime/entity/test_contracts.py -q` | **45 passed (1.62s)**. |
| Combined entity dir | `rtk env -u … pytest tests/llamaindex_runtime/entity/ -q` | Pre-hardening **87 passed (1.15s)** (42 merger + 45 contracts); post-hardening final **90 passed (1.88s)** (45 merger + 45 contracts). |
| Coverage | `rtk env -u … pytest tests/llamaindex_runtime/entity/test_merger.py --cov=llamaindex_runtime.entity.merger --cov-report=term-missing -q` | Pre-hardening **merger.py 96 stmts, 0 miss, 100%** (was 108 stmts, 1 miss, 99%); post-hardening final **98 stmts, 0 miss, 100%**. The previously uncovered orphan fallback is gone. |
| **HARDEN RED** (controlled digest-collision gap) | same selector with production temporarily reverted to `(priority, digest)` rank + rank-key duplicate detection | **4 failed, 41 passed (2.60s)**. The hardening discriminator `test_distinct_values_with_digest_collision_still_rank_by_payload` failed with `assert (3, '000…') != (3, '000…')`: under a forced digest collision, old `_rank_key` collapsed distinct values to equal rank keys (would mislabel them duplicate). No real SHA-256 collision was attempted. |
| **HARDEN GREEN** | same selector | **45 passed (2.07s)**. Implemented total structural order `(priority, sha256_digest, canonical_candidate_payload)`; duplicate detection by exact canonical payload equality; two opposite-direction same-kind pairs; collision-fallback + duplicate-under-collision tests added. |

### New final counts

- Merger focused selector: **45 passed** (37 original + 8 repair tests: chained-displacement
  truthfulness, every-non-selected-winner-overlaps invariant, non-numeric same-kind behavior,
  shuffled byte-identity, pinned fingerprint rule, opposite-numeric-direction pair proof,
  digest-collision payload fallback, duplicate-under-digest-collision).
- Contracts regression: **45 passed**. Combined entity directory: **90 passed** (45 merger + 45
  contracts).
- Coverage on `llamaindex_runtime/entity/merger.py`: **100%** (98/98 statements).

### Changed paths (repair, plan-16-03 scope only)

- `llamaindex_runtime/entity/merger.py` — corrected selection/attribution per above.
- `tests/llamaindex_runtime/entity/test_merger.py` — added 8 repair tests (5 orphan/numeric +
  3 hardening) + test-local fingerprint/rank/occurrence-map helpers.
- `.planning/phases/16-raw-corpus-entity-layer/16-03-SUMMARY.md` — this appended repair section.
- `llamaindex_runtime/entity/__init__.py` — **unchanged** (the facade already exported the merger
  API; no change required).

This repair adds no durable/persistence/network/model/database behavior, keeps results and inputs
immutable, preserves per-occurrence outcome completeness and scope isolation, and does **not**
claim Phase 16 completion.
