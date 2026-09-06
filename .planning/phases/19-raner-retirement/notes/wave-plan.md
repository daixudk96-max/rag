# Phase 19 W7 (debt): lazy heavy imports in ingestion/bundle.py — wave plan

## Authorization
- User 2026-09-04: '没问题，用这个转化成 graph 的 plan，然后直接开始用 graph 执行' (lazy-load fix via graph).

## Recon facts
- Pollution chain: tests import okf/serializer.py:23 → ingestion package __init__ (:1 'from .bundle import DoclingBundle, build_docling_bundle') → ingestion/bundle.py:9 'from docling.document_converter import DocumentConverter' + :10 'from llama_index.core import Document as LlamaDocument' (both top-level) → docling pulls torch/transformers → 9 entity zero-heavy-import guards fail in a shared pytest process.
- serializer.py:23 imports DoclingIngestor only for the static DoclingIngestor._flatten_docling_metadata (serializer.py:158); docling_ingestor.py top imports are clean (integration.py uses importlib lazy loaders).
- Bundle-stripped probe (bundle stubbed in sys.modules, then import pipeline + okf.serializer): HEAVY=[] → bundle.py is the ONLY heavy entry; bundle-only fix suffices.
- Importers of build_docling_bundle: tree/runtime.py:14, vector/runtime.py:11 (heavy-import modules where laziness is irrelevant), tests (test_docling_bundle.py:6, test_docling_ingestion.py:9, test_docling_2109_default_reader.py:40/:44). Blast radius LOW (lazy import, no signature change). GitNexus impact CLI failed ('program not found' for npx) — manual blast radius documented here instead.

## Canonical test (materialized RED)
- tests/llamaindex_runtime/okf/test_okf_lazy_heavy_import.py — 5 tests: 3 subprocess import probes (okf.serializer / ingestion package / docling_ingestor), 1 injected-fake-converter build probe (docling must stay unimported), 1 AST top-level scan of bundle.py.
- RED evidence 2026-09-04: 5 failed in 77.02s (all for the expected reasons: heavy modules present / top-level imports present).

## Fix spec
- bundle.py ONLY: typing line gains TYPE_CHECKING; top-level docling + llama_index imports deleted; TYPE_CHECKING block re-imports LlamaDocument for annotations; build_docling_bundle gains conditional lazy DocumentConverter (converter-is-None branch only) + function-level lazy LlamaDocument import.

## Execution record (2026-09-04)
- run-sx1adjcn: FAILED_FATAL — executed the STALE 16-16 body at repo-root notes/graph-body.json (my compile did not persist there; old canonical paths deleted in Phase 19). Lesson: compile does NOT write graph-body.json; persist it yourself.
- run-g9rdkpm7: FAILED_FATAL — correct body, allowTestsUpdate:false → RepoError tests-conflict (repo still held Phase 18 W4 canonical-tests ref+manifest with a different digest). Root cause found by reading lib/nodes/prepare.js + tdd-core repo.js bootstrapTests (:719-725).
- run-ysup1dx3: allowTestsUpdate:true → ALL nodes SUCCEEDED (prepare/workspace/writer/candidate/test/reviewer/mutation/certificate); merge → WAITING_SIGNAL (manual landing per W4 discipline). Writer agent f721cb25; reviewer a23c6de2 APPROVE (Gate A ac1-ac5 PASS, Gate B candidate sha d8c9fdbd, 5 mutants all caught; warnings: .claude/tdd-guard residue + candidate pytest.ini marker-drop + 7 pre-existing base collection errors).
- Landing: worktree bundle.py copied byte-exact to main repo (sha 0be7807e...); pytest.ini and .claude untouched (reviewer warnings honored).
- Post-merge remediation (2 coordinator mypy fixes, documented deviation from candidate sha): bundle.py:33 'doc_converter: DoclingConverterProtocol' annotation (:38 branch-type error), typing line +Any and 'conversion_result: Any' (:43 object.document attr error — surfaced by the new annotation, base-proven absent at 9c1922c).

## Verification plan (post-GREEN)
- New suite: 5 passed.
- okf full regression: expect 5 pre-existing failures / 3381+5=3386 passed / 31 skipped (no new failures, no count drift beyond +5).
- entity focused 966/0 unchanged.
- Joint probe: entity + new okf guard tests in ONE pytest process now pass (the original pain point).
- Canonical 6-domain combined re-run unchanged 1287/0.

## Merge resolution (2026-09-04, tdd-graph-conflict-resolution skill, 4-step gate all PASS)
- Root cause of WAITING_SIGNAL: NOT the manual-landing policy — a real cherry-pick conflict session (conflict-a0d1e477fa0e) inside merge worktree .tdd-graph-merge/run-ysup1dx3 (base a4b08ab5), because the candidate snapshot commit carried 3 files that differed from the prepare base tree: .claude/tdd-guard/data/test.json, llamaindex_runtime/__init__.py, pytest.ini (bundle.py itself cherry-picked clean).
- Resolutions: __init__.py → theirs (proved byte-identical to main repo truth, sha256 DA3559BC...; base held an engine stub marker); pytest.ini → main repo truth ([pytest]/pythonpath=./markers/integration — neither side matched main); test.json → ours (candidate runtime residue kept out, per reviewer warning). git add only, never commit; CHERRY_PICK_HEAD preserved (lives at .git/worktrees/run-ysup1dx3/, not $wt/.git).
- Index-blob verification (autocrlf lesson): worktree disk file shows CRLF so Get-FileHash mismatches are false alarms; authoritative check = git cat-file :0: → DA3559BC = candidate blob. pytest.ini index blob = main-repo content LF-normalized.
- tdd_graph resume → signaled:1 → merge LEASED → 80s → **run-ysup1dx3 status SUCCEEDED, all nodes SUCCEEDED**. integration ref CAS-moved a4b08ab5 → d50c63ea ('tdd-graph: candidate w1-lazy-heavy-imports g0'); integration tree bundle.py blob = 0BE7807E = certified candidate; conflict record auto-deleted; merge worktree auto-removed; main repo working tree untouched by the merge (bundle.py stays F1FF9D23 = candidate + 2 mypy fixes).
- Skill artifacts: notes/conflict-scene.md, notes/resolve-decision.md, notes/fix-notes.md, notes/resume-result.md (repo-root notes/, per gate workdir).
