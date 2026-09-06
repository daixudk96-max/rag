---
phase: 16-raw-corpus-entity-layer
type: replan
package: GATE3-WSL-SKIP-W2
date: 2026-08-29
authorization: explicit user grant (2026-08-29: "123我都授权" for WSL measurement + real inference; skip decision "没有，那就给他标记跳过吧，下一步。选项2，记录跳过即可" = TDD-governed amendment authorization)
supersedes: 16-13-GATE3-WSL-GAP-DOWNSTREAM-2026-08-29.md blocker status (now SKIPPED BY USER DECISION)
status: planning
---

# Gate 3 WSL Skip Package W2 — Replan (TDD-governed contract amendment)

## Purpose

Implement the user's skip decision honestly: the frozen gate3 WSL gate blocks every attempt on
this host because `probe_wsl_availability` returns AVAILABLE from `wsl.exe --version` rc=0
alone, while the only installed distribution is the docker-desktop backend (no general-purpose
Linux userspace). The user has decided to SKIP the WSL measurement requirement on this host and
proceed to the real inference attempt.

## Truthfulness analysis (why this is not fabrication)

- Contract 16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json L332: "truthful WSL measurement seam
  (explicit available-WSL probe; default probe must not **silently** record unavailable)".
- A distro-usability check (`wsl.exe -l -v` parsed, evidence retained) records unavailable
  **non-silently**: wsl.exe existing + --version rc=0 only proves the exe; no general-purpose
  distribution is a truthful, evidenced unavailability of a measurable WSL.
- 16-RESEARCH.md L201 original positioning: WSL is "仅记录，不阻塞 Windows 主路径"
  (measurement-only, never a blocker for the Windows main path) — the skip restores this
  original intent at the implementation layer.
- Frozen `_wsl.py` signatures are NOT modified; the check is a NEW module + injected seam.

## Scope (bounded, single writer, TDD)

### T1 — New gate3 module `llamaindex_runtime/gate3/_wsl_distro.py`
- `probe_wsl_distro_usability(*, wsl_executable=None, base_env=None, runner=None, timeout_s=10.0) -> WslDistroUsability`
  with frozen dataclass `WslDistroUsability(general_purpose_distro: bool, evidence_line: str | None)`.
- Runs `wsl.exe -l -v` (fixed argv, shell=False, bounded timeout, capture_output, scrubbed
  child env via `construct_child_env` + `_default_base_env` allowlist — same discipline as
  `_wsl.py`). Parses UTF-16LE/UTF-8 output defensively (wsl.exe emits UTF-16 on Windows).
  docker-desktop/docker-desktop-data distributions do NOT count as general-purpose.
  Subprocess failure / unparseable output -> fail-closed `general_purpose_distro=False` with
  the error recorded (never silently).
- Tests first (RED): fake runner injection (existing pattern), docker-desktop-only case,
  general distro case (e.g. Ubuntu line), subprocess error case, unparseable case.

### T2 — Launcher seam extension `run_raner_smoke_launch.py`
- New flag `--wsl-distro-check` (store_true). When set, launcher computes
  `WslDistroUsability`; if no general-purpose distro, it passes
  `wsl_availability=WslAvailability(status=WslStatus.NOT_ELIGIBLE, version_line=<evidence>,
  error=<"no general-purpose WSL distribution; recorded non-silently">)` into
  `supervise_launch` via the EXISTING `wsl_availability` injection seam
  (`run_raner_smoke_launch.py:174,215` -> `_parent.py:161-168`).
- NO frozen module changes: `_wsl.py`/`_parent.py` untouched. NOT_ELIGIBLE flows through the
  frozen contract as truthful (frozen runner records status="not_eligible", envelope=None —
  an allowed frozen status, evidence written).
- Without the flag, behavior is byte-identical to today (default remains the strict probe).
- Tests first (RED): flag absent -> unchanged behavior; flag present + no distro ->
  not_eligible path -> attempt proceeds; flag present + distro present -> AVAILABLE still
  blocks (strict probe retained).

### T3 — Attempt execution (real inference, user-authorized)
- Fresh attempt_id (uuid4 hex, same generation discipline as first attempt).
- Run: `rtk proxy python run_raner_smoke_launch.py --authorized --wsl-distro-check ...`
  with PYTHONPATH=E:/github/rag, all paths absolute, mirror digest
  1c53105d095c7839446332d34f5693b6dfc56b286ed19de2ab27b68905895424.
- Expected: launch_committed -> worker spawns -> model loads (2.24GB, CPU) -> 3 inference
  passes -> fixture signatures verified (PER/LOC/CORP/PROD) -> evidence + resource report
  published -> terminal ok in append-only registry.
- Failure is a VALID outcome (permanent execution_failed record): fixture mismatch, model
  load failure, etc. — never retried silently (per-attempt contract).

### T4 — Evidence + doc closeout
- Verify registry JSONL append-only chain, evidence file, resource report.
- Append attempt record to R1 completion doc + WSL gap doc.
- Update W2 status to COMPLETE.

## Coordinator verification round 2 (2026-08-31): argv/env channels proven closed, wrapper mandated

