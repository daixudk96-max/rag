---
phase: 16-raw-corpus-entity-layer
plan: 12
type: execute
wave: 2
macro_wave: W4
depends_on: [16-07]
requirements: [R-OKF-06]
files_modified:
  - verification/phase16-raw-corpus-entity-layer/build_raner_mirror.py
  - tests/llamaindex_runtime/entity/test_raner_mirror_builder.py
  # NOTE: the plan also lists raner_mirror_manifest.json / raner_mirror_evidence.md.
  # Neither exists in the repo: both are produced ONLY by an authorized gate run,
  # which was never authorized here. They are intentionally NOT present.
summary:
  - .planning/phases/16-raw-corpus-entity-layer/16-12-SUMMARY.md

key-decisions:
  - "[current 2026-08-09] Task 2 (blocking decision gate, future gate 2) was NOT authorized and remains NOT authorized; the default blocked_not_executed path is the delivered, tested, frozen contract. The separate single-use live mirror-creation authorization boundary is independent of the digest correction."
  - "[historical 2026-08-07 — superseded 2026-08-09 by Task #210, see the addendum] The frozen production manifest was pinned verbatim; its 63-char special_tokens_map.json digest was never 'fixed' and no nibble was guessed, so the authorized production path failed closed with manifest_invalid before any downloader/target/evidence."
  - "[current 2026-08-09 post-correction] Task #210 authoritative digest correction: the bounded single-file verification was separately authorized and consumed exactly once, anonymously retrieving only the frozen-revision special_tokens_map.json (150 bytes, JSON object with 7 keys) under a 16 KiB bounded read with no proxy/token/cookie/credential/SDK/retry/cache and no retained file; the authoritative SHA-256 is 7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150. Both production manifests pin this digest identically; exact 64-lowercase-hex validation remains fail-closed; deliberately malformed fixture manifests still fail before downloader construction; a valid authorized production binding can now reach downloader construction."
  - "[historical 2026-08-07, partially superseded] MirrorBuilder.build is a pure injectable seam (tiny manifest + fake Downloader + caller tmp_path); the default NeverDownloader always fails closed. The original claim that it was 'unreachable for the current frozen manifest' is superseded by the 2026-08-09 correction: an authorized valid manifest binding now reaches downloader construction, but the default NeverDownloader still fails closed on any download call."
  - "[current 2026-08-09] All artifact/output creation is exclusive (no-overwrite xb/x) and identity-safe: st_dev/st_ino identity and builder ownership are separate; only identity-proven owned objects are ever removed."

requirements-completed: [R-OKF-06]

duration: "multi-round TDD + coordinator verification + single code review + single security review (2026-08-07) + Task #210 authoritative digest correction (2026-08-09), all recorded below"
completed: 2026-08-07
corrected: 2026-08-09
---

# Phase 16: Plan 12 Summary

**单次授权只读 RaNER 离线 Mirror Builder（gate 2）——local/static/default-blocked 实现 COMPLETE；production mirror / live acceptance 仍 BLOCKED；Phase 16 仍 OPEN/EXECUTING，Wave 2 未完成（closeout 另由 Task #186 完成）**

## 状态边界（Status Boundaries）

- **Plan 16-12 local/static/default-blocked 实现 COMPLETE**：`build_raner_mirror.py` 与 `test_raner_mirror_builder.py` 已按 frozen contract 实现并通过 TDD / coverage / structural verifier / ownership probes / code review / security review。**2026-08-09 Task #210 修正后**：权威 `special_tokens_map.json` digest 已按 Task #210 修正为 `7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`（见文末 addendum）；两个生产 manifest 均原样 pin 该 64-hex digest；严格 SHA-256 校验仍 fail-closed。
- **Production mirror acceptance 仍 BLOCKED**：digest 修正**不代表** mirror 创建已授权或已执行。当前授权仍不覆盖真实 ModelScope mirror 创建/导入/下载/加载/推理；需要另行人类授权单次 mirror-build gate（~2.26 GB）。不得声称 Phase 16 或 Wave 2 已关闭。
- **Phase 16 仍 OPEN / EXECUTING**；Wave 2 closeout 另由 **Task #186** 完成；本 plan 不进入 Wave 3 或任何 live gate。
- **无真实模型/网络/持久化**：没有 ModelScope import/download/load/inference、没有网络模型访问、没有 Docker、没有 PostgreSQL/外部 DB、没有 C2、没有 commit/push。
- **无凭据**：未读取/打印/记录/持久化任何 credential value 或 connection value；变量名仅以守卫约束文字出现在 canonical selector 中。
- **未提交、不宣称 clean worktree**：全部文件保持 uncommitted；本文件不宣称 git cleanliness。

