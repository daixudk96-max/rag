# Phase 18 W0 Recon — Controlled OKF Writeback

> Read-only scout report for wave-1 (and downstream) spec authoring. All claims anchored `file:line`.
> Budget note: no empirical run of Path.rglob dot-dir behavior; stated as stdlib semantics to verify in impl.

---

## 1. okf_bundle/ structure + AGENT.md editing zones

**Top-level files** (glob `okf_bundle/**`): `okf_bundle/index.md`, `okf_bundle/log.md`, `okf_bundle/AGENT.md`, `okf_bundle/.okflintrc.json`.
**Dirs**: `raw/`, `entities/`, `concepts/`, `synthesis/` (each `.gitkeep`), `templates/` (`raw.md`, `entity.md`, `relation.md`, `concept.md`, `README.md`).
**`.staging/` DOES NOT EXIST yet** — no `.staging` anywhere under `okf_bundle/` (glob); wave-1 creates it. Per 18-BOUNDARY.md:18 the staging location is `okf_bundle/.staging/`.

**`.okflintrc.json`** (okf_bundle/.okflintrc.json:1-5): only rule `"timestamp-format": "off"`.

**AGENT.md editing-zones declaration VERBATIM** (okf_bundle/AGENT.md):
- `## Always do` (AGENT.md:12-16): "Keep valid YAML frontmatter on editable OKF Markdown pages." / "Treat `raw/` as machine-generated output from the docling-to-OKF serializer." / "Treat adjacent `*.spans.json` sidecars as the sole source of span identity." / "Make human knowledge edits in `entities/`, `concepts/`, and `synthesis/`." / "Use bundle-relative absolute links for cross-page references."
- `## Ask first` (AGENT.md:18-22): before deleting/restructuring knowledge pages; before changing bundle directory structure or type taxonomy; before changing raw-document provenance or regenerating an existing raw document.
- `## Never` (AGENT.md:24-29): "Modify files in `raw/` by hand." / "Modify a raw document's adjacent `*.spans.json` sidecar by hand." / "Remove or alter the `type` field in an existing editable OKF page." / "Use relative links (`./`) for cross-page references."

**Zone reading**: machine-writable whitelist = `entities/`,`concepts/`,`synthesis/` (AGENT.md:15); `raw/` + sidecars strictly machine-generated (AGENT.md:13-14,26-27). Matches 18-BOUNDARY.md:22 merge-executor whitelist exactly.

---

## 2. llamaindex_runtime/okf/parser.py — structure map

Total 647 lines. Module docstring (parser.py:1-15): parses OKF bundles; Phase 14-03 additions = sidecar reading, `RawFrontmatterContract` fail-fast, **sync-decision DTO for incremental sync**, **delete detection via path comparison**.

**Defense/budget internals**: `MAX_YAML_DEPTH=64 / MAX_YAML_NODES=10_000 / MAX_YAML_ALIASES=32` (parser.py:46-48); `_read_document_bytes_bounded` (parser.py:62) no-follow + `_limits.MAX_DOCUMENT_BYTES` cap (parser.py:78), reparse-point guard (parser.py:51).

**Public API + classes**:
- `SyncDecision` frozen dataclass (parser.py:118); `BundleStats` (parser.py:135; fields `parsed/skipped/malformed`, :138-140); `OKFFrontmatter` (parser.py:229); `OKFParagraph` (parser.py:279); `OKFDocument` (parser.py:289); `BundleDocuments` (parser.py:305); **`BundleResult = BundleDocuments`** (parser.py:333).

**Functions** (parser.py):
- `compute_sync_decision(*, doc_id, okf_file_path, current_canonical_hash, previous_state) -> SyncDecision` (parser.py:143-149); statuses `synced/skipped/resynced` (parser.py:150-177). **No production callers today** — only tests (`tests/llamaindex_runtime/okf/test_okf_parser_completion_contracts.py:214,220-244,256-300`). Implemented-but-unwired incremental sync.
- `compute_deleted_paths(previous_paths, current_paths) -> frozenset[str]` (parser.py:180-193).
- `OKFParser.parse_bundle(bundle_path) -> BundleResult` (parser.py:352); `parse_document` (414); `parse_frontmatter` (512); `build_frontmatter` (553); `extract_body` (567); `parse_paragraphs` (579); `compute_hash(file_path) -> str` sha256 (616); `main()` CLI (629, needs bundle_path arg, :634).

