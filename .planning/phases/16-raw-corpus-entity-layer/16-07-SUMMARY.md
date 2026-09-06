# Phase 16-07 SUMMARY — Read-Only Offline RaNER Mirror Loader (Hardened)

**Status (local implementation / hardening):** COMPLETE — fresh focused tests pass on 2026-08-07 (57 passed, 1 skipped).
**Status (production acceptance):** BLOCKED — the authoritative production manifest digest for `special_tokens_map.json` is 63 lowercase-hex characters (`763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150`), but a SHA-256 is always exactly 64 hex chars. No correct 64-char digest exists locally and none is guessed/fixed here. The production manifest binding is pinned verbatim and `_validated_manifest()` / `load_mirror()` fail closed on it *before any file hashing or model loading*.
**No live smoke was run; `runtime_compatibility_id` remains exactly `None`; no full Phase 16 completion is claimed; no later Phase 16 wave was entered.**
**Date:** 2026-08-07
**Plan:** `.planning/phases/16-raw-corpus-entity-layer/16-07-PLAN.md`
**Selector (all runs, identical):**
```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED python -m pytest tests/llamaindex_runtime/entity/test_offline_mirror.py -q
```

## Hardening TDD Evidence (this session, fresh)

The prior summary claimed the 63-char digest is "accepted structurally" via a length-agnostic validator. That weakened-validator narrative is **superseded**: `_validate_digest` now requires *exactly 64 lowercase hex chars*, so the frozen production manifest is malformed and rejected fail-closed before any file hash.

| Stage | Result | Detail |
|---|---|---|
| **RED (partial state)** | 1 failed, 54 passed, 1 skipped (3.29s) | Captured before any production/test fix. `test_loaded_mirror_invariants` still asserted the old loose contract: its first case expected `runtime_compatibility_id` but got `manifest digest must be a lowercase SHA-256 (64 hex characters)` because `LoadedMirror.__post_init__` validates the manifest binding (production 63-char digest rejected) before the compat-id check. Genuine hardening RED. |
| **GREEN (fixed + new regressions)** | 57 passed, 1 skipped (2.55s, then 2.59s) | Repaired `test_loaded_mirror_invariants` to the hardened contract (fixture manifest, exact-set mismatch, `root/name` path, canonical digest, non-regular leaf, relative root) and added forged/stale re-verification regressions plus a `_modelscope_available` probe unit test. |
| **Full entity dir regression** | 239 passed, 1 skipped (3.28s) | `tests/llamaindex_runtime/entity/` (`test_contracts.py`, `test_merger.py`, `test_segmenter.py`, `test_offline_mirror.py`). Only skip: `test_fifo_as_manifest_file_rejected` (Windows cannot create FIFOs). No regressions. |
| **Coverage** | 96% (164 stmts, 7 miss) | `--cov=llamaindex_runtime.entity.offline_mirror`. The 7 uncovered lines are exclusively the defensive TOCTOU branches in `_open_regular`: `os.open` OSError after a passing `_validate_leaf` (215-216), `os.fstat` OSError (219-221), and the fstat non-regular guard (223-224). None is deterministically triggerable; these are the documented pathname-based TOCTOU gaps. |

New/updated tests this session:
- `_validate_digest`: exactly-64-lowercase-hex acceptance and rejection of 63/65/uppercase/non-hex/non-str (parametrized).
- Production binding pinned verbatim; `_validated_manifest()` and `load_mirror` reject the 63-char entry structurally before any file hash (`test_validated_manifest_rejects_production_binding`, `test_production_load_mirror_fails_closed_before_any_file_hash`).
- Bytes roots rejected (`test_bytes_root_rejected`); symlink/reparse ancestors of a supplied root rejected (`test_symlink_ancestor_of_root_rejected`).
- `LoadedMirror` exact current validated-manifest name set, `root / name` path equality, canonical artifact digest, `runtime_compatibility_id` exactly `None`, and non-symlink regular leaf at construction (`test_loaded_mirror_invariants`, `test_loaded_mirror_symlink_root_rejected`).
- Forged DTO (files escaping root; forged artifact digest) rejected before dependency probe/pipeline (`test_forged_loaded_mirror_cannot_reach_dependency_probe`).
- Mirror mutated on disk after a successful `load_mirror` is rehashed and rejected before dependency probe (`test_stale_mirror_rehashed_and_rejected_before_pipeline`).
- Valid passed `LoadedMirror` is freshly re-verified (a second `load_mirror` on the same root, exactly once) and reaches the fake ModelScope pipeline exactly once (`test_load_model_success_with_fake_modelscope`, which now spies on `load_mirror`).
- `_modelscope_available` probes without importing (`test_modelscope_available_probes_without_importing`).
- Source guards: no whole-file read, no network/download API, no top-level heavy imports; lazy ModelScope imports live only inside function bodies; fresh-process import leaves modelscope/torch/sentencepiece/transformers/tokenizers/jieba absent from `sys.modules`.

