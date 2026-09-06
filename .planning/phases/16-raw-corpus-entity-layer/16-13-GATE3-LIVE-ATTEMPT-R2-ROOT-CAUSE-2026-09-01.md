# Gate 3 Live Attempt R2 — Root Cause Adjudication (2026-09-01)

status: DIAGNOSTIC COMPLETE — LIVE GATE HONESTLY FAILED; USER DECISION REQUIRED

## 1. Scope and authorization

- User authorization chain: '解除数字数据库禁令，然后继续吧' (2026-08-31, Phase 16 DB gate) then '1然后3' where 3 = one real RaNER live smoke attempt. WSL measurement skipped by separate user decision (see 16-13-GATE3-WSL-SKIP-W2-REPLAN-2026-08-29.md).
- Coordinator (non-implementing) performed all diagnostics with read-only probes plus one real authorized attempt. No production/test code was edited. No frozen module was edited.

## 2. Attempts recorded (append-only registry, each honestly terminal)

| attempt_id | outcome | root cause layer |
|---|---|---|
| 13a36e8f7cbd42d28b5c6433b5165fce | execution_failed (supervisor_observed_exit, exit 1) | isolated venv held the 2026-08-29 repo wheel (sha af4f8dea…) missing W2 `_wsl_distro`; fixed by rebuilding repo wheel (sha 323b9cdf…) + re-provision |
| b25e312fdc524c6e9d87578c822ffa21 | execution_failed (19s, sanitized) | modelscope undeclared runtime deps: `simplejson`, then `sortedcontainers` missing from the 52-package metadata closure (lazy imports in modelscope fileio/jsonplus). Fixed: pip download both wheels into the wheelhouse + append to requirements.lock (54 lines), full re-provision (build cb7d9aff…) |
| b6a565e3189a40468f8481f48cb102fa | execution_failed (model loaded, CRF pipeline ran) | modelscope 1.39.1 preprocessor label-mask defect for unspaced Chinese + frozen fixture mismatch (see below) |

Registry: verification/phase16-raw-corpus-entity-layer/raner_smoke_attempt_registry.jsonl — 9 lines, one terminal per attempt, never rewritten (contract-compliant).

## 3. Root cause chain (three layers, all independently probed)

### Layer 1 — model infrastructure: WORKING

- load_mirror: all 7 files SHA-256 verified, artifact_digest 1c53105d095c7839446332d34f5693b6dfc56b286ed19de2ab27b68905895424, 1.6s.
- load_model: pipeline(Tasks.named_entity_recognition, model=mirror_root, device='cpu') loads ModelForTokenClassificationWithCRF (2.24GB pytorch_model.bin), all checkpoint weights used.
- The task-model CRF head decode works when given a correct label_mask.

### Layer 2 — modelscope 1.39.1 preprocessor defect (repo-dependent, systemic for Chinese)

- pipe.preprocess(text) returns `label_mask` summing to **1** over 512 positions (expected ≈ 7 for the 13-char fixture text) and a single merged offset (0, 15).
- Cause: the preprocessor resolves to the XLMRobertaTokenizer SLOW path; modelscope `get_label_mask_and_offset_mapping_XLMRobertaTokenizer` (token_classification_preprocessor.py L438-462) treats `▁`-prefixed pieces as word starts. Unspaced Chinese yields essentially one `▁`-piece, so label_mask degenerates. The fast-tokenizer path has the same collapse because HF word_ids treat the whole unspaced string as ONE word.
- Forcing the fast tokenizer (`Preprocessor.from_pretrained(root, use_fast=True)`) still yields output `{'output': []}` — the defect is in the per-word masking semantics, not merely tokenizer speed.
- The correct invocation (proven by probe): `add_special_tokens=True` + per-char label_mask (masking `<s>`/`</s>`) + `model.head.decode(logits, label_mask)` + fast-tokenizer offsets. The frozen pipeline cannot be driven into this state through its public constructor without a code change in non-frozen repo code.

