---
phase: 16-raw-corpus-entity-layer
type: downstream-gap
package: GATE3-WSL-GAP
date: 2026-08-29
status: SKIPPED BY USER DECISION (2026-08-29) — WSL measurement requirement waived on this host; Gate 3 proceeds Windows-only
---

# Gate 3 WSL Measurement Gap — Downstream Task Record

## Context

The first real Gate 3 attempt (attempt_id 449cf1e358a94d708e5b39b061b6c917, 2026-08-29) correctly fail-closed at `not_launched / wsl_not_ready` because the host WSL is AVAILABLE but the frozen gate3 design requires an injected live measurement provider for AVAILABLE hosts. The attempt produced zero side effects (no registry entry, no output directory, no model load, no inference).

## User decision (2026-08-29, path 1)

User selected path 1: **accept the fail-closed validation and formally document the WSL measurement gap as a separate downstream task.** No WSL measurement provider injection, no host transition, no further attempt until separately authorized.

## What this gap means

- **Goal**: Produce truthful quantitative WSL measurements (cold start, peak memory, throughput, p95 latency) on a host where WSL is AVAILABLE.
- **Blocking condition**: `WslMeasurementContract.ready` returns False for `AVAILABLE` status without an injected `LiveWslMeasurementProvider`. The CLI path (run_raner_smoke_launch.py) has no provider injection, so every attempt on an AVAILABLE host fails closed.
- **Current state**: WSL probe on this host returns status=available (wsl.exe at C:\Windows\system32\wsl.exe, --version returns 0).

## What is NOT authorized (unchanged)

- Real WSL model benchmarking (16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json L270: "real WSL model benchmarking" is explicitly NOT authorized).
- Any live Gate 3 attempt beyond the first (already executed) without separate authorization.
- Model download (mirror is local), RaNER inference, external database, C2, commit, push.

## Options for a future downstream package (requires separate user authorization)

1. **Inject a bounded live WSL measurement provider** — a callable that performs a real WSL measurement contract (outputs a frozen-runner `WslMeasurement(status='measured', envelope=ResourceEnvelope(...))`) and is passed via `wsl_measurement_provider` seam. This is the only path to produce real quantitative measurements on an AVAILABLE host. Requires authorization for "real WSL model benchmarking" per contract L270.
2. **Host transition** — move to a machine where wsl.exe is absent (NOT_ELIGIBLE). Not recommended; hides real host capability and is not a truthful measurement path.
3. **Keep gap documented, no action** — accept that Gate 3 quantitative measurement on AVAILABLE-WSL hosts remains pending. The fail-closed gate is correct and safe; the gap is a capability, not a defect.

## Reference artifacts (first attempt)

```
attempt_id: 449cf1e358a94d708e5b39b061b6c917
result: status=not_launched result_reason=wsl_not_ready exit_code=None
registry: NOT created
output: NOT created
wsl_probe: status=available (wsl.exe --version rc=0)
```

## Addendum: user authorization 1+2 and the distribution blocker (2026-08-29, later same day)

User authorized BOTH paths ("123我都授权" = 1 and 2): (1) bounded live WSL measurement provider with "real WSL model benchmarking" authorization, and (2) the real inference attempt. Read-only feasibility probe (`wsl.exe -l -v`, exit 0) found exactly one installed distribution: **docker-desktop (STATE=Stopped, WSL version 2)** — a Docker Desktop backend utility distribution, NOT a general-purpose Linux distribution.

Consequences, verified from source:

- Measuring WSL resources truthfully requires running the model/measurement inside a real Linux userspace (the frozen-runner contract requires a `WslMeasurement(status='measured', envelope=ResourceEnvelope(...))` produced by real measurement). The only available distribution is Docker Desktop's backend — exercising it means driving Docker infrastructure, which the standing constraints (§2.1, Task #227 addendum) explicitly forbid ("禁止 Docker..."). Installing a new general-purpose distribution (e.g. Ubuntu via `wsl --install`) is a system-level mutation outside the repository and outside the authorized boundary.
- Additionally verified: the provider seam cannot cross the process boundary as a callable. `supervise_launch` spawns `worker --attempt-id` as a fresh subprocess; `run_raner_smoke_attempt.main(wsl_measurement_provider=None)` receives the provider only as an in-process function argument (run_raner_smoke_attempt.py:117-122), and the launcher's `wsl_measurement_provider` parameter (run_raner_smoke_launch.py:175,216) is only forwarded to the in-process `supervise_launch` preflight check — the provider callable would have to live inside the worker process. A CLI-injected provider would need a new sanctioned delivery channel (e.g. a repo-local provider script path the worker imports after the startup barrier), itself a TDD-governed contract amendment touching the frozen worker.

Therefore BOTH authorized items are blocked by the same hard precondition: **no general-purpose WSL distribution exists on this host**. Path 2 (real inference attempt) without path 1 is a no-op by design (fail-closed `wsl_not_ready` reproduces attempt 449cf1e3... with zero side effects).