The implementer's follow-up DID implement the worker-side gate swap
(run_raner_smoke_attempt.py:123-157 `_resolve_wsl_availability` + main(distro_probe=None) seam;
mtime 2026-08-31 10:13 — the coordinator's round-1 read raced the implementer's session) and
test_attempt_wsl_skip.py. However the coordinator then PROVED both delivery channels from the
launcher to the spawned worker are closed: frozen `_parent.py:174` hardcodes
`cmd = [venv_python, worker_script, "--attempt-id", attempt_id]` (no extra argv possible) and
`_env.py construct_child_env` L106-118 copies ONLY `_DEFAULT_ALLOWED_KEYS` (+3 direct
GATE3_*/RAG_NER keys in `_parent.py:171-173`) — any custom env key is stripped. With no
delivery channel, a real attempt would still burn a permanent execution_failed record. The
sanctioned solution (final instruction messageId dac3157e-c27d-4efa-a845-856df91da20b): a NEW
~20-line wrapper script `run_raner_smoke_attempt_with_distro_check.py` that appends
`--wsl-distro-check` and forwards into the real worker main() (all gates, the startup barrier,
and the per-attempt contract unchanged); the attempt command passes the wrapper as
--worker-script. Frozen files remain untouched.

## Coordinator verification round 1 (2026-08-31): worker change missing, second correction dispatched

Independent coordinator verification of the first W2 delivery: launcher changes
(--wsl-distro-check routing + distro_probe seam) and _wsl_distro.py are correct and green
(594 passed, 4 skipped re-verified; black/ruff/mypy/py_compile clean). BUT the worker file
run_raner_smoke_attempt.py was NOT modified (mtime still 2026-08-12; lines 159-167 still build
the contract from the raw probe). The first scope-extension message arrived after the
implementer's turn had completed. Consequence if unfixed: supervisor commits launch_committed +
worker_started, then the spawned worker independently probes AVAILABLE and returns 1 -> a
permanent execution_failed registry record per attempt. A mandatory follow-up was dispatched
(send_message messageId b1d0d137-784e-456d-9a51-a9eb29c8ed04) requiring the worker gate swap
(--wsl-distro-check flag + distro_probe seam) and, because the frozen _parent.py builds the
worker cmd without extra flags and construct_child_env allowlist-scrubs env, a thin wrapper
worker script (run_raner_smoke_attempt_with_distro_check.py) that appends the flag and forwards
into the real worker main() — the attempt command then passes the wrapper as --worker-script.
No frozen file changes; per-attempt contract intact.

## Coordinator scope correction (2026-08-29, mid-implementation)

Source verification during dispatch review found T2 alone is INSUFFICIENT: the spawned worker
performs its own WSL gate at run_raner_smoke_attempt.py:159-167 (independent
build_wsl_measurement_contract from probe_wsl_availability(); the injected provider parameter
cannot cross the process boundary). With launcher-side skip only, the supervisor would commit
launch_committed + worker_started, then the worker would return 1 at its WSL gate — producing a
real execution_failed registry record on every attempt. The worker file
(verification/phase16-raw-corpus-entity-layer/run_raner_smoke_attempt.py, Task #218 harness,
NOT a frozen gate3 module) is therefore added to the W2 editable scope with a surgical change:
same optional --wsl-distro-check flag + distro_probe test seam + gate check swap
(AVAILABLE-without-general-distro -> truthfully NOT_ELIGIBLE via the new module; probe error ->
BROKEN fail-closed). Communicated to the implementer via send_message (messageId
b3b8f7c4-b44b-4238-887e-c0e692e74f0a). All other constraints unchanged: frozen gate3 modules
(`_wsl.py`, `_parent.py`, `_staging.py`, `_runtime_builder.py`, etc.) remain untouched.

## Constraints (unchanged)
- No Docker/PostgreSQL/external DB/network download/model download/C2/commit/push.
- Model comes from the frozen local mirror only. No mutation of global C:\Python311.
- Frozen gate3 modules: no source edits (`_wsl.py`, `_parent.py`, `_staging.py`,
  `_runtime_builder.py`, etc.). New code only in new files + launcher CLI (R1-owned file)
  + the attempt worker harness (scope-corrected above).
- Single TDD implementer writer; coordinator non-implementer, verifies independently.
- All commands via rtk proxy.
- GitNexus impact: supervise_launch LOW (0 direct callers), probe_wsl_availability LOW
  (3 upstream), build_wsl_measurement_contract LOW (3 upstream) — verified 2026-08-29.
## 状态收尾(2026-08-31)

- T1/T2 完成(见上文交付清单); 协调器独立复跑: gate3 全量 600 passed, 4 skipped; black 7 files unchanged; ruff All checks passed; mypy Success; py_compile exit 0。
- T3(真实 attempt): 未执行 — 用户 2026-08-31 决定直接跳过 Linux/WSL 并进入下一部分(见 16-13-GATE3-WSL-GAP-DOWNSTREAM-2026-08-29.md '最终关闭'章节, 含 venv wheel/_wsl_distro 阻塞发现与恢复步骤)。
- T4: 本节即收尾记录。
