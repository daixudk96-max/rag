# GOAL: Execute complete PageIndex integration (resolve TODOs + verify)

**MODE**: Integration mode — complete implementation (not just architecture)

---

## REQUIRED SKILLS (call in this order)

1. `autod` → check AUTOD state, route to workflow
2. `gitnexus-exploring` → understand reasoning_backend dependencies
3. `tdd-workflow` → enforce RED → GREEN for each TODO resolution
4. (Optional) `daixucode` → refresh control files if roadmap changes

---

## MANDATORY READ ORDER (READ BEFORE ACTING)

Executor MUST read these control files IN ORDER:

1. **00-MASTER.md** — Current reality (80% complete + 20% TODO), remaining work
2. **01-ROADMAP.md** — Task sequence (Task 1-3), verification steps
3. **02-INTERFACES.md** — Immutable contracts, adapter seams
4. **03-CURRENT-PHASE.md** — Current task details, exit criteria (READ THIS FIRST)

**Path**: `changes/pageindex-complete-integration/`

---

## EXECUTION MODE (Integration Mode — Complete Implementation)

- **READ FIRST**: Extract current task from `03-CURRENT-PHASE.md` (do NOT assume from memory)
- **GitNexus impact**: Run `gitnexus impact` before ANY symbol edit in reasoning_backend.py
- **TDD cycle**: RED (write test for TODO resolution) → GREEN (implement) → IMPROVE
- **Reindex**: `gitnexus analyze --embeddings --skills --verbose` after each implementation
- **Phase completion**: verify exit criteria, update 03-CURRENT-PHASE.md, proceed to next task

---

## FROZEN CONSTRAINTS (Generic)

- **PageIndex donor**: NOT modified (frozen contract)
- **Registry seam**: MUST use RegistryWriter protocol (no direct DB writes)
- **BackendHit format**: MUST preserve output contract (frozen fields + provenance)
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
- **Task complete** → STOP, report exit criteria met, await gate decision

---

## CURRENT TASK (DO NOT ASSUME)

**READ FROM**: `changes/pageindex-complete-integration/03-CURRENT-PHASE.md`

Executor must read this file to extract:
- Current task number (Task 1.1, 1.2, 1.3, 2.1, etc.)
- TODOs to resolve (reasoning_backend line numbers)
- Exit criteria (tests to pass, contracts to preserve)
- Confidence level
- Next tasks preview

**DO NOT ASSUME FROM MEMORY OR CHAT HISTORY.**

---

## Integration Mode Requirements

This control package is in **integration mode — complete implementation**. Executor MUST:

- ✓ Resolve ALL TODOs/stubs (not just architecture files)
- ✓ Implement runnable reasoning_backend (LLM reasoning functional)
- ✓ Test with real document (PageIndexClient integration)
- ✓ Verify Registry write success (tree_nodes populated)
- ✓ Demonstrate token savings (90%+ reduction)
- ✓ Complete backend stack verification (tree + reasoning + hybrid)

**DO NOT**: Accept stub/TODO as complete (integration mode requires runnable outcomes)

---

## GOAL Summary

Execute PageIndex complete integration control package. Read control files FIRST. Extract current task from 03-CURRENT-PHASE.md. Resolve TODOs, verify frozen contracts, test integration, demonstrate runnable outcomes. Stop on blockers, violations, or task completion. Await user gate decision before next task.

---

**EXECUTOR**: Start by reading `changes/pageindex-complete-integration/03-CURRENT-PHASE.md` to extract current task (Task 1.1: LLM reasoning call).