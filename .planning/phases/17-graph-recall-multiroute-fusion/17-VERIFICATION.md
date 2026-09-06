# Phase 17 verification — 17-VER (2026-09-04)

## 1. What Phase 17 delivered

Phase 17 (graph-recall multiroute fusion) shipped a UIE-first entity/relation
extraction pipeline over the OKF rebuild corpus, a LightRAG-backed knowledge
graph backend with a loop-bound live gate, a dual-route (graph + BM25 titles)
recall path merged by reciprocal-rank fusion, a live acceptance runner
(`run_graph_recall_acceptance.py`), and a dual-batch demo
(`run_phase17_demo.py`) that exercises the same seams end to end. Both entry
points share one bridge module (`live_bridge.py`, extracted in W5a) and were
executed live on 2026-09-03 in the deepseek-v4-flash era.

## 2. Live gate + demo (both executed, deepseek-v4-flash era)

| Artifact | Status | sha256 (256-bit hex, first 16) | Size |
| --- | --- | --- | --- |
| graph_recall_acceptance_evidence.md (live gate) | executed, exit 0, route PURE_UIE, recall_hit_count 3, ingest_entities 8 | 853bb353db2ee566 | 415 B |
| phase17_demo_report.md (live demo) | executed x2 batches (similar, mixed), both route PURE_UIE | c2ae8ea3bede7ff9 | 538 B |

The live gate evidence is a single-line JSON record with exactly 19 keys; the
demo report contains two batches (`## batch: similar`, `## batch: mixed`), each
with `status: executed` and `route: PURE_UIE`.

## 3. Archive chain

| Generation | Gate sha256 (first 16) | Demo sha256 (first 16) | Note |
| --- | --- | --- | --- |
| First run (executed_2026-09-03, pre_fix17 copies) | 20a4de975fbac845 | 9ea91f0d7406e5a7 | byte-identical pairs |
| FIX-17 rerun (live + executed_deepseek_2026-09-03) | 853bb353db2ee566 | c2ae8ea3bede7ff9 | current live artifacts |
| llm500 honest-failure record | cda8790aab4bdeaa | n/a | {"error_type":"ValueError","exit_code":3,"status":"executed_failed"} |

## 4. Explicit non-claims

- The LLM-primary extraction route was NEVER exercised live: both demo batches
  routed PURE_UIE because the trial gate decided so; the llm branch exists and
  is tested, but no live run exercised it.
- BM25 ran single-route RRF only: `bm25_titles` was empty in the live runs, so
  the fusion consumed graph hits alone; no cross-route RRF benefit was measured.
- The `invariants` key is ABSENT from the archived gate evidence: the runner
  gained the invariants block in W5c, after the live runs happened. Archived
  evidence therefore predates that instrumentation and must not be quoted as
  if it carried invariants.
- Debt wave W5a/W5b/W5c closed 2026-09-04 with 8 of 13 follow-ups closed;
  F11 (live re-run of the demo llm branch), F12, F4-live, and F14-residual
  remain recorded as open items requiring live infrastructure.

## 5. How to re-verify

From the repository root (no DB, no model, no network needed):

    python verification/phase17-graph-recall-multiroute-fusion/run_phase17_verification.py

Exit 0 means every check passed and `phase17_verification_evidence.md` was
(re)written into the verification directory; exit 3 is fail-closed with
`verification_status: verification_failed`. The verifier consumes on-disk
artifacts only: it never re-runs live gates and never fabricates evidence.
