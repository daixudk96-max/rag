---
phase: 16-raw-corpus-entity-layer
type: completion
package: GATE3-PREP-R1
date: 2026-08-29
status: CLOSED (blockers T1-T4 resolved; review chain ALL STAGES APPROVED; first real attempt fail-closed validated; WSL gap documented downstream)
---

# Gate 3 Preparation Remediation Package R1 — Completion

## Status

R1 package CORE BLOCKERS RESOLVED (per replan .planning/phases/16-raw-corpus-entity-layer/16-13-GATE3-PREP-REPLAN-R1-2026-08-29.md):

| Blocker | Status | Evidence |
|---|---|---|
| No requirements.lock | RESOLVED | .cache/raner-runtime/requirements.lock (52 hash-locked lines) |
| No wheelhouse | RESOLVED | .cache/raner-wheelhouse/ (52 wheels) + .cache/raner-runtime/dist/ (53 incl repo wheel) |
| No isolated venv + import proof | RESOLVED | .cache/raner-runtime/venv/ (isolated, include-system-site-packages=false) + import_proof.json proof_kind=raner_runtime_import_tokenizer_offline, network_attempts_observed=0, is_fast=true |
| No production launcher | RESOLVED | verification/phase16-raw-corpus-entity-layer/run_raner_smoke_launch.py + tests (3 passed) |

## Implementation facts

- Wheelhouse 52 wheels (all .whl, byte-verified against lock): modelscope==1.39.1, transformers==4.57.3, torch==2.5.1+cpu, tokenizers==0.22.2, sentencepiece==0.2.1, huggingface_hub==0.36.2, numpy==2.4.6, safetensors==0.8.0, addict==2.4.0, protobuf==3.20.3, fsspec==2026.2.0, datasets==4.8.4, pandas==3.0.5, pyarrow==25.0.1, Pillow==12.3.0 + aiohttp/dill/multiprocess/xxhash/tzdata/yarl/propcache/multidict/frozenlist/aiosignal/aiohappyeyeballs/attrs/anyio/h11/httpcore/httpx/...
- Closure evolution (documented, coordinator-authorized): 34 (base) → 51 (+datasets families, fsspec downgrade to 2026.2.0) → 52 (+Pillow). datasets and Pillow are modelscope.pipelines HARD import requirements (marked optional-extra in metadata but unconditionally imported by modelscope/pipelines/__init__.py → base.py → msdatasets/ms_dataset.py:9 and pipeline_inputs.py:4). Both are within the user authorization (official Python package access for repo-local isolated preparation).
- .cache/raner-runtime/ artifacts: venv/, dist/ (53 wheels incl llamaindex_runtime-0.1.0), requirements.lock (52), dependency_provenance.json, import_proof.json, network_denial_proof.json, wheelhouse_manifest.json, repo_artifact_contract.txt (203 bytes binding staged repo copy to plan digest af4f8dea...).
- build_id: 4464256d21b0424d94db043015061ca1; lock_raw_digest: 924c993836db8a9fe35fcc2a1737d3eb0feba256330a6dedc829868a6dcdb230.
- launcher CLI: verification/phase16-raw-corpus-entity-layer/run_raner_smoke_launch.py — argparse (--attempt-id, --venv-python, --worker-script, --mirror-root, --output-root, --live-runner, --mirror-digest, [--timeout, --registry-path, --lock-path]); constructs LaunchSpec; calls supervise_launch (default spawn=subprocess.Popen), prints status/result_reason/exit_code, exit 0 for ok else 1.
- Tests: tests/llamaindex_runtime/gate3/test_smoke_launch_cli.py (3 tests: ok outcome argv propagation, BROKEN WSL -> not_launched with no spawn, spawn OSError -> execution_failed/launch_denied).

## Coordinator fresh verification (independent, 2026-08-29)

- Full gate3 suite: 569 passed, 4 skipped (15.19s) — includes 3 new launcher tests.
- Black (new files): 2 files would be left unchanged.
- Ruff (new files): All checks passed.
- Mypy (new files, --follow-imports=skip): Success: no issues found in 2 source files.
- py_compile (new files): exit 0.
- Isolated venv real import chain (venv python, offline env): modelscope.pipelines OK, AutoTokenizer OK, torch 2.5.1+cpu. pyvenv.cfg: include-system-site-packages=false (isolation proven).
- import_proof.json: {"build_id":"4464256d21b0424d94db043015061ca1","is_fast":true,"network_attempts_observed":0,"proof_kind":"raner_runtime_import_tokenizer_offline","runtime_name":"llamaindex-runtime","runtime_version":"0.1.0"}.
- Lock semantics: 52 lines name==version --hash=sha256:<64hex>; validate_hash_lock=52; validate-lock CLI OK.

