# W7 wave-plan (tdd-graph; authored 2026-09-02)

## Self-check (four questions)
1. Can each wave's tests be expressed as standalone pytest files with fakes only? YES (runner + demo orchestrator are pure orchestration over injectable seams; real PG/LLM/UIE only in coordinator live gates).
2. Is every called API verified? Yes - see requirements.md (probed signatures this session).
3. Are frozen modules untouched by design? Yes - all new code under verification/phase17-graph-recall-multiroute-fusion/ + tests/llamaindex_runtime/phase17/.
4. Does any test need network/docker/LLM? No - gate tests assert zero-connect; demo tests use fakes.

## Waves
- wave-1 gate-runner: NEW verification/phase17-graph-recall-multiroute-fusion/run_graph_recall_acceptance.py (env gate, skipped-by-default, argv-routing-forbidden, redacted evidence, proof pipeline over injectable seams, exit codes 0/1/3).
- wave-2 demo-pipeline (dependsOn wave-1): NEW verification/phase17-graph-recall-multiroute-fusion/run_phase17_demo.py + uie_batch.py; two demo batches (similar -> PURE_UIE route A; mixed -> LLM-primary route B); per-batch report + totals; fail-closed.

## Post-graph steps (coordinator, not in graph)
1. fresh verification (focused + combined + statics + hashes).
2. ordered review chain (Spec/General/Python/Security) -> fix round if C/H.
3. LIVE gates (coordinator-executed, evidence archived): disposable PG acceptance run + dual-route demo run (real LLM trial + relation judge; real DashScope embedding; LightRAG PG storages).
4. 17-18-SUMMARY + taskboard close; then LLM unification package (user-approved A-then-unify sequencing).

## Step 4 fallback
Graph engine previously FAILED_FATAL 3x at prepare with no diagnostics (run-uofxl4t9 / run-f7fv1qct / run-sua8bq4s). If prepare dies again: switch to relay-baton mode (canonical tests + workorder already on disk; transcriber worker executes TDD). No retries beyond one resume attempt.