## Task #186 Wave 2 Closeout（post-plan closeout 状态修正）

- **本 plan 当时**（Task #186 之前）：16-12 local/static/default-blocked 实现 COMPLETE，但 scheduler Wave 2 尚未 close；Wave 2 closeout 当时预留由 Task #186 完成。
- **Task #186 后**：scheduler Wave 2 的已授权 local/static/default-blocked 范围（16-06/16-08/16-12）已整体收尾——coordinator fresh combined selector **273 passed in 3.95s**（16-06 focused 83 + 16-08 focused 143 + 16-12 focused 47 = 273，完整 12-variable env-clean）。这是 **Wave 收尾，不是 Phase 16 closure**。
- 16-12 的真实 gate task（Task 2：单次授权 ModelScope mirror 创建）**未授权**；production mirror acceptance 仍 **BLOCKED**：**[historical 2026-08-07 — superseded 2026-08-09 by Task #210]** `special_tokens_map.json` 权威 digest 曾仅 63 lowercase hex（`763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`），不猜测/补齐 nibble，严格 SHA-256 fail closed，`runtime_compatibility_id=None`。**[current 2026-08-09]** 权威 digest 已修正为 64-hex `7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`（两个生产 manifest 均原样 pin；严格 SHA-256 校验仍 fail-closed；授权且有效 binding 现在可到达 downloader 构造，但默认 NeverDownloader 仍对任何下载 fail-closed），`runtime_compatibility_id` 仍为 `None`（由 gate 3 单独授权决定）。本修正只更新状态，不改写本 plan 原始 TDD/coverage/review 证据与结论；Task #186 的最终 COMPLETE 判定由协调器 fresh re-read/verify 决定。

## 计划身份（Plan Identity）

- Plan **16-12**，scheduler **wave 2**，macro **W4**，requirement **R-OKF-06**，depends_on **16-07**（只读离线 mirror loader 硬化）。
- Type：`execute`；Task 1 为 auto 实现；Task 2 为 blocking decision gate（未来 gate 2，单次授权 ModelScope mirror 创建）。Task 2 未获得授权，故 delivered 契约即默认 `blocked_not_executed` 路径。

## 授权范围（Authorization Scope）

**当前授权仅覆盖**：
- 静态 / default-blocked runner（`build_raner_mirror.py`）；
- 本地纯测试（`test_raner_mirror_builder.py`）；
- 注入的 fake `Downloader`；
- 临时目录（caller-controlled `tmp_path` target/output）。

**不覆盖**：真实 ModelScope mirror 创建、导入、下载、加载或推理；网络模型访问；Docker；PostgreSQL；外部数据库；C2；commit；push。

## TDD Evidence

Selector（focused，与 16-07/16-08 一致的完整 env guards；launcher 在 `pytest` 与 `python -m pytest` 间变化，语义等价）：

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_raner_mirror_builder.py -q
```

| Stage | Result | Detail |
|---|---|---|
| **RED** | collection FileNotFoundError | 先写测试、runner 尚不存在；test module 在 import-time 通过 `importlib.util.spec_from_file_location` 建立 spec/module，随后 `spec.loader.exec_module(module)` 尝试打开尚不存在的 `build_raner_mirror.py`，由此抛出 `FileNotFoundError` 并使 pytest collection 中止。**不得虚构或声称精确 RED 测试数量**——collection 在测试计数前即中止。 |
| **GREEN（首个完整）** | `47 passed` | 同一 focused selector 首次完整通过。**tests 在首个完整 GREEN 时冻结**。 |
| **REFACTOR / hardening / final runs** | 冻结不变 | 测试断言 hash 从首个完整 GREEN 起至所有 REFACTOR/hardening/final runs **未改变**。 |

**Frozen test（首次 GREEN 时冻结，全部 REFACTOR/hardening runs 均不变）：**

- `test_raner_mirror_builder.py` — **709 行**，sha256 `99a4edffcb995a765f7058e53dfdfb815ae26e889b9a2698e7e80110b73e4e59`

## 最终稳定实现（Final Stable Implementation）

- runner `build_raner_mirror.py` — **798 行**。
- 最大函数 `_run_build` — **恰好 50 行**（AST `end_lineno - lineno + 1`）；**无 >50 行函数**（`over_50=[]`）。
- **std-lib only**：`hashlib` / `json` / `os` / `stat` / `dataclasses` / `pathlib` / `types` / `typing` / `collections.abc`；**无 modelscope/torch/transformers/tokenizers/sentencepiece/jieba import**（仅 2 次 `os.environ` 读取：授权 gate `OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED` 与 root `RAG_NER_MIRROR_ROOT`，后者仅在授权后读取；无 env 枚举/复制）。
- artifact 使用 **`xb`**（exclusive、no-overwrite、no-follow）；output 使用 **`x`**（exclusive）。
- **repo 中真实 `raner_mirror_manifest.json` / `raner_mirror_evidence.md` 均不存在**（仅在授权 gate run 时才会产生）。

## 默认 gate（Default Gate）

- 无精确授权值（`OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED` 必须等于 `"1"`）时：stdout **恰好** `blocked_not_executed\n`、**非零退出**、**stderr 空**。
- 授权检查发生在 **root lookup、manifest validation、SDK/downloader、目录/文件创建之前**（`main()` 第一行即检查授权，其后才读 root、再验 manifest、再构造 builder）。
- 默认路径零下载、零 heavy import、零 root lookup、零目录/文件创建。

## 生产绑定 anomaly（Production Binding Anomaly）— historical 2026-08-07, superseded 2026-08-09

> **[historical point-in-time as of 2026-08-07 — superseded by Task #210 on 2026-08-09, see the addendum below]** This section records the original 63-character anomaly and the pre-correction fail-closed behavior. It is preserved verbatim as historical evidence; it is NO LONGER the current production binding.

- `special_tokens_map.json` 的权威 digest 只有 **63 个 lowercase hex 字符**（`763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`，与 16-07 记录一致）；严格 SHA-256 validator 要求**恰好 64 个 lowercase hex**，因此 fail closed。
- **不猜测、不补齐 nibble**；生产 manifest binding 原样 pin 住，永不"修复"。
- **授权但使用当前生产 manifest** 时：stdout **恰好** `manifest_invalid\n`、**非零退出**、**stderr 空**、**root 未创建**、**无 repo manifest/evidence**（`_validated_manifest` 在构造 downloader/target 之前即失败）。
- 默认 `NeverDownloader` 对任何下载调用 fail closed（raise MirrorBuildError），且在当前 frozen manifest 下不可达（`main` 在到达 downloader 前即返回 `manifest_invalid`）。

## 生产绑定（Production Binding）— current 2026-08-09 post-correction

- **Task #210 修正后的权威 digest**：`7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`（64 lowercase hex）。修正后该 digest 是当前 production binding；旧的 63 字符值**仅**作为明确标注的 historical point-in-time 记录保留。
- **两个生产 manifest 均原样 pin 同一 digest**：`llamaindex_runtime/entity/offline_mirror.py`（line 83）与 `verification/phase16-raw-corpus-entity-layer/build_raner_mirror.py`（line 128）完全一致。生产 manifest 现在能通过校验。
- **精确 64-lowercase-hex 校验仍 fail-closed**；故意构造的 malformed fixture manifests 仍在 downloader 构造前失败（`manifest_invalid`）。
- **未授权行为仍 `blocked_not_executed`**；**有效授权的 production binding 现在可到达 downloader 构造**（默认 `NeverDownloader` 仍对任何下载调用 fail closed；真实 mirror 创建仍待单独授权）。

## 本地安全语义（Local Security Semantics）

- **Exclusive create**：artifact 用 `xb`、output 用 `x`，任何已存在即 fail closed，绝不覆盖 caller 文件。
- **Identity 与 ownership 分离**：`st_dev`/`st_ino` identity 对 caller-existing 与 builder-created 目录**均**捕获；**仅** build 创建的目录携带 owned record。rollback/chmod/目录复验都以 dev/ino 匹配为准，pathname 从不单独作为 authority。
- **Replacement / chmod / lstat / type / write-bit 一律 fail closed**：identity 不匹配、symlink/reparse、类型变化、读-only chmod 失败或写位未去除均 raise。
- **只清理 identity-proven owned objects**：`_remove_owned_file` 仅在 identity 仍匹配且为 regular file 时移除；`_remove_dir_if_owned_empty` 仅对 builder-created 且仍 owned 且空目录 rmdir。
- **不递归删除 target**；**不删除 caller/foreign/replacement objects**（预检后出现、racing replacement、foreign child 一律存活）。
- **成功后 artifacts 与 target 去除全部写位**（`_NO_WRITE_BITS = S_IWUSR|S_IWGRP|S_IWOTH`，mandatory fail-closed）。
- **output identity capture failure 的有意行为**：若 `_ensure_output_dir` 在捕获 identity 前失败，已可靠拥有的 target（owned record 已捕获）会被清理；而未验证 identity 的空 output 目录被**保留**——这是 ownership-safe 的设计（从未确认 owned 的对象绝不被删除）。

## 最新 coordinator verification（不复跑；旧 87% 不是最终覆盖率）

- **focused tests**：`47 passed in 2.17s`
- **combined frozen selector + repository-external adversarial probes（branch coverage）**：`47 passed in 3.08s`；**422 statements, 67 missed, 118 branches, 25 partial, 83% coverage**
- **Ruff**：`All checks passed!`；runner **`1 file already formatted`**
- **CLI verifier**（default blocked 与 authorized manifest_invalid 的 stdout/stderr/exit code）、**structural verifier**、**ownership/atomicity probes**、**extra identity/replacement probes**、**specific refactor regression probe** 均通过；各 verifier/probe 的 key 输出见下（仅列出已给定数值，不伪造未提供的数字）。

### specific regression probe（output identity capture failure）

- `output_capture_failure_result=blocked`
- `output_capture_failure_downloader_calls=0`
- `output_capture_failure_target_exists=False`
- `output_capture_failure_output_exists=True`

### structural verifier

- `runner_lines=798`
- `test_lines=709`
- `test_sha256=99a4edffcb995a765f7058e53dfdfb815ae26e889b9a2698e7e80110b73e4e59`
- `max_function=('_run_build', 50)`
- `over_50=[]`
- `os_environ_reads=2`
- `exclusive_artifact=True`
- `exclusive_output=True`
- `repo_manifest_exists=False`
- `repo_evidence_exists=False`

## 审核边界（Review Boundaries）

- 同一稳定内容**仅执行一次 Sonnet code review 和一次 Sonnet security review**；两者均 **APPROVE**。
- code review 的**唯一 MEDIUM** 经**同一 reviewer 仅作 adjudication**，结论 **`no_change_needed`**：frozen contract 明确要求 caller-selected empty mirror root 在成功后也只读，因此该发现无需改动。
- 最终 unresolved：**CRITICAL=0、HIGH=0、MEDIUM=0**。
- **不存在第二次 code review**；security review 为独立、一次。

## LOW/INFO residual notes（记录，不作为已修复或 blocker）

- **same-user TOCTOU residual**：路径安全是 pathname-based、fail-closed，但非 capability-rooted 且非完全 TOCTOU-free。
- **无 fsync/rename crash atomicity**：artifact 与 output 均为直写，无 rename-commit；崩溃一致性与并发替换不在本 bounded 任务范围。
- **identity capture failure 可能留下空目录**：如上所述，未验证 identity 的空 output 目录被有意保留。
- **未来若生产 manifest 修复而 `main` 仍使用 `NeverDownloader`**：授权路径将因 `NeverDownloader` 直接 raise 而 traceback——需另行人类授权并注入真实 downloader 才能走通。**[historical 2026-08-07 note — the 'if the manifest is fixed' premise has since materialized on 2026-08-09 (Task #210): the manifest is now corrected, and the note stands for the downloader-injection requirement]**。
- **evidence 文件名为 `.md` 但内容为 deterministic JSON**（`_canonical_json`，仅 status/model/revision/artifact_digest/files，无 root path/URL/query/token/credential/connection/database 文本）。
- **16-12 PLAN 的 `config.py` key-link 不准确**：runner 并不读取 `llamaindex_runtime/config.py`；root env 直接在 `main()` 中读取（`RAG_NER_MIRROR_ROOT`）。

## 明确未执行（Not Executed）

ModelScope import / download / load / inference、network model access、Docker、PostgreSQL、external DB、C2、commit、push —— 全部**未执行**。

## 明确未生成（Not Produced）

- **没有**真实 `raner_mirror_manifest.json` / `raner_mirror_evidence.md`（它们仅在授权 gate run 中产生；Task 2 未授权，故未生成）。

## 文件清单（Files）

- `verification/phase16-raw-corpus-entity-layer/build_raner_mirror.py`（plan 声明的 files_modified；已存在，uncommitted）。
- `tests/llamaindex_runtime/entity/test_raner_mirror_builder.py`（plan 声明的 files_modified；已存在，uncommitted）。
- `raner_mirror_manifest.json` / `raner_mirror_evidence.md` —— plan files_modified 中列出但**未生成**（见上）。
- 本 `16-12-SUMMARY.md` 为**唯一新建文档**；其余文件均保持未修改。 [historical point-in-time as of the original 16-12 snapshot (2026-08-07) — since superseded by later Wave closeouts and the Task #210 addendum in this same file]

## 结论（Conclusion）

- **Plan 16-12 在当前授权的 local/static/default-blocked 范围内完成**：默认 gate、生产 binding fail-closed、注入式安全 build 语义均已由 frozen tests + coordinator probes 验证。
- **[historical 2026-08-07]** Production mirror acceptance 当时 BLOCKED：需要（a）修正权威 `special_tokens_map.json` 为 64-hex digest，且（b）另行人类授权真实 ModelScope mirror 创建；两者当时均未发生。**[current 2026-08-09]**（a）已由 Task #210 完成——权威 digest 修正为 `7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150` 且两个生产 manifest 均原样 pin，校验 fail-closed 保持；（b）**仍未发生**——真实 ~2.26 GB ModelScope mirror 创建仍待一项新的独立单次授权。因此 **production mirror acceptance 仍 BLOCKED**（gate 2：`blocked_not_executed`）。
- **Phase 16 仍 OPEN / EXECUTING**；**Wave 2 closeout 另由 Task #186 完成**；本 plan **不进入 Wave 3 或任何 live gate**。
- 不宣称 clean worktree；无任何真实 mirror / manifest / evidence 生成。Task #210 是权威 digest 修正（文档/状态同步与 bounded 单文件验证），不是 Wave/Phase closure，也不是 mirror 创建授权。

## Task #210 authoritative digest correction addendum（2026-08-09）

> **This addendum records the Task #210 authoritative Gate 2 digest correction and its non-live verification. It SUPERSEDES the 63-character digest anomaly as a current production binding and as a current blocker for the manifest-validation step — but it does NOT supersede the separate live mirror-creation authorization gate. The actual ~2.26 GB Gate 2 mirror creation was NOT authorized and NOT executed.**

### 1. Bounded single-file verification (authorized, consumed exactly once)

- **Separately authorized and consumed exactly once.** It anonymously retrieved only the frozen-revision `special_tokens_map.json`.
- **Payload facts:** 150 bytes, JSON object with 7 keys; read under a **16 KiB bounded read**.
- **Isolation facts:** no inherited proxy (`ProxyHandler({})`), no token/cookie/credential/SDK/retry/cache, **no retained file**.
- **Authoritative SHA-256:** `7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`.
- **Supersession of the prior 63-char value:** the prior 63-character value (`763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`) was missing the `8` after the initial `763`; it is superseded as a **current production binding** but may remain in clearly labeled **historical point-in-time** sections of this document.

### 2. Task #210 TDD correction scope (exactly five uncommitted/untracked Python files — NOT edited here)

| File | Lines | Role |
|------|-------|------|
| `llamaindex_runtime/entity/offline_mirror.py` | 378 | production manifest pin (digest at line 83) |
| `verification/phase16-raw-corpus-entity-layer/build_raner_mirror.py` | 796 | gate-2 builder production manifest pin (digest at line 128) |
| `tests/llamaindex_runtime/entity/test_offline_mirror.py` | 797 | offline-mirror tests |
| `tests/llamaindex_runtime/entity/test_raner_mirror_builder.py` | 713 | builder tests |
| `tests/llamaindex_runtime/entity/test_raner_mirror_modelscope_downloader.py` | 777 | modelscope-downloader seam tests |

- The corrected digest is **pinned identically in both production manifests**.
- **Exact 64-lowercase-hex validation remains fail-closed.**
- **Production manifest now validates**; **deliberately malformed fixture manifests still fail before downloader construction**; **unauthorized behavior remains `blocked_not_executed`**; **a valid authorized production binding can now reach downloader construction**. No actual downloader/network/model action occurred in tests.

### 3. Genuine RED / GREEN / final evidence

- **Genuine RED:** `7 failed, 124 passed, 1 skipped`.
- **GREEN / final focused:** `131 passed, 1 skipped`.
- **Fresh coordinator final full entity selector:** `678 passed, 1 skipped`.
- **Ruff clean; py_compile clean; scoped Black clean.**
- **File sizes:** offline_mirror 378; builder 796; test_offline_mirror 797; test_raner_mirror_builder 713; test_raner_mirror_modelscope_downloader 777.
- **Only >50-line function:** pre-existing untouched `test_loaded_mirror_invariants` at 56 lines.

### 4. Reviews (exactly one each, Task #210 only)

- Exactly **one Sonnet Python code review** and exactly **one Sonnet security review** were performed **for Task #210 only**.
- **Both verdicts APPROVE; each has CRITICAL=0, HIGH=0, MEDIUM=0, LOW=0.**
- The unchanged Task #209 downloader seam was **not re-reviewed**.

### 5. GitNexus distinction (impact vs whole-worktree risk)

- **Exact prior impacts** for `FROZEN_MANIFEST`, `_RAINER_MIRROR_MANIFEST`, and the relevant changed test symbols were **LOW with 0 direct dependants, 0 affected processes, 0 affected modules**.
- **Fresh global `detect-changes --scope unstaged --repo rag`** reported **HIGH: 31 tracked files, 220 symbols, 9 processes**. This is **whole dirty-worktree risk**, not Task #210 scope. **All five Task #210 files are untracked and therefore excluded from that tracked-only detection.**
- **Do NOT claim a clean worktree or a commit-scope pass.**

### 6. Gate / current-state honesty

- The **actual approximately 2.26 GB Gate 2 mirror creation was NOT authorized or executed**.
- `raner_mirror_manifest.json` and `raner_mirror_evidence.md` **do not exist**.
- No mirror, staging artifact, model load, inference, DB, Docker, C2, commit, or push occurred.
- **Gate 2 remains `blocked_not_executed`** pending a **NEW independent single-use mirror-build authorization**.
- **Gate 3 remains `blocked_not_executed`**, and **`runtime_compatibility_id` remains `None`** until a separately authorized real smoke.
- **Gate 4 remains `blocked_not_executed`** downstream.
- **Gate 1 remains executed/verified**; **C2 remains `skipped_not_entered` and disabled**.
- **Phase 16 remains OPEN/EXECUTING; `nyquist_compliant: false`**; this correction is **not** Wave/Phase closure.
- **D4 remains frozen until Phase 19**; **Phase 20 still needs separate pilot authorization + human G6 Go/No-Go**.
- **No commit/push authorized.**

### 7. Verification deviation (transparent, not overstated)

- One local **Black line-range check accidentally cleared nonexistent `OKF_E2B_MIGRATION_TEST_DATABASE_DISPOSABLE`** and omitted `OKF_E2B_MIGRATION_TEST_AUTHORIZED`.
- It was **formatter-only** and performed **no DB/network/SDK/credential/live action**.
- **Every subsequent GitNexus, diff, formatter, lint, compile, and pytest command restored the exact 12-variable guard.**
- Recorded transparently; **NOT labeled a live security failure**.

## Gate 2 mirror-build SUCCESS addendum (2026-08-09)

> **This addendum records the authorized single-use Gate 2 ModelScope RaNER mirror build, which ran to SUCCESS on 2026-08-09 after the Task #210 digest correction. The earlier statements in this document asserting that `raner_mirror_manifest.json` / `raner_mirror_evidence.md` do not exist and that Gate 2 remains `blocked_not_executed` are SUPERSEDED as of this addendum. Gate 3 and Gate 4 remain `blocked_not_executed` pending separate authorizations; Phase 16 remains OPEN/EXECUTING.**

### 1. Authorization (consumed exactly once)

- A fresh single-use authorization (`OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED=1`, "授权重新构建") was granted on 2026-08-09 after the Task #210 digest correction and the static suite passed (131 passed, 1 skipped).
- The authorized build was executed **exactly once** and is now **consumed**; no auto-rerun.
- Target: the user-confirmed explicit local target `.cache/raner-mirror` (mirror root resolved via `RAG_NER_MIRROR_ROOT`).

### 2. Build result

- **Status: `ok`; exit code 0.**
- Model: `iic/nlp_raner_named-entity-recognition_chinese-large-generic`; revision `4d15e5b1427685cfd2cfc416903890219dc0582c`.
- All seven frozen files downloaded and verified by strict SHA-256 against the corrected manifest; the corrected `tokenizer_config.json` digest `5c07c2bf4f3f9dda349358194311cb433eebc22b95bddba813c144b206a30e89` matched the real downloaded file.
- All seven mirror files were hardened read-only on Windows (write bits cleared; read-only verification passed).

### 3. Published artifacts (now EXIST)

- `verification/phase16-raw-corpus-entity-layer/raner_mirror_manifest.json` (618 B): the seven file-to-digest mapping, including `tokenizer_config.json`=`5c07c2bf4f3f9dda349358194311cb433eebc22b95bddba813c144b206a30e89` and `special_tokens_map.json`=`7638f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150` (Task #210 authoritative).
- `verification/phase16-raw-corpus-entity-layer/raner_mirror_evidence.md` (852 B): deterministic JSON with `status=ok`, model, revision, `artifact_digest`, and the seven digests only (no root path / URL / credential / database text).
- **Evidence integrity confirmed:** `canonical_json_sha256(manifest)` = `1c53105d095c7839446332d34f5693b6dfc56b286ed19de2ab27b68905895424` == evidence `artifact_digest` -> match True.
- Mirror file sizes verified on disk (all read-only): `pytorch_model.bin` 2,239,833,895 B; `tokenizer.json` 17,082,661 B; `sentencepiece.bpe.model` 5,069,051 B; `config.json` 1207 B; `configuration.json` 175 B; `special_tokens_map.json` 150 B; `tokenizer_config.json` 559 B.

### 4. Current gate state (updated)

- **Gate 2: now EXECUTED / status `ok`** — the ~2.26 GB mirror exists at the authorized local target. `blocked_not_executed` no longer applies to the mirror-creation step.
- **Gate 3 (`OKF_E2B_RANER_SMOKE_AUTHORIZED`): still `blocked_not_executed`** — the real RaNER load smoke / resource measurement requires its own separate single-use authorization; `runtime_compatibility_id` remains `None` until then. The built read-only mirror is the input for this gate.
- **Gate 4: still `blocked_not_executed`** downstream.
- **Gate 1 remains executed/verified; C2 remains `skipped_not_entered` and disabled.**
- **Phase 16 remains OPEN/EXECUTING (`nyquist_compliant: false`);** this is a Gate 2 build success, NOT a Wave/Phase closure.
- **D4 frozen until Phase 19; Phase 20 needs separate pilot authorization + human G6 Go/No-Go.**
- **No commit/push authorized;** all files remain uncommitted/untracked.

### 5. No secrets

- No `DATABASE_URL` or credential value was read, printed, logged, or persisted into `.planning` artifacts; the 12-variable env-clean guard was applied to every non-database Bash command.

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 12*
*Completed: 2026-08-07*
*Corrected: 2026-08-09 (Task #210 authoritative digest correction addendum; Gate 2 mirror-build SUCCESS addendum)*
