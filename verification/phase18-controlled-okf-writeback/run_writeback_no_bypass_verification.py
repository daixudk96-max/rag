"""R-OKF-07 no-bypass verification for the controlled OKF writeback (18-VER).

Proves that the Phase 18 writeback pipeline has NO human-review bypass:

- static source checks (approval-gate literal, no auto-merge wiring, CLI
  subcommand set without a merge subcommand, writable-root whitelist);
- functional probes on a disposable tmp bundle (proposal -> approve -> apply
  full chain, raw-target rejection, traversal rejection, unapproved-apply
  rejection, parser zero-ingest of .staging).

The runner is read-only with respect to the repository: functional probes run
inside tempfile.TemporaryDirectory with zero network, zero DB, and zero model
access.  The W7 live acceptance selector is default-denied and serializes as
blocked_not_executed; it needs separate user authorization per the master
plan.  The runner never fabricates evidence: every recorded boolean comes from
an actually executed probe or scan.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Final

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from llamaindex_runtime.okf.parser import OKFParser  # noqa: E402
from llamaindex_runtime.okf.writeback import apply as wb_apply  # noqa: E402
from llamaindex_runtime.okf.writeback import journal as wb_journal  # noqa: E402
from llamaindex_runtime.okf.writeback.proposal import (  # noqa: E402
    TARGET_ROOTS,
    WritebackProposal,
    write_proposal,
)

OK_EXIT: Final = 0
FAIL_EXIT: Final = 3
EVIDENCE_NAME: Final = "phase18_writeback_verification_evidence.md"
BLOCKED_STATUS: Final = "blocked_not_executed"
LIVE_SELECTORS: Final = {"w7_live_acceptance": BLOCKED_STATUS}

APPLY_GATE_LITERAL: Final = "proposal must be approved before merge; current status: "
CLI_SUBCOMMANDS_EXPECTED: Final = {"list", "show", "approve", "reject", "discard"}
TARGET_ROOTS_EXPECTED: Final = ("entities", "concepts", "synthesis")
_SCAN_CACHE: Final[dict[str, list[str]]] = {}
_SCAN_SKIP_DIRS: Final = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    # Non-production trees: disposable tdd_graph run worktrees (byte-copies of
    # the frozen definition and its tests) and the .tmp scratch area.
    ".tdd-graph-worktrees",
    ".tmp",
}
_PROBE_FRONTMATTER: Final = "---\ntype: legacy_entity\nname: huawei\n---\n"
_PROBE_ACTOR: Final = "verification-probe"
_PROBE_CREATED_AT: Final = "2026-09-04T00:00:00Z"


def _check_a1_apply_gate_literal(repo_root: Path) -> bool:
    source = (
        Path(repo_root) / "llamaindex_runtime" / "okf" / "writeback" / "apply.py"
    ).read_text(encoding="utf-8")
    return APPLY_GATE_LITERAL in source


def find_apply_callers_outside_tests(repo_root: Path) -> list[str]:
    """Return repo .py files calling apply_proposal() outside allowed zones.

    Allowed zones: the apply.py definition itself, tests/**, and
    verification/**.  Everything else (production llamaindex_runtime code
    outside writeback, scripts/**, ...) is reported as an outside caller.
    Non-production trees (.tdd-graph-worktrees snapshots, .tmp scratch,
    caches, venvs) are excluded from the walk.
    """
    root = Path(repo_root)
    cache_key = str(root)
    cached = _SCAN_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)
    definition = root / "llamaindex_runtime" / "okf" / "writeback" / "apply.py"
    outside: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SCAN_SKIP_DIRS for part in path.parts):
            continue
        relative = path.relative_to(root)
        if path == definition or relative.parts[0] in {"tests", "verification"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "apply_proposal(" in text:
            outside.append(str(relative).replace("\\", "/"))
    _SCAN_CACHE[cache_key] = outside
    return list(outside)


def _check_a2_no_auto_merge_wiring(repo_root: Path) -> bool:
    return find_apply_callers_outside_tests(repo_root) == []


def cli_subcommands(repo_root: Path) -> set[str]:
    source = (
        Path(repo_root) / "llamaindex_runtime" / "okf" / "writeback" / "cli.py"
    ).read_text(encoding="utf-8")
    return set(re.findall(r'sub\.add_parser\("([a-z]+)"', source))


def _check_a3_cli_subcommands(repo_root: Path) -> bool:
    return cli_subcommands(repo_root) == CLI_SUBCOMMANDS_EXPECTED


def _check_a4_target_roots(repo_root: Path) -> bool:
    return TARGET_ROOTS == TARGET_ROOTS_EXPECTED and "raw" not in TARGET_ROOTS


def _probe_proposal(target_file: str) -> WritebackProposal:
    return WritebackProposal(
        target_file=target_file,
        patch="merged body from verification probe",
        reason="R-OKF-07 no-bypass verification probe",
        evidence=("verification-probe",),
        proposed_by=_PROBE_ACTOR,
        created_at=_PROBE_CREATED_AT,
    )


def _check_b1_raw_write_rejected(repo_root: Path) -> bool:
    try:
        _probe_proposal("raw/secret.md")
    except ValueError:
        return True
    return False


def _check_b2_traversal_target_rejected(repo_root: Path) -> bool:
    try:
        _probe_proposal("entities/../../escape.md")
    except ValueError:
        return True
    return False


def _build_probe_bundle(bundle: Path) -> WritebackProposal:
    (bundle / "entities" / "org").mkdir(parents=True)
    (bundle / "index.md").write_text("# index\n", encoding="utf-8")
    target = bundle / "entities" / "org" / "huawei.md"
    target.write_text(_PROBE_FRONTMATTER + "stale body\n", encoding="utf-8")
    return _probe_proposal("entities/org/huawei.md")


def _check_b3_unapproved_apply_rejected(repo_root: Path) -> bool:
    del repo_root
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        proposal = _build_probe_bundle(bundle)
        staging = bundle / ".staging"
        write_proposal(staging, proposal)
        try:
            wb_apply.apply_proposal(
                proposal,
                bundle_root=bundle,
                staging_dir=staging,
                actor=_PROBE_ACTOR,
                at="2026-09-04T00:00:03Z",
            )
        except ValueError as exc:
            return "must be approved before merge" in str(exc)
        return False


def b4_probe_details(repo_root: Path) -> dict[str, bool]:
    """Run the approved proposal -> journal -> apply chain on a tmp bundle.

    Returns {'body_replaced': bool, 'frontmatter_preserved': bool,
    'merged_event_recorded': bool}; every value is False when the chain
    itself fails, so a crashed probe can never look like a pass.
    """
    del repo_root
    details = {
        "body_replaced": False,
        "frontmatter_preserved": False,
        "merged_event_recorded": False,
    }
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        proposal = _build_probe_bundle(bundle)
        staging = bundle / ".staging"
        staged = write_proposal(staging, proposal)
        journal_path = staging / "journal.jsonl"
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        wb_journal.record_creation(
            journal_path,
            proposal.proposal_id,
            actor=_PROBE_ACTOR,
            at="2026-09-04T00:00:01Z",
            payload_digest=digest,
        )
        wb_journal.approve(
            journal_path,
            proposal.proposal_id,
            actor=_PROBE_ACTOR,
            at="2026-09-04T00:00:02Z",
            payload_digest=digest,
        )
        wb_apply.apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor=_PROBE_ACTOR,
            at="2026-09-04T00:00:03Z",
        )
        merged = (bundle / "entities" / "org" / "huawei.md").read_text(encoding="utf-8")
        details["frontmatter_preserved"] = merged.startswith(_PROBE_FRONTMATTER)
        details["body_replaced"] = merged == (
            _PROBE_FRONTMATTER + "merged body from verification probe\n"
        )
        events = wb_journal.read_events(journal_path)
        details["merged_event_recorded"] = any(
            event.event_type == "merged" and event.proposal_id == proposal.proposal_id
            for event in events
        )
    return details


def _check_b4_approved_chain_merged(repo_root: Path) -> bool:
    try:
        return all(b4_probe_details(repo_root).values())
    except Exception:
        return False


def _check_b5_parser_staging_zero_ingest(repo_root: Path) -> bool:
    del repo_root
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        (bundle / "entities" / "org").mkdir(parents=True)
        (bundle / "index.md").write_text("# index\n", encoding="utf-8")
        (bundle / "entities" / "org" / "huawei.md").write_text(
            _PROBE_FRONTMATTER + "body\n", encoding="utf-8"
        )
        before = OKFParser().parse_bundle(bundle)
        staging = bundle / ".staging"
        write_proposal(staging, _probe_proposal("entities/org/huawei.md"))
        (staging / (str(uuid.uuid4()) + ".md")).write_text("decoy\n", encoding="utf-8")
        after = OKFParser().parse_bundle(bundle)
        paths_before = sorted(str(doc.file_path) for doc in before)
        paths_after = sorted(str(doc.file_path) for doc in after)
        no_staging_doc = not any(".staging" in path for path in paths_after)
        return (
            no_staging_doc
            and paths_before == paths_after
            and after.stats.parsed == before.stats.parsed
            and after.stats.skipped == before.stats.skipped + 1
        )


_CHECKS: Final = (
    ("a1_apply_gate_literal", "_check_a1_apply_gate_literal"),
    ("a2_no_auto_merge_wiring", "_check_a2_no_auto_merge_wiring"),
    ("a3_cli_subcommands", "_check_a3_cli_subcommands"),
    ("a4_target_roots", "_check_a4_target_roots"),
    ("b1_raw_write_rejected", "_check_b1_raw_write_rejected"),
    ("b2_traversal_target_rejected", "_check_b2_traversal_target_rejected"),
    ("b3_unapproved_apply_rejected", "_check_b3_unapproved_apply_rejected"),
    ("b4_approved_chain_merged", "_check_b4_approved_chain_merged"),
    ("b5_parser_staging_zero_ingest", "_check_b5_parser_staging_zero_ingest"),
)


def main(argv: list[str], *, repo_root: Path) -> int:
    if argv:
        raise ValueError("verification runner takes no command line arguments")
    root = Path(repo_root)
    results: dict[str, bool] = {}
    for name, attribute in _CHECKS:
        check = globals()[attribute]
        try:
            results[name] = bool(check(root))
        except Exception:
            results[name] = False
    checks_failed = sum(1 for ok in results.values() if not ok)
    record: dict[str, object] = {
        "verification_status": (
            "verified" if checks_failed == 0 else "verification_failed"
        ),
        "checks_run": len(_CHECKS),
        "checks_failed": checks_failed,
        "raw_write_rejected": results["b1_raw_write_rejected"],
        "traversal_rejected": results["b2_traversal_target_rejected"],
        "unapproved_apply_rejected": results["b3_unapproved_apply_rejected"],
        "approved_chain_merged": results["b4_approved_chain_merged"],
        "parser_staging_zero_ingest": results["b5_parser_staging_zero_ingest"],
        "apply_callers_outside_tests": len(find_apply_callers_outside_tests(root)),
        "cli_merge_subcommand_absent": results["a3_cli_subcommands"],
        "live_selectors": dict(LIVE_SELECTORS),
    }
    evidence_path = Path(__file__).resolve().parent / EVIDENCE_NAME
    evidence_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return OK_EXIT if checks_failed == 0 else FAIL_EXIT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], repo_root=Path(__file__).resolve().parents[2]))