## Original First-Implementation TDD Evidence (preserved, superseded where noted)

| Stage | Result | Detail |
|---|---|---|
| **RED** | 1 collection error (FAIL) | `ImportError: cannot import name 'offline_mirror' from 'llamaindex_runtime.entity'` at `tests\llamaindex_runtime\entity\test_offline_mirror.py:51`; the production module did not exist. Exit code 2. |
| **GREEN attempt 1** | 15 failed, 27 passed, 1 skipped | First implementation exposed real bugs: `type(root) is Path` rejecting platform subclasses (`WindowsPath`/`PosixPath`); the strict 64-char digest check rejecting the frozen 63-char `special_tokens_map.json` entry; exact-list membership failing on indented lazy-import lines. |
| **GREEN final (original)** | 43 passed, 1 skipped | Original validator was length-agnostic so the frozen 63-char entry "validated structurally". **This is the narrative superseded by the hardening above**: production now rejects the malformed binding fail-closed before file hashing, per the frozen truth that SHA-256 digests are exactly 64 lowercase hex. |

## Frozen Public Contract Delivered

- **`RAINER_MIRROR_MANIFEST`** — immutable `MappingProxyType`, pinned verbatim from the model-selection manifest (2026-07-13, §1.3):

  | File | SHA-256 (frozen, lowercase) |
  |---|---|
  | `pytorch_model.bin` | `62fbd5cae19c206d2219033f59b0bff9b9216c02471f8d4d96cd155a31e9412b` |
  | `config.json` | `f8740e1a4b8ab43b2932023cb50cdb892084c640f9d80b915142093f3a986396` |
  | `configuration.json` | `2757784508a1700160a96fdf187190a91bde1ee68dd1ed9b1ab70de0eb89a517` |
  | `sentencepiece.bpe.model` | `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865` |
  | `tokenizer.json` | `984b1def3a3be6e7bcc33df5397c52fc77ed8ce49eaba7fc66cf623ae19aabf0` |
  | `special_tokens_map.json` | `763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150` (**63 hex chars — authoritative upstream anomaly, pinned verbatim, never "fixed"**) |
  | `tokenizer_config.json` | `0525bc6493bb897fcd5b9fa2d4ca416c15bf61387c4e975018cde9998e1a5ed7` |

  Immutability is test-pinned; the constant is never weakened. Fixture tests monkeypatch the module's manifest binding to an immutable small fixture manifest with real 64-char SHA-256 hashes while the frozen constant is pinned independently.

- **`_validate_digest`** — requires *exactly 64 lowercase hex characters*; rejects 63/65, uppercase, non-hex, and non-str. The frozen production manifest therefore fails `_validated_manifest()` before any file hash.

- **`LoadedMirror`** — frozen `@dataclass`; `files` is an immutable `MappingProxyType` whose key set must exactly equal the current validated manifest names, each value must equal `root / name`, each path must be a non-symlink regular file at construction, `artifact_digest` must equal `canonical_json_sha256(manifest)`, and `runtime_compatibility_id` must be exactly `None` (the field default is `None`; any non-`None` value is rejected). Per-name re-validation inside `__post_init__` was removed as redundant because the exact-set check already proves every key is a validated manifest name; fail-closed semantics are preserved.

- **`RaNERDependencyError(RuntimeError)`** — typed dependency error.

- **`load_mirror(root=None)`** — explicit local root wins; absent/empty env fails closed on `RAG_NER_MIRROR_ROOT` only. Validates root (non-symlink/reparse directory, including every ancestor component), manifest binding, and every file (regular, non-symlink, exact SHA-256) before returning.

- **`load_model(mirror=None)`** — always re-runs `load_mirror(loaded.root)` immediately before any dependency probe/import and rejects any metadata mismatch (`artifact_digest`, file key set, or any `root/name` path), so a forged or stale `LoadedMirror` can never reach ModelScope. Then probes `importlib.util.find_spec("modelscope")`, raises `RaNERDependencyError` mentioning the `ner` extra when unavailable, and otherwise lazily imports ModelScope and calls `pipeline(Tasks.named_entity_recognition, model=<re-verified mirror root>, device="cpu")` — no hub model id, no revision, no download/cache argument.

## Design Notes