### Layer 3 — frozen fixture vs real model (THE acceptance-contract finding)

Probing with the correct invocation (evidence: .tmp/raner_pred.json, sha256 9df1235c8d33e3c9abc905fcd4c4e3fd485188b775a4d6c4ddfe08d8dae43a3a) gives the model's true tokens/predictions for `李雷在北京使用华为Mate60`:

| token span | model (correct decode) | frozen fixture | verdict |
|---|---|---|---|
| 李雷 (0,2) | B-PER E-PER → PER(0,2) | PER(0,2) | MATCH |
| 在北京 (2,5) | O | LOC(3,5) | MISMATCH |
| 华为 (7,9) | B-PROD(7,…) | CORP(7,9) | MISMATCH |
| Mate60 (9,15) | E-PROD ends 13; 60 = O | PROD(9,15) | MISMATCH |

- The frozen `_FIXTURE_SIGNATURES=(('PER',0,2),('LOC',3,5),('CORP',7,9),('PROD',9,15))` was authored in Task #218 and explicitly never validated against a real model (16-11: 'no real RaNER model wired').
- Even with a fully correct integration, the live gate would still fail the fixture check honestly (model does not produce LOC for 北京 nor CORP for 华为 in isolation).

## 4. What is NOT the problem

- Model weights/mirror: artifact_digest 1c53105d… verified on every load; SHA-256 per file OK.
- Worker/supervisor/registry/auth/token flow: 3rd attempt reached real inference; all lifecycle records honest.
- The adapter's offset/shape validation: it correctly fail-closed on empty chunks (0 mentions → fixture mismatch → LiveSmokeError).

## 5. Decision points (user; coordinator cannot amend contracts or edit code itself)

1. Authorize a bounded TDD remediation: fix the invocation layer in non-frozen repo code (`offline_mirror.load_model` / adapter glue; GitNexus impact first) so the pipeline produces the model's TRUE entities; the fixture check would then fail HONESTLY with real entities recorded → live gate remains execution_failed unless the fixture is amended.
2. Same as 1, and additionally decide the fixture question separately: either keep `_FIXTURE_SIGNATURES` as the frozen acceptance contract (gate stays failed) or authorize a contract amendment to re-baseline the fixture from a human-reviewed trusted model run (NOT derived from this diagnostic alone).
3. Accept the current three execution_failed records as the honest terminal state; document the residual gap; Gate 3 remains failed; Phase 16 record carries an explicit NON-CLAIM.

## 6. Artifacts

- Diagnostic probes archived: .tmp/gate3_diag_probes/step1..8_code.py
- Prediction evidence: .tmp/raner_pred.json (sha256 9df1235c8d33e3c9abc905fcd4c4e3fd485188b775a4d6c4ddfe08d8dae43a3a)
- Launcher logs: .tmp/gate3_live_attempt3.log, .tmp/gate3_live_attempt4.log
- requirements.lock: 54 lines (52 + simplejson==4.1.2 + sortedcontainers==2.4.0, both hash-pinned, wheels in .cache/raner-wheelhouse)
- Provisioned runtime: build_id cb7d9affca0d4e819ed4d59a4766b97a, lock_raw_digest bf12ba2cb95319456cfc621f283603c6689c69bcb0c9059fe44ed4b389ba546d, repo wheel 323b9cdf28637e2659499c465f7363d0ce72a65cc0bc8f4b0ccf0f5329e2b8ac


## 7. Independent verification (user-directed subagent, 2026-09-01)

Per user decision (option 3: no code/test changes; independent verification delegated to a read-only subagent under coordinator direction), subagent 408ad347-b3df-458c-b514-242984c15554 independently recomputed every claim.

Result: APPROVE_WITH_NOTES — CRITICAL=0 HIGH=0 MEDIUM=1 LOW=0