**Bundle walk — recursive? YES.** parse_bundle: `candidates = sorted(root.rglob("*.md"), key=bundle_relative_components)` (parser.py:364-367) under `BundleAuthority(root)` (parser.py:363); routed to `_parse_candidates` (parser.py:368). `Path.rglob` walks the whole tree including dot-directories → a future `okf_bundle/.staging/` is guaranteed to enter the crawl if it holds `*.md`.

**Existing path filters** — the exact spot a `.staging` exclusion belongs:
- `_parse_candidates`: `if candidate.name in {"index.md", "log.md"} or ".obsidian" in parts:` → skip (parser.py:395-397). `parts = bundle_relative_components(candidate, root)` computed at parser.py:386. A staging skip belongs here as a companion branch (e.g. `parts[0] == ".staging"`).
- Raw routing: `_parse_authorized` sees `parts[0] == "raw"` → `_parse_admitted_raw` via `read_raw_pair` (parser.py:428-431); non-raw via `authority.read_document(parts)` (parser.py:433).
- Editable-page identity: content sha256 as `version_hash` / `okf_version_hash` (parser.py:467); raw identity uses manifest canonical_hash from the sidecar pair (parser.py:450).

**Existing parser tests** (why re-read not needed): `test_okf_parser_completion_bundle.py`, `test_okf_parser_completion.py`, `test_okf_parser_completion_contracts.py`, `test_okf_parser_completion_span_identity.py`, `test_okf_parser_completion_error_safety.py`, `test_okf_parser_completion_remediation.py`, `test_okf_parser_completion_frontmatter_contracts.py`, `test_okf_parser_path_security.py`, `test_okf_parser_cli.py`, `test_raw_pair_parser_admission.py`, plus `_parser_completion_testkit.py`.

---

## 3. F3 sync flow — canonical-hash sync + trigger seam

**Scripts present**: `scripts/rebuild_from_okf.py` (E1 — per STATE.md "the sole supported E1 CLI"), `scripts/rebuild_from_okf_e2a.py`, `scripts/rebuild_from_okf_e2b.py`. **No runtime rebuild module under `llamaindex_runtime/okf/`** (glob: none); the runtime dir has `canonical_hash.py`, `roundtrip.py`, `raw_pair.py`, etc.

**E1 entry** (scripts/rebuild_from_okf.py):
- `rebuild_bundle(bundle_path: Path, *, environ=None) -> int` (rebuild_from_okf.py:742-751): requires `_require_disposable_database_url` (747, 769), `_admit_bundle` (750), then `_rebuild_admitted_bundle`. Consumes **bundle path only — no hash ledger**.
- `main` (754); `parse_arguments` (161) demands one of `--verify-roundtrip` / `--rebuild`.
- It is a **raw → DB canonical-span reconciliation** (`_canonical_rows` :325, `_reconcile_spans` :414); exports `canonical_hash`/span machinery from okf package.
- **Triggered today**: manual CLI (e.g. `python scripts/rebuild_from_okf.py --bundle <bundle-root> --rebuild`), evidenced in verification/phase14-okf-foundation/12-gate-f-non-goals-scope-attestation.json:49-50 (`command_pattern`). Not referenced from any runtime ingestion path.

**E2b entry** (scripts/rebuild_from_okf_e2b.py):
- `rebuild_bundle(bundle_path: Path, *, environ=None, connection_factory, repository_factory, extractor_factory, corpus_input_factory, desired_state_factory) -> _E2bRebuildOutcome` (scripts/rebuild_from_okf_e2b.py:500-554); all pipeline seams keyword-only injectable, defaults fail-closed (514-539); runs phase-16 E2b reconcile per admitted raw doc (`_rebuild_one` :466). `main` (573), `_run_redacted_cli` (591) — never prints `str(exc)` (596).

