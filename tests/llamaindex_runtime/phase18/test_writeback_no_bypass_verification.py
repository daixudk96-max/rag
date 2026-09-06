"""R-OKF-07 no-bypass verification tests (run_writeback_no_bypass_verification.py).

The runner lives at verification/phase18-controlled-okf-writeback/ and is
loaded via importlib by absolute path, registered in sys.modules like the
phase17 tests do.  The writeback library is FROZEN: these tests exercise only
the runner -- static source checks against the real repo, functional probes on
disposable tmp bundles, and the evidence-record contract.  Zero network, zero
DB, zero model.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = (
    REPO_ROOT
    / "verification"
    / "phase18-controlled-okf-writeback"
    / "run_writeback_no_bypass_verification.py"
)

RECORD_KEYS = {
    "verification_status",
    "checks_run",
    "checks_failed",
    "raw_write_rejected",
    "traversal_rejected",
    "unapproved_apply_rejected",
    "approved_chain_merged",
    "parser_staging_zero_ingest",
    "apply_callers_outside_tests",
    "cli_merge_subcommand_absent",
    "live_selectors",
}


@pytest.fixture(scope="module")
def runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "run_writeback_no_bypass_verification", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_main(runner: Any) -> tuple[int, dict[str, Any]]:
    exit_code = runner.main([], repo_root=REPO_ROOT)
    evidence = RUNNER_PATH.parent / runner.EVIDENCE_NAME
    record: dict[str, Any] = json.loads(evidence.read_text(encoding="utf-8"))
    return exit_code, record


def test_a1_apply_gate_literal_present(runner: Any) -> None:
    assert runner._check_a1_apply_gate_literal(REPO_ROOT) is True


def test_a2_no_apply_callers_outside_tests(runner: Any) -> None:
    assert runner._check_a2_no_auto_merge_wiring(REPO_ROOT) is True
    assert runner.find_apply_callers_outside_tests(REPO_ROOT) == []


def test_a2_scanner_detects_outside_caller(runner: Any, tmp_path: Path) -> None:
    package = tmp_path / "scripts"
    package.mkdir()
    (package / "rogue.py").write_text(
        "from x import apply_proposal\n\napply_proposal(p)\n", encoding="utf-8"
    )
    found = runner.find_apply_callers_outside_tests(tmp_path)
    assert len(found) == 1
    assert found[0].endswith("rogue.py")


def test_a3_cli_subcommands_exact_and_merge_absent(runner: Any) -> None:
    assert runner._check_a3_cli_subcommands(REPO_ROOT) is True
    assert runner.cli_subcommands(REPO_ROOT) == {
        "list",
        "show",
        "approve",
        "reject",
        "discard",
    }


def test_a4_target_roots_literal(runner: Any) -> None:
    assert runner._check_a4_target_roots(REPO_ROOT) is True
    assert runner.TARGET_ROOTS == ("entities", "concepts", "synthesis")
    assert "raw" not in runner.TARGET_ROOTS


def test_b1_raw_target_rejected(runner: Any) -> None:
    assert runner._check_b1_raw_write_rejected(REPO_ROOT) is True


def test_b2_traversal_target_rejected(runner: Any) -> None:
    assert runner._check_b2_traversal_target_rejected(REPO_ROOT) is True


def test_b3_unapproved_apply_rejected(runner: Any) -> None:
    assert runner._check_b3_unapproved_apply_rejected(REPO_ROOT) is True


def test_b4_body_replaced_and_frontmatter_preserved(runner: Any) -> None:
    details = runner.b4_probe_details(REPO_ROOT)
    assert details["body_replaced"] is True
    assert details["frontmatter_preserved"] is True
    assert runner._check_b4_approved_chain_merged(REPO_ROOT) is True


def test_b4_journal_records_merged_event(runner: Any) -> None:
    details = runner.b4_probe_details(REPO_ROOT)
    assert details["merged_event_recorded"] is True


def test_b5_parser_zero_ingest_of_staging(runner: Any) -> None:
    assert runner._check_b5_parser_staging_zero_ingest(REPO_ROOT) is True


def test_main_rejects_command_line_arguments(runner: Any) -> None:
    with pytest.raises(
        ValueError, match="verification runner takes no command line arguments"
    ):
        runner.main(["extra"], repo_root=REPO_ROOT)


def test_main_all_green_on_real_repo(runner: Any) -> None:
    exit_code, record = _run_main(runner)
    assert exit_code == runner.OK_EXIT
    assert record["verification_status"] == "verified"
    assert record["checks_run"] == 9
    assert record["checks_failed"] == 0


def test_record_allowlist_keys_exact(runner: Any) -> None:
    _, record = _run_main(runner)
    assert set(record.keys()) == RECORD_KEYS


def test_live_selector_default_denied(runner: Any) -> None:
    _, record = _run_main(runner)
    assert record["live_selectors"] == {"w7_live_acceptance": "blocked_not_executed"}


def test_evidence_serialization_single_line(runner: Any) -> None:
    _run_main(runner)
    raw = (RUNNER_PATH.parent / runner.EVIDENCE_NAME).read_text(encoding="utf-8")
    record: dict[str, Any] = json.loads(raw)
    expected = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert raw == expected + "\n"


def test_fail_closed_aggregation_two_induced_failures(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "_check_a1_apply_gate_literal", lambda repo_root: False)
    monkeypatch.setattr(runner, "_check_b1_raw_write_rejected", lambda repo_root: False)
    exit_code, record = _run_main(runner)
    assert exit_code == runner.FAIL_EXIT
    assert record["checks_failed"] == 2
    assert record["verification_status"] == "verification_failed"


def test_main_guard_present(runner: Any) -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert "repo_root=Path(__file__).resolve().parents[2]" in source