| Check | Verdict | Key evidence |
|---|---|---|
| C1 registry | PASS | exactly 9 JSONL lines; attempt ids exactly {13a36e8f…, b25e312f…, b6a565e3…}; per attempt exactly one launch_committed / worker_started / execution_failed (supervisor_observed_exit, worker_exit_nonzero, exit 1); no rewrites (identical after pytest re-check) |
| C2 prediction evidence | PASS | .tmp/raner_pred.json sha256 9df1235c8d33e3c9abc905fcd4c4e3fd485188b775a4d6c4ddfe08d8dae43a3a; 9 token/label/offset pairs exact |
| C3 lock+wheelhouse | PASS | 54 hash-pinned lines; line 53 simplejson==4.1.2 (c79ab4ac…f001f), line 54 sortedcontainers==2.4.0 (a163dcaede0f1c021485e957a39245190e74249897e2ae4b2aa38595db237ee0); wheel file hashes match lock lines |
| C4 runtime | PASS | dependency_provenance.json (parsed 2 ways): build_id cb7d9affca0d4e819ed4d59a4766b97a, lock_raw_digest bf12ba2cb95319456cfc621f283603c6689c69bcb0c9059fe44ed4b389ba546d; import_proof.json parses, proof_kind raner_runtime_import_tokenizer_offline |
| C5 planning doc | PASS | this file, 68 lines, contains Layer 1/2/3 + evidence hashes |
| C6 no source edits | PASS | all 9 watched file LastWriteTimes < 2026-09-01T00:00+08:00 (latest 2026-08-31 10:35:36); 0 step*_code.py in the verification dir; 8 archived under .tmp/gate3_diag_probes/ |
| C7 test sanity | FAIL (the single MEDIUM) | gate3 pytest = 2 failed, 598 passed, 4 skipped — test_worker_entry.py:208/324 (pre-freeze, 2026-08-12) assert `not REGISTRY_PATH.exists()`; REGISTRY_PATH is this phase's own required registry deliverable, created by the 3 honest attempts; test-suite-vs-deliverable non-hermetic coupling, NOT a code regression |
| C8 repo wheel | PASS | .cache/raner-repo-dist wheel sha256 323b9cdf…b8ac; matches repo_artifact.sha256 inside dependency_provenance.json |

### C7 disposition (recorded, NOT executed — option 3 forbids code/test changes)

The two failing assertions are pre-existing test-environment coupling: the default REGISTRY_PATH file is a legitimate phase deliverable created by authorized live attempts, so `assert not REGISTRY_PATH.exists()` can never pass in this environment again. The worker invariant they intend to prove (the worker never writes the lifecycle registry) is NOT invalidated — C1 shows only supervisor-written lifecycle records. Exemption recorded here per the verifier's remedy option; any future change to test_worker_entry.py (e.g., hermetic temp-registry injection) MUST go through the standard owner+TDD+review chain and must NOT be treated as license to weaken tests.

### 8. User decision (2026-09-01, final — verbatim intent)

User selected option 3 (no further remediation for the fixture/model mismatch) and directed that all future actual verification be delegated to subagents with the coordinator acting as guide/router only. Consequences recorded:

- Gate 3 live smoke = 3 attempts, all honestly terminal (execution_failed × 3); no attempt record rewritten; registry is append-only history.
- The frozen `_FIXTURE_SIGNATURES` remains untouched; the live gate's failure is the honest detection of a fixture authored without real-model validation (16-11: 'no real RaNER model wired') plus a systemic modelscope-1.39.1 preprocessor defect for unspaced Chinese.
- STATE.md updated: status phase16_gate3_live_failed_honest_terminal.
- Residuals for any future session (explicitly NOT authorized now): (a) load_model invocation-layer fix (specials + char-level label_mask + CRF decode, proven working in probes); (b) fixture re-baseline ONLY with explicit contract amendment; (c) hermetic test_worker_entry.py registry seams.