**Post-merge sync trigger seam — where it naturally lives**: The raw rebuild CLIs are NOT the seam (they consume raw/ only). The 14-03 incremental-sync decision machinery — `compute_sync_decision` (parser.py:143) + `compute_deleted_paths` (parser.py:180) — is exactly the "F3 sync" hooking point, and it currently has **zero live callers** (only test_okf_parser_completion_contracts.py). Per requirements.md:13 wave-4 only needs an **injectable seam** ("F3 同步触发经注入 seam（本波不真跑同步）"), so wave-4 authors should inject a `sync_trigger: Callable` rather than wire a real call.

**Hash caveat for wave specs**: `canonical_hash(frontmatter, sidecar)` (llamaindex_runtime/okf/canonical_hash.py:30) is raw-sidecar-only; **for editable pages post-merge the change signal is the plain content sha256** (`OKFParser.compute_hash` parser.py:616, or the `version_hash` computed at parser.py:467 / canonical_hash.py normalize: `canonical_json_sha256` chains in e2a). pin which function records "canonical hash change" for `entities|concepts|synthesis` targets.

---

## 4. UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md — §5 and §7

File exists: .planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md. Section index: §5 at :91, §7 at :118.

**§5 llm-wiki-compiler (MIT, TS → design-translate, do not port code)** (:91-102):
- Candidate storage: `.staging/candidates/<id>.json` one-proposal-one-file; reject → move into `archive/` (llmwiki `.llmwiki/candidates/` pattern) (:95).
- Structured hold reasons: `HeldReason` codes `low-confidence | contradicted | schema-violating | provenance-violating | imported | manual-review-requested` — our proposal schema adds this field (:96).
- Concurrency: re-read candidate under lock (TOCTOU guard) + hold lock across the whole review command (:97).
- Honest atomicity layering: only the body write is atomic (journal); index/state refresh is best-effort re-runnable tail — the 18 merge executor follows this, never pretends fully-atomic (:98).
- **Our improvement** (they lack it): explicit audit fields `approvedBy/approvedAt/rejectedReason` — they delete the candidate on approval (no audit trail), our journal adds it (:99).
- `canonicalBody()` strips derived Citations section then sha256 — same idea as our canonical-hash-excludes-formatting; but their frontmatter serialization is unordered (lossy) — counter-example confirming 14-01 pinned order (:100).
- Their citation anchors are line ranges, not char offsets → `span_id` chain has no upstream to port (:101).

**§7 open-knowledge (GPL-3.0) — user 2026-07-12 verdict lifted the ban** (:118-147):
- Verdict quote (:120): "open-knowledge这个是我自己使用，我认为你需要突破这个代码限制。" — private use, no distribution → GPL-compliant. **Tripwire** (:121): before any future distribution/open-sourcing, must dispose of GPL-derived parts (whole-repo GPL or strip); ported/copied files carry a source header; `grep -r "inkeep/open-knowledge"` enumerates the strip list.
- **7a PORT** (:127-135): `frontmatter-merge.ts` = RFC 7396 merge-patch semantics (patch values replace; `null`/''/`[]` delete keys; `undefined` preserves) → 18 proposal format + merge executor (:129); `doc-name.ts` = write-time admission: strict docName validation (rejects `..` traversal, absolute paths, control chars, dot-prefixed hidden segments) → merge-executor whitelist pre-check (:130); `ingest-body.ts:74-78` kebab-case slug `^[a-z0-9][a-z0-9-]{0,99}$`, date goes in frontmatter not slug (:131); `atomic-yaml-write.ts` = tmp+rename atomic write + **>30s stale .tmp.* orphan sweep** (ogham enhancement) (:132); `links.ts` + wiki-link parse = normalized relative links + broken-link detection returning `brokenLinks` after write + `[[wikilink]]` extraction (:133); `write.ts` asset-dedup = SHA-256 byte dedup, date-versioned re-ingest on mismatch (:134).
- Dedup rule (:136): YAML frontmatter codec, atomic export, unknown-field preservation stay with **ogham-mcp (Python, ported in 14) as first source** — open-knowledge only fills gaps (merge-patch, admission, broken-link, stale-tmp sweep). Do not double-port.
- **7b COPY** (:138-143): SKILL.md trio (packs/okf — type single rule + retained files + `log.md` contract; packs/entity-vault — dossier convention: compiled-truth zone + `--- timeline ---` separator + append-only timeline entries `- **YYYY-MM-DD** | source | @author — evidence. Confidence: …`; project — grounding "every factual claim must cite a local source; a bare URL is not a finished citation", persist-as-you-go, link discipline) → excerpt into `okf_bundle/AGENT.md` + 18 agent prompts (:140); `consolidate-body.ts:25-35` decision-confirmation gate (must state the decision / rejected alternatives / reason before writing canonical) → human-review CLI approve prompt (:141); log discipline `## YYYY-MM-DD: <summary>` append-only, newest-first + ≤80-char user-facing `summary` on each write/edit → 18 audit journal two-layer structure (human-readable `log.md` + machine-readable summary) (:142); `status: provisional|canonical` + `sources:[...]` + `supersedes:[...]` provenance chain → 16/18 entity/synthesis status+provenance fields (:143).
- **7c SKIP** (:145-147): Yjs/CRDT, Hocuspocus, ProseMirror, React/Electron UI, Orama search, MCP infra.
- These are distilled into 18-BOUNDARY.md:52-56 (authoritative boundary pointer).

