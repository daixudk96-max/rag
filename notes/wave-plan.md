# Wave plan - self-check (tdd-graph-plan flow, manual gate execution)

Note: the skill's step-gate launcher (run.cmd / .step-gate) does not exist in this
environment (searched user/.dsh/.claude/skills and dsh tree). The gate protocol
(status/next/complete) is therefore not executable; we follow the skill's
functional pipeline manually and record each artifact honestly:
notes/wave-plan.md -> notes/requirements.md -> compile -> handoff.

## Self-check (four questions)
1. Is this tdd-graph suited here? YES - 16-16 is a pure, deterministic, local TDD
   unit task (coref rules), exactly the graph's shape; no DB/model/network/live gate.
2. One wave or many? ONE wave (16-16-coref-rules): tests-first authoring, single
   module + package export change. 16-15 is NOT included (blocked: PostgreSQL
   authorization + skipped 16-13 live dependency - user decision 2026-08-31).
3. Source of truth? .planning/phases/16-raw-corpus-entity-layer/16-16-PLAN.md
   (interfaces from llamaindex_runtime/entity/contracts.py + resolution.py;
   fixture pattern mirrors tests/llamaindex_runtime/entity/test_resolution.py).
4. Constraints? Pure stdlib, no DB/model/network/persistence, frozen gate3
   untouched, default-off resolver gate, no canonical merge, no model values,
   tests assertions immutable between RED/GREEN/REFACTOR.

## Gate absence record
- 'C:/Users/daixu/.claude/skills/tdd-graph-plan/scripts/run.cmd' -> False
- 'E:/github/rag/.claude/skills/tdd-graph-plan/scripts/run.cmd' -> False
- No .step-gate in repo; no run.cmd/flow.yaml anywhere found under
  C:/Users/daixu/.dsh or E:/github/dsh. Step-gate is unavailable (environment).
- Consequence: chain mirror/step receipts cannot be produced. Proceeding with
  the skill's substance (collect -> compile -> handoff) is the operator-visible
  equivalent; any rework loop is done through compile failures (fail-closed).