Possible forward paths (each requires separate user decision):

A. **Install a general-purpose WSL distribution** (e.g. `wsl --install -d Ubuntu`) — a host-level system mutation, explicitly NOT in the repo-local authorization boundary; requires explicit user action or explicit authorization acknowledging the system change.
B. **Keep the gap documented** (status quo) — Gate 3 quantitative measurement remains pending until a suitable host or distribution exists.
C. **Run the attempt on a different host** where WSL is NOT_ELIGIBLE or truly measurable — the frozen design truthfully reports `not_eligible` and proceeds on such hosts.

## User skip decision (2026-08-29, final)

After full explanation of the requirement's provenance (OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md L402 → ROADMAP.md L651 Phase 16 success criteria → frozen gate3 `_wsl.py` enforcement) and the docker-desktop-only host reality, the user decided: **SKIP the WSL measurement requirement on this host and proceed.** "没有，那就给他标记跳过吧，下一步。选项2，记录跳过即可。"

Consequences of this decision:

- The WSL measurement gap is CLOSED as a blocker: no WSL provider will be built, no contract amendment for "real WSL model benchmarking", no distribution installation.
- Gate 3 quantitative evidence on this host is **Windows-only**: `ResourceEnvelope` covers Windows cold start / peak memory / throughput / p95 latency; the WSL side remains truthfully recorded as not measured (never fabricated), consistent with the original research positioning (16-RESEARCH.md L201: "仅记录，不阻塞 Windows 主路径" — measurement-only, not a blocker for the Windows main path).
- The first real attempt (449cf1e358a94d708e5b39b061b6c917, terminal-not-launched, zero side effects) remains valid evidence of the fail-closed gate.
- The frozen gate3 enforcement code (`_wsl.py`) is NOT modified. The skip is recorded at the planning/authorization layer, not by weakening the code gate. A future host WITH a general-purpose distribution can still produce the WSL measurement under the unchanged frozen design.
- The user separately authorized the real inference attempt ("123我都授权" earlier the same day; reconfirmed by choosing to proceed). The next action is a fresh Gate 3 attempt that proceeds past the WSL gate by the sanctioned skip decision and runs the real Windows-side RaNER smoke (model load from the local mirror + 3 inference passes + evidence publication), with the per-attempt contract (fresh attempt_id, launch_committed before model loader, append-only registry) fully in force.

## Next steps

- The first Gate 3 attempt is recorded as terminal-not-launched evidence (zero side effects).
- The WSL measurement gap is a downstream task that requires separate user authorization ("real WSL model benchmarking" per contract L270).
- No further Gate 3 attempts until separately authorized by the user.
## 最终关闭(2026-08-31): Linux/WSL 整体跳过 — 不再继续研究

用户决定(2026-08-31 原话): “直接跳过吧，我们进行下一个部分。这个就写到文档里，说没继续研究了。直接跳过linux吧，我们进行下一个部分。这个就写到文档里，说没继续研究了。”

- 本机不对 Linux/WSL 测量链做任何进一步研究或实现; 也不在本机发起真实 Gate 3 attempt(此前 '123我都授权' 的 attempt 授权随之搁置)。
- W2 代码已交付并验证(launcher --wsl-distro-check + wrapper + _wsl_distro.py; gate3 全量 600 passed, 4 skipped; black/ruff/mypy/py_compile 全绿; TDD RED→GREEN 有记录), 保留为可用机制, 未用于发起 attempt。
- 搁置时发现的阻塞(仅未来恢复时相关): 已 provision 的 venv(build 4464256d) 内 repo wheel af4f8dea19d1d1d92ffe0db6533004f228d6b1bcf74a00a0fb2e93189e674969 早于 _wsl_distro.py; run_raner_smoke_attempt.py:40 模块级 import llamaindex_runtime.gate3._wsl_distro → worker 会 ModuleNotFoundError。已于 2026-08-31 重建 wheel(digest 0b9951835cda4d2ed4a3674032644576c1b6b8679e33e16ecd13525e2555c811, 原地覆盖 .cache/raner-repo-dist/llamaindex_runtime-0.1.0-py3-none-any.whl; 旧原件完整保留于 .cache/raner-runtime/dist/ 同名文件, 证据链无破坏)。
- 恢复步骤(未执行): 旧 .cache/raner-runtime 改名保留 → prepare_raner_runtime.py build-plan --execute(lock 不变 52 行, wheelhouse 本地已齐, --no-index 全程无网络) → launcher 以 --worker-script run_raner_smoke_attempt_with_distro_check.py + --wsl-distro-check 发起。
- Registry: 从未创建(首次 attempt 为 not_launched, 无 commit); attempt_id 6d726876eafa46c5a1e5b8def1f83533 未被消费。
