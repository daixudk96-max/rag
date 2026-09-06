---
phase: 16-raw-corpus-entity-layer
type: replan
package: GATE3-PREP-R1
date: 2026-08-29
authorization: explicit user grant (2026-08-29, user reply "1" to "authorize continue")
supersedes: Task #224 remediation-allowance LIMIT_REACHED record (16-13-SUMMARY.md Task #227 addendum 2026-08-12)
status: planning
---

# Gate 3 Preparation Remediation Package R1 — Replan

## Purpose

Task #227 addendum (2026-08-12) recorded: Task #224 INCOMPLETE LIMIT_REACHED; two independent
spec reviews BLOCKED; the decisive blocker is **no production mechanism to populate/validate the
wheelhouse** plus **no production launcher composition**; remediation allowance was exhausted and
any further writer dispatch requires **explicit user authorization** and a **fresh replan**.

The user (2026-08-29, reply "1") authorized: plan and dispatch a new bounded TDD remediation
package to complete the chain **wheelhouse populate/validate → isolated venv build → import
proof + network denial proof → launcher composition (exact Plan 16-13 runner reachable path)**,
all passing before launching the first real Gate 3 attempt.

## Authorization Boundary (verbatim §2.1 constraints still in force)

- ✅ AUTHORIZED: pip download of official Python package wheels from PyPI into repository-local
  `.cache/raner-wheelhouse/` ("official Python package access solely for repository-local isolated
  preparation", per Task #222 preparation_authorization + user "1").
- ✅ AUTHORIZED: building the isolated venv under `.cache/raner-runtime/`, running the offline
  tokenizer import proof (no model load, no inference), and composing the launcher CLI.
- ❌ FORBIDDEN (unchanged): Docker, PostgreSQL, external database, model download (the RaNER model
  is already local under `.cache/raner-mirror/`), RaNER inference, any live gate, C2, commit, push,
  mutation of global `C:\Python311`, and any edit to the frozen mirror.
- Forbidden-env guard: all substantive subprocess commands run via `rtk proxy` (or `rtk env -u
  DATABASE_URL ...`) with the canonical clean-env guards from prior phase-16 selectors.
- Coordinator is a NON-implementer: it routes/dispatches/verifies/reports; all source/test changes
  are written by a single TDD implementer subagent.
- Workflow tool is DISABLED; ordinary background subagents are permitted.

## Current Facts (verified 2026-08-29)

1. **NO requirements.lock** in the repo: no `*.txt` with `--hash=sha256:` lines exists anywhere;
   `llamaindex_runtime/uv.lock` is stale (`uv lock --check` exit 1) and does not pin torch/
   transformers versions (name-only entries).
2. **NO wheelhouse**: `.cache/` contains only `raner-mirror/` (the verified read-only mirror).
   No `.cache/raner-runtime/`, no venv, no dist, no wheelhouse, no proof artifacts.
3. **NO production launcher**: `supervise_launch` / `LaunchSpec` exist only in
   `llamaindex_runtime/gate3/_parent.py` (320 lines); zero callers anywhere (grep confirms only
   `test_parent.py` uses them). `prepare_raner_runtime.py` has `build-plan --execute` but the
   supervisor launcher is never composed.
4. **Preparation CLI exists**: `verification/phase16-raw-corpus-entity-layer/prepare_raner_runtime.py`
   (211 lines) — `validate-pyvenv`, `validate-lock`, `mirror-integrity`, `mirror-readonly`,
   `import-proof`, `build-plan` (dry-run default, `--execute` authorizes real artifact-producing
   execution).
5. **Live runner** `verification/phase16-raw-corpus-entity-layer/run_raner_smoke_live.py` (Task
   #218, 491 lines) imports `llamaindex_runtime.entity.*` (offline_mirror, rarer_adapter,
   label_map, segmenter, contracts) plus, at model load, ModelScope `pipeline` (which itself
   imports torch, addict, transformers, tokenizers, sentencepiece).
6. **Global env probe (read-only, 2026-08-29)**: `modelscope.pipelines` import FAILS with
   `ModuleNotFoundError: No module named 'addict'` (global 1.39.1); `transformers.AutoTokenizer`
   imports OK; torch 2.5.1+cu124 present (CUDA unavailable); sentencepiece 0.2.1 present; protobuf
   6.33.5 present but incompatible with frozen `>=3.19,<3.21`. Global env is polluted and unusable
   — hence the isolated venv requirement.
7. **Import method**: `offline_mirror.load_model` uses `modelscope.pipelines.pipeline(
   Tasks.named_entity_recognition, model=str(root), device="cpu")`; the proof tokenizer path uses
   `transformers.AutoTokenizer.from_pretrained(root, local_files_only=True, use_fast=True)`.
8. **Mirror**: `.cache/raner-mirror/` complete (7 files; pytorch_model.bin 2,239,833,895 bytes,
   SHA256 `62fbd5ca...` matches manifest; artifact_digest
   `1c53105d095c7839446332d34f5693b6dfc56b286ed19de2ab27b68905895424`; all read-only non-reparse).
9. **PyPI reachable**: `pip index versions torch` works; torch 2.13.0 latest, 2.5.1 available.
10. **GitNexus**: CLI 1.6.4 (`npx gitnexus`), index up-to-date at commit 9c1922c; `impact` /
    `context` / `detect-changes` commands available via `npx gitnexus`. NO MCP tools in this session
    — impact analysis MUST use the CLI.
11. **Gate3 modules complete** (Task #221/#224 produced): `_parent.py` (supervisor), `_registry.py`,
    `_reconcile.py`, `_lifecycle.py`, `_publisher.py`, `_wheelhouse.py` (validate/copy),
    `_runtime_builder.py` (A4, plan + runbook + provision), `_staging.py`, `_lock.py`, `_prep.py`
    (import proof), `_paths.py`, `_env.py`, `_fsguard.py`, `_wsl.py`. tests: `tests/llamaindex_runtime/gate3/`
    566 passed / 4 skipped (2026-08-29 independent rerun).

## Blocker Resolution Design

### T1 — Determine the exact dependency closure for the live path

The live path is: `run_raner_smoke_live.py` → entity modules → `load_model` →
`modelscope.pipelines.pipeline(..., device="cpu")` + `transformers.AutoTokenizer.from_pretrained(...)`.

Required direct imports (verified import chain): `modelscope` (1.39.x, incl. `modelscope.pipelines`
+ `modelscope.utils.constant`), `addict` (modelscope.pipelines hard-requires it), `transformers`
(AutoTokenizer), `tokenizers` (fast tokenizer backend), `sentencepiece` (sentencepiece.bpe.model
tokenizer), `torch` (CPU; modelscope pipeline / transformers under the hood), plus transitive
deps of each (numpy, filelock, huggingface-hub, safetensors, regex, requests, tqdm, packaging,
setuptools, urllib3, typing-extensions, networkx, jinja2, fsspec, opt-einsum?, sympy, pyyaml,
python-dateutil, protobuf<3.21,>=3.19, etc.).

The minimal importer set is: `modelscope`, `transformers`, `tokenizers`, `sentencepiece`, `addict`,
`torch`, and their transitive closures. `protobuf` must be pinned to `>=3.19,<3.21` to satisfy
modelscope's `nlp` extra constraint.

### T2 — Generate the exact hash-locked requirements + wheelhouse

Steps (implementer):
1. Create `.cache/raner-wheelhouse/` (repo-local; under project root so non-reparse absolute
   chain; create via strict `mkdir` after `lstat` verification per `_wheelhouse` conventions).
2. Use `pip download` (rtk proxy; official PyPI index; `--only-binary=:all:` for wheels; target
   Python 3.11 Windows) for the closure set into the wheelhouse; record each wheel's filename,
   parse `name==version` from the wheel filename, compute SHA-256 of each wheel.
3. Write `.cache/raner-runtime/requirements.lock` in pip requirements-file format:
   `name==version --hash=sha256:<digest>` for every wheel, sorted by name; validate with
   `validate_hash_lock` (green) and the CLI `validate-lock`.
4. Add `.cache/raner-runtime/wheelhouse_manifest.json` (deterministic) and validate the wheelhouse
   via `validate_wheelhouse` (via `build-plan` with `--wheelhouse-dir`).

### T3 — Build the isolated venv + run the import proof

Use `prepare_raner_runtime.py build-plan --execute` (real authorized artifact-producing execution
behind the explicit `--execute` flag) with the lock + wheelhouse + repo artifact. This produces:
`venv/`, `dist/`, `requirements.lock`, `dependency_provenance.json`, `import_proof.json`,
`network_denial_proof.json`, `wheelhouse_manifest.json` under `.cache/raner-runtime/`. The offline
import proof (`run_import_proof`) then proves `transformers.AutoTokenizer.from_pretrained(...,
local_files_only=True, use_fast=True)` loads the tokenizer with zero network attempts.

### T4 — Compose the production launcher CLI

The only production-path gap. Create
`verification/phase16-raw-corpus-entity-layer/run_raner_smoke_launch.py` (or extend
`prepare_raner_runtime.py`) that:
1. Reads the prepared runtime plan (or rebuilds it from `.cache/raner-runtime/` state),
2. Builds the `LaunchSpec` (attempt_id, venv_python, worker_script=run_raner_smoke_attempt.py,
   mirror_root, output_root, live_runner, mirror_digest),
3. Calls `supervise_launch(...)` with the OS lock + registry path + child env,
4. Prints the terminal `LaunchOutcome`.

This closes blocker #3 ("no production mechanism to populate/validate the wheelhouse" was T2/T3;
launcher composition is T4) and gives an exact-reachable-path runner.

### T5 — Coordinator fresh verification + TDD

- TDD: test-first for any NEW symbol (launcher CLI, any new helper). Frozen earlier tests stay
  green (they must NOT be weakened).
- Coordinator fresh runs: focused new tests + full gate3 suite + black/ruff/isort + scoped mypy +
  py_compile.
- Gate condition: T1–T4 pass → coordinator verify → review chain (spec/code/python/security) →
  then, and only then, a real Gate 3 attempt may be planned (still requires separate explicit
  coordinator-initiated attempt per the attempt contract).

## Files likely changed (implementation)

- NEW `.cache/raner-wheelhouse/*.whl` + `.cache/raner-wheelhouse/` (generated cache, untracked)
- NEW `.cache/raner-runtime/requirements.lock`, `venv/`, `dist/`, `dependency_provenance.json`,
  `import_proof.json`, `network_denial_proof.json`, `wheelhouse_manifest.json`
- NEW `verification/phase16-raw-corpus-entity-layer/run_raner_smoke_launch.py` (launcher CLI)
- NEW `tests/llamaindex_runtime/gate3/test_smoke_launch_cli.py` (TDD tests)
- MAYBE `verification/phase16-raw-corpus-entity-layer/prepare_raner_runtime.py` (small extension)
- PLANNING-ONLY: this replan doc; no frozen contract tests weakened.

## Constraints for the implementer

- Python 3.11.9 via `rtk proxy`; no mutation outside the explicit paths.
- All new files: Black-formatted, isort-clean, ruff-clean, mypy-clean (scoped to the new files);
  type annotations on all public symbols.
- GitNexus: MUST run `npx gitnexus impact` on any existing symbol before editing; `detect-changes`
  before any commit (no commit in this package).
- No model load, no inference, no live gate, no registry writes during preparation.
- Single writer: exactly one implementing subagent; the coordinator never writes source/test.

## Verification Gate for this package

1. requirements.lock validates (`validate_hash_lock` + CLI `validate-lock`).
2. wheelhouse validates against lock entries (`build-plan --wheelhouse-dir`, dry-run).
3. isolated venv `pyvenv.cfg` shows `include-system-site-packages=false`.
4. import proof succeeds (`proof_kind` correct, `network_attempts_observed=0`, `is_fast=true`).
5. launcher CLI dry-print produces a valid `LaunchSpec` with absolute non-reparse roots.
6. New tests RED→GREEN; frozen tests remain green (no weakening).
7. Coordinator fresh rerun of the full gate3 suite + black/ruff/mypy/py_compile.
8. Review chain (spec/code/python/security) APPROVE_WITH_NOTES or better.
