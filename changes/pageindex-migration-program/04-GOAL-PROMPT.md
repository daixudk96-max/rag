# GOAL: Execute frozen control package for PageIndex migration (integration mode)

**MODE**: Integration mode — drive real adapter integration, not more donor research.

---

## REQUIRED SKILLS (call in this order)

1. `autod` → check AUTOD state, route to current workflow
2. `gitnexus-exploring` → understand existing tree/backend architecture
3. `tdd-workflow` → enforce RED → GREEN for integration slices
4. (Optional) `daixucode` → refresh control files if roadmap changes

---

## MANDATORY READ ORDER (READ BEFORE ACTING)

Executor MUST read these control files IN ORDER:

1. **00-MASTER.md** — Mission, frozen strategy, donor priority
2. **01-ROADMAP.md** — Phase ordering, mainline route, paused branches
3. **02-INTERFACES.md** — Immutable contracts, adapter seams
4. **03-CURRENT-PHASE.md** — Current task details, exit criteria (READ THIS FIRST)

**Path**: `changes/pageindex-migration-program/`

---

## EXECUTION MODE (Integration Mode)

- **READ FIRST**: Extract current phase from `03-CURRENT-PHASE.md` (do NOT assume from memory)
- **GitNexus impact**: Run `gitnexus impact` before ANY symbol edit in llamaindex_runtime/
- **TDD cycle**: RED (write integration test) → GREEN (implement adapter) → IMPROVE
- **Reindex**: `gitnexus analyze --embeddings --skills --verbose` after each slice
- **Phase completion**: Verify exit criteria, report to user for gate decision

---

## FROZEN CONSTRAINTS (Generic)

- **PageIndex donor**: NOT modified (frozen contract)
- **Registry seam**: MUST use `RegistryWriter` protocol (no direct DB writes)
- **BackendHit format**: MUST preserve output contract
- **RuntimeSettings**: MUST route LLM calls through unified seam
- **Existing logic**: MUST preserve runtime.py, semantic_distribution.py, hiro_decision_policy.py

---

## STOP CONDITIONS

Executor MUST STOP and report to user if:

- **Frozen contract violation** → STOP immediately
- **Paused branch re-entry** → STOP, ask user (no auto-unpause)
- **HIGH/CRITICAL impact** → STOP, confirm with user before edit
- **Confidence < 0.7** → STOP, ask for clarification
- **Test blockers** → STOP, report dependency issues, await gate decision
- **Phase complete** → STOP, report exit criteria met, await gate decision

---

## CURRENT PHASE (DO NOT ASSUME)

**READ FROM**: `changes/pageindex-migration-program/03-CURRENT-PHASE.md`

Executor must read this file to extract:
- Current phase number (Phase 1, 2, 3, 4, 5)
- Current task details
- Blockers and remaining subtasks
- Confidence level
- Exit criteria

**DO NOT ASSUME FROM MEMORY OR CHAT HISTORY.**

---

## Integration Mode Requirements

This control package is in **integration mode**. Executor MUST:

- ✓ Implement runnable adapter outcomes (NOT more donor research)
- ✓ Verify Registry write success (tree_nodes, node_spans)
- ✓ Demonstrate token savings (90%+ reduction)
- ✓ Run integration tests (PageIndexClient functional)
- ✓ Complete phase based on actual integration, tests, reindex success

**DO NOT**: Evaluate donor fit, research seams, or propose approaches (Phase 1 already completed architecture).

---

## GOAL Summary

Execute PageIndex migration control package. Read control files FIRST. Extract current phase from 03-CURRENT-PHASE.md. Drive actual integration (integration mode). Stop on blockers, violations, or phase completion. Await user gate decision before phase advance.

---

**EXECUTOR**: Start by reading `changes/pageindex-migration-program/03-CURRENT-PHASE.md` to extract current state.