---

## 5. tests/llamaindex_runtime/okf/ conventions

Flat package (no subdirs), ~190 test files, has `__init__.py`. Naming: `test_<topic>*.py`; shared testkits/drivers prefixed `_` (e.g. `_rebuild_cli_testkit.py`, `_rebuild_integration_testkit.py`, `raw_pair_testkit.py` (no underscore), `_parser_completion_testkit.py`, `_sidecar_testkit.py`, `_serializer_testkit.py`).

**Import/pattern exemplars**:
- `test_okf_parser_path_security.py`: `from llamaindex_runtime.okf import parser as parser_module`, `from llamaindex_runtime.okf.parser import OKFParser`, `from .raw_pair_testkit import bind_raw_bytes` (:11-18); builds bundles in `tmp_path` via local helpers `_write_non_raw(root, relative, content)` (:21) and `_write_raw(root, relative="raw/source.md")` (:30, writes md+sidecar+GenerationManifest). This is the template for the wave-1 `test_parser_staging_exclusion.py` (put sample body markdown under `.staging/`, assert parse output excludes it).
- `test_rebuild_from_okf_e2b_default_seams.py`: loads the script as an isolated module via `importlib.util.spec_from_file_location("rebuild_from_okf_e2b", SCRIPT)` (:16-22,63,90); `REPO_ROOT = Path(__file__).resolve().parents[3]` (:38), `SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf_e2b.py"` (:39); guarded env keys `_DATABASE_ROUTING_KEYS` frozenset (:50-57); guarded rebuild env map (:43-49).
- `_rebuild_cli_testkit.py`: `load_rebuild_module()` (:67) → isolated module; `make_bundle(tmp_path, fixture)` (:76-94) serializes a frozen docling fixture (`tests/fixtures/okf_roundtrip/<fixture>/{expected_span_ids.json,docling_output.json}`) via `serializer.serialize_document(...)` into the temp bundle; `bundle_result(*documents)` (:97) builds `BundleResult` without a filesystem round-trip.

**Planned wave-1 test files** (requirements.md:10): `tests/llamaindex_runtime/okf/test_writeback_proposal.py`, `tests/llamaindex_runtime/okf/test_parser_staging_exclusion.py` (testsRoot=tests; `allowTestsUpdate: false`).

---

## 6. Existing writeback / staging / review code — collision audit

