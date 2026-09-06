# 16-16 SUMMARY — local conservative coref rules (tdd-graph executed)

status: COMPLETE (delivered via tdd-graph pipeline; engine-level candidate failure documented; coordinator-landed + fresh-verified)

## Deliverables (in main repo, untracked as house convention, NO commit)
- llamaindex_runtime/entity/coref_rules.py (NEW, 230 lines): pure stdlib-only; frozen CorefCluster (5 exact fields), frozen CorefClusterSet.tombstone (new set, KeyError on unknown, originals untouched); build_coref_clusters(resolved, *, coref_rules_version, resolver_mode=None): exact 'rules' gate (default off), span_id member identity, duplicate-span ValueError, (document_id, version_id, mention_text, entity_type) grouping with >=2 members, cluster_id = deterministic_id('coref_cluster', canonical_json(...)), provenance {'coref_rules_version','strategy':'local_lexical_structural'} only, sorted/deterministic.
- llamaindex_runtime/entity/__init__.py: additive exports (import block + __all__ += CorefCluster/CorefClusterSet/build_coref_clusters); diff vs repo base purely additive (31 diff lines).
- tests/llamaindex_runtime/entity/test_coref_rules.py: canonical wave tests (planner-authored; blob e687246fc81d59c3619b0a817c95767239c1d901 proven unchanged by writer; post-landing hygiene: black reformat + ruff F401 unused-import removal — assertion behavior unchanged, selector 23/23 before and after).

## TDD evidence (writer child agent c08d8b88, engine workspace)
- RED stub: 21 failed / 2 passed; GREEN: 23/23; REFACTOR (extracted _collect_member_groups / _clusters_from_groups): 23/23; same selector throughout; test assertions untouched by writer (git blob equality proven).
- Manual mutation testing (mutation tool unavailable): gate inversion -> 14 failed; duplicate-span check disabled -> exactly test_duplicate_member_identity_fails_closed; _MIN_CLUSTER_MEMBERS 2->1 -> exactly the 5 never-cluster tests. Restored + hash-verified after each.
- Zero-new-failure parity vs base; GitNexus: new leaf symbol, zero upstream callers; only pre-indexed symbol touched = entity __init__ (additive).

## Engine run record (honest)
- tdd_graph compile: ok, nodes=9, edges=29, warnings=[] (notes/graph-body.json persisted)
- run-e9v7v20g: prepare SUCCEEDED / workspace SUCCEEDED / writer SUCCEEDED / candidate FAILED_FATAL / test,reviewer,mutation,certificate,merge BLOCKED
- candidate receipt outcome=failed args={} ; workspace redProof: 'canonical tests digest verification failed' — Windows checkout CRLF vs raw sha256 materialization artifact (marked non-blocking at workspace, fatal at candidate). resume (bound, signaled 0) and graph_recover (0) exhausted; no retry primitive for FAILED_FATAL in engine tools.
- Coordinator landing: worktree deliverables copied byte-identical (sha12 coref b29d7bead5ec; test 802c519a3da0 = prepare manifest entry; __init__ d34f19f3a086). Dependency materialization copies skipped (already exist in main repo).

## Fresh coordinator verification (main repo, 2026-08-31)
- selector tests/llamaindex_runtime/entity/test_coref_rules.py: 23 passed (x3 runs incl. after hygiene)
- entity suite: 740 passed / 3 failed / 1 skipped — the 3 failures are PRE-EXISTING host-state artifacts: tests assert absence of verification/phase16-raw-corpus-entity-layer/raner_mirror_manifest.json which exists as a legitimate artifact of earlier authorized mirror work (raner_mirror_builder x2 + modelscope_downloader x1); unrelated to coref (import health proven by 740 passing incl. resolution/merger suites)
- gate3 suite: 600 passed / 4 skipped (unchanged from pre-16-16 baseline; frozen gate3 untouched)
- black/ruff/mypy: clean on the three touched files (black 1-file reformat of canonical tests + ruff F401 fix applied post-landing; coref_rules.py and __init__ unchanged-clean; mypy Success on coref_rules.py --follow-imports=skip)

## Constraints compliance
- No Docker/PostgreSQL/external DB/network/model download/RaNER inference/live gate/C2/commit/push. No gate3 module touched. Engine worktrees retained as-is under .tdd-graph-worktrees/ and .claude/worktrees/ (infra cleanup = separate follow-up).

## Follow-ups
- ENGINE (infra, non-code): tdd-graph candidate node performs raw-sha256 materialization verification of canonical tests; fails on Windows CRLF checkout normalization. Record for the tdd-graph toolchain, not for this repo's code.
- Optional: sweep pre-existing 3 host-state mirror tests into a fail-closed path tolerant of legitimate existing artifacts (separate decision; tests untouched this cycle).