## Files created (untracked, no commit)

- verification/phase16-raw-corpus-entity-layer/run_raner_smoke_launch.py (launcher CLI)
- tests/llamaindex_runtime/gate3/test_smoke_launch_cli.py (3 TDD tests)
- Generated cache: .cache/raner-wheelhouse/, .cache/raner-runtime/, .cache/raner-lock/ (requirements.lock), .cache/raner-repo-dist/ (llamaindex_runtime-0.1.0 wheel)
- Planning-only: .planning/phases/16-raw-corpus-entity-layer/16-13-GATE3-PREP-REPLAN-R1-2026-08-29.md (this + replan doc)

## Discipline compliance

- No model load, no inference, no live gate, no registry writes during preparation. Mirror untouched. No commit/push. No global C:\Python311 mutation.
- All commands via rtk proxy python / rtk env. Frozen gate3 tests untouched (566 baseline + 3 new = 569).
- Coordinator is non-implementer: all source/test/wheelhouse/lock/provision carried out by TDD implementer subagents (4 rounds: #1 no-constraint failure interrupted; #2 corrected 34-closure + launcher; #3 datasets 51-closure; #4 Pillow 52-closure success). All claims independently re-verified by coordinator.

## Next steps

1. **Review chain** (spec/code-quality/python/security) on the R1 changes (launcher CLI + tests; closure/lock/wheelhouse/venv are generated artifacts, review focuses on the new launcher + test code and the closure decision).
2. Then (per replan gate) real Gate 3 attempt planning can proceed — still requires explicit coordinator-initiated attempt per 16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json (per-attempt, fresh immutable attempt_id, launch_committed before model loader, terminal per attempt).
3. NOTE: The live smoke attempt itself would load the RaNER model (2.26GB mirror) and run inference — this is a LIVE GATE and remains NOT authorized; R1 only prepared the runtime harness.

## Open items / recorded (not blockers for R1)

- The launcher CLI's supervise_launch default spawn path (real subprocess) is not exercised by the TDD tests (they inject spawn) — this is deliberate; a real attempt is separately authorized.
- .cache/raner-lock/requirements.lock duplicates .cache/raner-runtime/requirements.lock (the latter is the authoritative plan input; the former was the generation workspace). Not a defect.
## Review chain (2026-08-29, after launcher fix)

| Stage | Result | Findings |
|---|---|---|
| Spec compliance | APPROVE_WITH_NOTES (0C/0H/0M/0L/2N) | LaunchSpec 9 fields complete; supervise_launch params all forwarded; no scope creep; tests real behavior |
| Code quality | APPROVE_WITH_NOTES (0C/1H/2M/2L/3I) | HIGH-1 env_base {} missing Windows keys |
| Python language | APPROVE_WITH_NOTES (0C/1H/3M/3L/4I) | HIGH-1 (same) + timeout validation/type annotations |
| Security | APPROVE_WITH_NOTES (0C/1H/2M/3L/3I) | HIGH-2 no explicit authorization gate (NOT_ELIGIBLE could reach real inference) |

## Owner fix (IMPLEMENTER #5, 7b99d854) — 2 HIGH + 3 MEDIUM + 2 LOW resolved

- HIGH-1 FIXED: `_CHILD_BASE_KEYS` (39 explicit allowlist keys) + `_default_child_env()` mirroring `_wsl._default_base_env` (key-membership copy, never full enum, no forbidden key); real scrubbing still by `_parent.py:170 construct_child_env`. main() default `env_base=_default_child_env()`.
- HIGH-2 FIXED: `--authorized` (store_true, default False); missing -> stderr 'authorization required: pass --authorized to launch a live smoke attempt' + return 1, never spawns (before LaunchSpec/supervise_launch). docstring updated.
- MEDIUM-1 FIXED: `--timeout` type=`_positive_finite_float` (0<t<inf; rejects 0/neg/nan/inf/non-numeric -> argparse SystemExit 2).
- MEDIUM-2 FIXED: `spawn: SpawnFn | None` (new SpawnFn Protocol `__call__(cmd, *, env, cwd, stdin) -> object`); `wsl_measurement_provider: LiveWslMeasurementProvider | None`; all public symbols annotated; no bare Any.
- LOW-1 FIXED: `_TERMINAL_FAILURE_STATUSES` dead constant removed.
- LOW-2 FIXED: main() try/except `(ValueError, AttemptPathError, OSError, LockContentionError, ChildEnvError)` -> stderr 'error: ...' + return 1 (no bare traceback).

## Tests (not weakened; strengthened)

- NEW `test_authorization_required_never_spawns`: no --authorized -> spawn never called + rc=1 + stderr message + no stdout 'status='.
- STRENGTHENED `test_ok_outcome_propagated`: asserts spawn env contains PYTHONNOUSERSITE=1, RAG_NER_MIRROR_ROOT, GATE3_OUTPUT_ROOT, GATE3_LIVE_RUNNER; FORBIDDEN_ENV_KEYS all absent; _CHILD_BASE_KEYS present-keys forwarded.
- NEW `test_invalid_timeout_rejected` (parametrized '0'/'−5'/'nan'/'inf'/'abc'): SystemExit code=2.
- Original 3 tests (ok/not_launched/launch_denied) unchanged assertion strength.

## Coordinator fresh verification after fix (independent rerun, 2026-08-29)

- Full gate3 suite: **575 passed, 4 skipped** (12.64s; +6 new tests).
- black: 2 files unchanged. ruff: All checks passed. mypy (--follow-imports=skip): Success, no issues in 2 source files.
- Authorization gate live check: `run_raner_smoke_launch.py` without --authorized -> exit 1 + 'authorization required: pass --authorized to launch a live smoke attempt' (no spawn).
- Code inspection: `_CHILD_BASE_KEYS`/`_default_child_env`/`_positive_finite_float`/SpawnFn Protocol/--authorized all present and correct.

## R1 package status

- Blockers T1-T4 (wheelhouse populate/validate, isolated venv build, import proof + network denial proof, launcher composition): **ALL RESOLVED**.
- Review chain: **ALL STAGES APPROVED** (with notes; HIGHs fixed by owner and re-verified).
- Next step (per replan gate, requires separate explicit user/coordinator authorization per 16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json): a real Gate 3 attempt. NOTE the real attempt loads the RaNER model (2.26GB mirror) and runs inference — a LIVE GATE; remains NOT authorized.

---

## First real Gate 3 attempt (2026-08-29, coordinator-initiated, per-attempt contract)

Per 16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json (per-attempt, fresh immutable attempt_id, launch_committed before model loader, terminal per attempt). Attempt id: 449cf1e358a94d708e5b39b061b6c917. Launched via run_raner_smoke_launch.py with --authorized.

**Result**: status=not_launched result_reason=wsl_not_ready exit_code=None (outer exit 1).

**Verified evidence**:
- Registry NOT created (no launch_committed, no terminal record) — fail-closed before any lifecycle write.
- Output directory NOT created (no worker spawn).
- WSL probe via gate3 (_wsl.py probe_wsl_availability) returned status=available (wsl.exe exists at C:\Windows\system32\wsl.exe, --version returns 0).
- Per frozen design, WslMeasurementContract.ready returns False for AVAILABLE without an injected live measurement provider; supervise_launch returns LaunchOutcome(status="not_launched", result_reason="wsl_not_ready") BEFORE commit_launch/spawn.
- This is the CORRECT fail-closed behavior: no model load, no inference, no registry entry, no output artifacts. The launch gate protects against unmeasured-WSL (availability without truthfully measured resource envelope).

**Conclusion**: First real Gate 3 attempt correctly demonstrates the WSL fail-closed gate. It did NOT produce quantitative measurements (cold start / peak memory / throughput / p95 latency) because WSL is AVAILABLE on this host but the frozen design requires an injected live measurement provider for AVAILABLE hosts (real WSL model benchmarking is explicitly NOT authorized per contract L270). No artifacts were written; the attempt is terminal (not_launched) with no registry record.

**Next decision point** (requires user authorization): To produce actual quantitative Gate 3 measurements with WSL AVAILABLE, a bounded live WSL measurement provider would need to be injected (still no model download — the mirror is local). Otherwise the host should be transitioned to NOT_ELIGIBLE, or the attempt treated as a successful fail-closed validation with the WSL gap formally documented as a separate downstream task.

**User decision (2026-08-29, "1")**: Accepted path 1 — treat the first real Gate 3 attempt as a successful fail-closed validation and formally document the WSL measurement gap as a separate downstream task. No WSL measurement provider injection, no host transition, no further attempt until separately authorized. The first real attempt (449cf1e358a94d708e5b39b061b6c917) is hereby recorded as terminal-not-launched evidence with zero side effects (no registry entry, no output, no model load, no inference).