- **`writeback`: zero implementation anywhere.** Gate-F attestation explicitly searched and recorded 0 occurrences: verification/phase14-okf-foundation/12-gate-f-non-goals-scope-attestation.json:162 ("combined agent/writeback/Git add-commit-push search: 0 occurrences"), :163; and :165 confirms "Agent writeback" is deliberately deferred to Phase 18. 18-BOUNDARY.md:27 (T8): no auto-merge switch, not even an off-state implementation. → `llamaindex_runtime/okf/writeback/` is a free namespace; no collision.
- **`.staging` as a directory name: no existing use** in okf_bundle or any bundle. 
- **Closest existing symbol with a different meaning**: `llamaindex_runtime/gate3/_staging.py` + `tests/llamaindex_runtime/gate3/test_staging.py` — gate3 trial-engine pipeline "staging" (Phase 17); different domain, same word. wave-1 should keep the OKF naming `okf_bundle/.staging/` distinct and NOT touch gate3.
- **`review`-named code**: `test_task27_*_review*.py` exist (test_task27_review_regressions.py etc.) — Task27 is a hook/protocol review set (canonical value domain, hostile hook closure), unrelated to proposal review; not examined in depth. No collision with Phase-18 review CLI.
- **`HeldReason` / `WritebackProposal` / `archive/`(in bundle): zero matches** — new names are free.
- **Frozen files not to touch** (requirements.md:7): `entity/{label_map,contracts,normalization,identity,fuzzy_recall,review_basket,relation_review,coref_rules,uie_adapter}.py`, `extraction/trial.py`, `graph/lightrag_backend.py`, `analysis/graph_channel.py`.

---

## wave-1 implications

**wave-1 MUST do** (per requirements.md:10 + boundary):
1. NEW `llamaindex_runtime/okf/writeback/__init__.py` + `writeback/proposal.py`: frozen `WritebackProposal` with `proposal_id=uuid5(NAMESPACE_URL, "okf-writeback-proposal-v1"+payload)`, `target_file` (bundle-relative admission; **`raw/` prefix → ValueError**, AC A03), `patch` str, `reason` non-empty, `evidence` = tuple of span_id refs (**empty → `unverified=True` but still lands**, AC A02), `proposed_by` non-empty, `created_at` via injectable clock seam, `status` pinned `created`. Atomic write to `okf_bundle/.staging/<proposal_id>.json` (create `.staging/` — doesn't exist yet). Round-trip == original (AC A01).
2. EDIT `llamaindex_runtime/okf/parser.py` at the skip filter **parser.py:395-397** (`index.md/log.md/.obsidian` branch): add `.staging` exclusion (parts-based, e.g. `.staging` in `parts` / `parts[0] == ".staging"`) so the crawl from `root.rglob("*.md")` (parser.py:365) never picks up staging content. **This is a genuine requirement, not cosmetic**: `Path.rglob` descends into dot-directories, so any `*.md` under `.staging/` is currently ingested. Keep the crawl under `BundleAuthority` (parser.py:363) and rooted read security intact — see test_okf_parser_path_security.py fixtures for the template; new test places body-sampled markdown under `.staging/` and asserts zero ingestion (AC A04).
3. New tests `test_writeback_proposal.py` + `test_parser_staging_exclusion.py` in `tests/llamaindex_runtime/okf/` following the flat-package + `tmp_path`-bundle convention (test_okf_parser_path_security.py pattern).

**wave-1 MUST NOT do**:
- Touch `raw/` or any `*.spans.json` (machine-only zones, AGENT.md:13-14,26-27; 18-BOUNDARY.md:28).
- Touch `scripts/rebuild_from_okf*.py` (E1/E2a/E2b frozen CLIs) or auth/audit DB machinery.
- Touch the frozen-file list (requirements.md:7) nor the non-okf `gate3/_staging.py` trial staging.
- Any git auto-op, network/model/RaNER, or live-gate behavior (requirements.md:7; 18-BOUNDARY.md:27-29).
- Drop/alter `type` or restructure bundle taxonomy (AGENT.md:21,28).

**Borrowed blueprints wave-1 should fold in**: HeldReason field (UPSTREAM :96), one-proposal-one-JSON + reject-to-archive (:95), RFC7396 merge-patch expression for `patch` (:129), doc-name-style admission for `target_file` (:130), GPL source headers on anything ported/copied from open-knowledge (:121). Structure/post-staging concerns (lifecycle/journal/CLI/merge) belong to waves 2-4, not wave-1.