- **Streaming SHA-256:** files are opened `os.open(... | O_NOFOLLOW | O_BINARY | O_CLOEXEC)` and hashed with `hashlib.sha256()` over `os.read(fd, 64 KiB)` chunks; no file is ever read whole (source-guard test rejects `read_bytes`/`read_text`/`.read()`). A >300 KB fixture proves multi-chunk correctness.
- **Path safety (fail-closed, pathname-based):** root must be an absolute real directory that is not a symlink/reparse point; the entire component chain from the filesystem root down is lstat-checked so a symlink *ancestor* of the supplied root is rejected; every manifest entry name is validated as a single safe relative component via `validate_relative_path(..., windows=True)` (rejects traversal, absolute entries, drive prefixes, Windows reserved names); each leaf is lstat-checked for symlink/reparse/non-regular before an `O_NOFOLLOW` open plus `fstat` regular-file confirmation. This is fail-closed but NOT capability-rooted and NOT fully TOCTOU-free: a concurrent attacker able to swap a path component between a check and its open is out of scope for this bounded task (the `_open_regular` fstat guards are the residual defense).
- **Immutability:** `MappingProxyType` for the public manifest and `LoadedMirror.files`; frozen dataclass; deterministic `artifact_digest` via reused `canonical_json_sha256` (sorted-key canonical JSON, order-independent).
- **Zero default import surface:** module imports only stdlib plus pure `entity/contracts.py` and `okf/rooted_open.py` helpers; in-process and fresh-subprocess tests assert `modelscope`/`torch`/`sentencepiece`/`transformers`/`tokenizers`/`jieba` absent from `sys.modules`; a source-level test forbids top-level heavy imports and confirms ModelScope imports live only inside function bodies.
- **Re-verification contract:** `load_model` never trusts a passed `LoadedMirror`; it re-hashes the root and compares trusted metadata before the dependency probe, import, or pipeline call. The success-path test proves a single re-verifying `load_mirror` call precedes exactly one pipeline call; forged-DTO and stale-on-disk tests prove the probe/pipeline is never reached on mismatch.
- **No mutation of the mirror:** the loader only opens files read-only; a test snapshots sizes/bytes before and after and asserts identity.

## Security / Correctness Checks

- No `modelscope`/`torch`/`sentencepiece`/`transformers`/`tokenizers`/`jieba` import at module import time; ModelScope is imported lazily only inside `load_model` after a positive `find_spec` probe.
- No download, network call, hub-identifier fallback, package installation, database, Docker, real model mirror/download/inference, or live smoke. Source-level tests reject `snapshot_download`, `local_files_only`, `requests.`, `urllib.`, `import socket`, `import requests`, and the hub model id string.
- Errors expose no credentials and no unrelated environment state; `DATABASE_URL` and credentials are never read, printed, logged, or persisted. All Bash commands clear the sensitive/authorization env vars with the documented `rtk env -u ...` selector.
- Fail-closed for: missing files, single-byte mismatches, non-directory/unreadable/symlink/reparse roots (including ancestor components), symlink/reparse/non-regular leaves, traversal/absolute/multi-component manifest entries, empty manifests, non-mapping manifests, and malformed (non-64-char or non-hex) digests.

## Limitations / Not Claimed

- **Production acceptance is BLOCKED.** The authoritative `special_tokens_map.json` digest is 63 hex chars, not 64. The production manifest binding is pinned verbatim and never "fixed"; no correct 64-char digest exists locally and none is guessed. Consequently `_validated_manifest()` and `load_mirror` (with the default binding) fail closed structurally before any file hashing, and no real mirror can be loaded until the authoritative source is corrected under separate authorization.
- **`runtime_compatibility_id` is `None`.** No model/library/platform compatibility identity is fabricated; D8 requires a separately authorized offline smoke to freeze it. `load_model` was exercised only against a fake ModelScope stub, never real inference.
- **No live smoke:** the 2.26 GB model was not downloaded; the production manifest was never verified against real artifact files. No claim of live compatibility, model load success, or Phase 16 completion is made. No later Phase 16 wave was entered.
- **FIFO non-regular-file rejection** is skipped on Windows (`os.mkfifo` unavailable). On this Windows 11 box directory symlinks, file symlinks, symlink-root escapes, and symlink-ancestor escapes were exercised and rejected.
- **TOCTOU:** path safety is pathname-based and fail-closed, not capability-rooted and not fully TOCTOU-free (see Design Notes).
- The module is not exported through `entity/__init__.py` (frozen contract: facade untouched); a future consumer (`raner_adapter.py`) is out of scope.

## Blockers

**BLOCKED (production acceptance):** the authoritative 63-character `special_tokens_map.json` digest. Resolution requires a separately authorized correction of the frozen model-selection manifest data; this task pinned it verbatim and did not guess/fix the missing nibble. Local implementation/hardening is complete and verified by the fresh command results above.
