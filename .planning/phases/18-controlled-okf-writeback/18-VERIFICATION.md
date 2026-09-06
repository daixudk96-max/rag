# Phase 18 Verification — Controlled OKF Writeback (R-OKF-07)

Run date: 2026-09-04. Runner: `verification/phase18-controlled-okf-writeback/run_writeback_no_bypass_verification.py`.
Evidence line (real run, `checks_failed=0`, exit 0):

```
{"apply_callers_outside_tests":0,"approved_chain_merged":true,"checks_failed":0,"checks_run":9,"cli_merge_subcommand_absent":true,"live_selectors":{"w7_live_acceptance":"blocked_not_executed"},"parser_staging_zero_ingest":true,"raw_write_rejected":true,"traversal_rejected":true,"unapproved_apply_rejected":true,"verification_status":"verified"}
```

## 1) Phase 18 delivered

- Proposal schema + `.staging/` write protocol + parser exclusion (W1).
- Lifecycle journal with per-proposal event scoping (W2 + W2.1 interleaving fix).
- Review CLI: `list` / `show` / `approve` / `reject` / `discard` (W3).
- Merge executor `apply.py`: target whitelist + frontmatter-preserving RFC7396-style merge (W4, graph-engine candidate 300b93c landed) + W2.1 per-proposal journal scoping.

## 2) No-bypass proof (real run, all pass)

| Check | Name | Result |
| --- | --- | --- |
| A1 | a1_apply_gate_literal (apply.py:122 gate literal) | pass |
| A2 | a2_no_auto_merge_wiring (0 apply_proposal callers outside writeback/tests) | pass |
| A3 | a3_cli_subcommands (no merge subcommand) | pass |
| A4 | a4_target_roots (TARGET_ROOTS = entities/concepts/synthesis) | pass |
| B1 | b1_raw_write_rejected (write into raw/ raises) | pass |
| B2 | b2_traversal_target_rejected (entities/../.. raises) | pass |
| B3 | b3_unapproved_apply_rejected ("must be approved before merge") | pass |
| B4 | b4_approved_chain_merged (body replaced + frontmatter preserved + merged event) | pass |
| B5 | b5_parser_staging_zero_ingest (.staging decoy skipped, docs unchanged) | pass |

B4 probe details (independent tmp bundle): body_replaced, frontmatter_preserved, merged_event_recorded — all true.

## 3) Debt wave W5

Executed under Phase 17 taskboard rows W5a/W5b/W5c (cross-ref 17-PLAN-MASTER §27). Follow-ups 13 -> 8 closed (F3/F4-codeable/F5/F6/F7/F8/F9/F10/F13). NOT fixed, recorded: F11 (BM25 real route), F12 (UNKNOWN source_id), F4-live (LLM-primary never exercised live), F14-residual.

## 4) Explicit NON-CLAIMS

- No merge CLI subcommand exists (`apply_proposal` is library-only; W7 live scope decides wiring).
- No auto-merge code anywhere (T8 redline; A2 scan: 0 production callers).
- raw/ and sidecar zero-write proven by B1 + target whitelist.
- W7 live acceptance NOT yet authorized (`live_selectors` default-denied: `w7_live_acceptance` -> `blocked_not_executed`).
- Production proposals do not exist yet (`.staging` absent from the real okf_bundle).

## 5) Re-verify

```
python verification/phase18-controlled-okf-writeback/run_writeback_no_bypass_verification.py
```

(__main__ guard: `main(sys.argv[1:], repo_root=Path(__file__).resolve().parents[2])`; argv must be empty.)

Suites at verification time: phase18 focused 18 passed; 7-domain 3 failed/1559 passed/1 skipped (3 pre-existing raner trio); okf 5/3381/31; gate3 2/598/4 — all pre-existing failures identical to baseline.
