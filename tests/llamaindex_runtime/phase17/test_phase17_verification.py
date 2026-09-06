"""Verification-orchestrator tests (run_phase17_verification.py, 17-VER pattern).

The orchestrator consumes the on-disk Phase 17 evidence artifacts; it must NOT
re-run live gates and must NOT fabricate evidence.  These tests pin the frozen
19-key gate contract, the archive sha256 chain, the demo report shape, the
fail-closed aggregation behaviour, and the allowlisted evidence record.  The
real artifacts are read-only here; every tamper case runs against a tmp copy.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase17-graph-recall-multiroute-fusion"
VERIFICATION_PATH = VERIFICATION_DIR / "run_phase17_verification.py"

GATE_LIVE = "graph_recall_acceptance_evidence.md"
GATE_FIRST = "graph_recall_acceptance_evidence_executed_2026-09-03.md"
GATE_DEEPSEEK = "graph_recall_acceptance_evidence_executed_deepseek_2026-09-03.md"
GATE_PRE_FIX17 = "graph_recall_acceptance_evidence_pre_fix17_2026-09-03.md"
GATE_LLM500 = "graph_recall_acceptance_evidence_llm500_2026-09-03.md"
DEMO_LIVE = "phase17_demo_report.md"
DEMO_FIRST = "phase17_demo_report_executed_2026-09-03.md"
DEMO_DEEPSEEK = "phase17_demo_report_executed_deepseek_2026-09-03.md"
DEMO_PRE_FIX17 = "phase17_demo_report_pre_fix17_2026-09-03.md"

ARTIFACT_NAMES = (
    GATE_LIVE,
    GATE_FIRST,
    GATE_DEEPSEEK,
    GATE_PRE_FIX17,
    GATE_LLM500,
    DEMO_LIVE,
    DEMO_FIRST,
    DEMO_DEEPSEEK,
    DEMO_PRE_FIX17,
)

RECORD_KEYS = {
    "gate_evidence_sha256",
    "demo_report_sha256",
    "gate_status",
    "gate_exit_code",
    "recall_hit_count",
    "ingest_entities",
    "demo_batches_executed",
    "live_selectors",
    "verification_status",
    "checks_run",
    "checks_failed",
}


@pytest.fixture(scope="module")
def verification() -> Any:
    spec = importlib.util.spec_from_file_location(
        "phase17_verification", VERIFICATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_artifacts(tmp_path: Path) -> Path:
    for name in ARTIFACT_NAMES:
        shutil.copyfile(VERIFICATION_DIR / name, tmp_path / name)
    return tmp_path


def _run(verification: Any, target: Path) -> tuple[int, dict[str, Any]]:
    exit_code = verification.main([], verification_dir=target)
    evidence = target / verification.VERIFICATION_EVIDENCE_NAME
    record: dict[str, Any] = json.loads(evidence.read_text(encoding="utf-8"))
    return exit_code, record


def test_gate_evidence_parses_with_frozen_nineteen_keys(
    verification: Any,
) -> None:
    payload = json.loads((VERIFICATION_DIR / GATE_LIVE).read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(verification.GATE_EVIDENCE_KEYS)


def test_gate_evidence_contract_values_pass() -> None:
    payload = json.loads((VERIFICATION_DIR / GATE_LIVE).read_text(encoding="utf-8"))
    assert payload["status"] == "executed"
    assert payload["exit_code"] == 0
    assert payload["recall_hit_count"] >= 1
    assert payload["ingest_entities"] > 0
    assert payload["route"] == "PURE_UIE"


def test_demo_report_contains_both_batches() -> None:
    report = (VERIFICATION_DIR / DEMO_LIVE).read_text(encoding="utf-8")
    assert "## batch: similar" in report
    assert "## batch: mixed" in report


def test_demo_report_has_two_executed_and_two_pure_uie_lines() -> None:
    report = (VERIFICATION_DIR / DEMO_LIVE).read_text(encoding="utf-8")
    assert report.count("status: executed") == 2
    assert report.count("route: PURE_UIE") == 2


def test_gate_live_sha_matches_deepseek_archive_and_pin(
    verification: Any,
) -> None:
    assert _sha256(VERIFICATION_DIR / GATE_LIVE) == verification.GATE_LIVE_SHA
    assert _sha256(VERIFICATION_DIR / GATE_DEEPSEEK) == verification.GATE_LIVE_SHA


def test_gate_first_run_archive_pair_matches_pin(verification: Any) -> None:
    assert _sha256(VERIFICATION_DIR / GATE_FIRST) == verification.GATE_FIRST_ARCHIVE_SHA
    assert (
        _sha256(VERIFICATION_DIR / GATE_PRE_FIX17)
        == verification.GATE_FIRST_ARCHIVE_SHA
    )


def test_llm500_honest_failure_archive_matches_pin(verification: Any) -> None:
    llm500 = VERIFICATION_DIR / GATE_LLM500
    assert _sha256(llm500) == verification.GATE_LLM500_ARCHIVE_SHA
    payload = json.loads(llm500.read_text(encoding="utf-8"))
    assert payload["status"] == "executed_failed"
    assert payload["exit_code"] == 3


def test_demo_live_sha_matches_deepseek_archive_and_pin(verification: Any) -> None:
    assert _sha256(VERIFICATION_DIR / DEMO_LIVE) == verification.DEMO_LIVE_SHA
    assert _sha256(VERIFICATION_DIR / DEMO_DEEPSEEK) == verification.DEMO_LIVE_SHA


def test_demo_first_run_archive_pair_matches_pin(verification: Any) -> None:
    assert _sha256(VERIFICATION_DIR / DEMO_FIRST) == verification.DEMO_FIRST_ARCHIVE_SHA
    assert (
        _sha256(VERIFICATION_DIR / DEMO_PRE_FIX17)
        == verification.DEMO_FIRST_ARCHIVE_SHA
    )


def test_tampered_gate_evidence_fails_with_exit_three(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    gate = target / GATE_LIVE
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            '"status":"executed"', '"status":"executed_failed"'
        ),
        encoding="utf-8",
    )
    exit_code, record = _run(verification, target)
    assert exit_code == verification.FAIL_EXIT
    assert record["verification_status"] == "verification_failed"
    assert record["checks_failed"] >= 1


def test_missing_gate_evidence_fails_closed(verification: Any, tmp_path: Path) -> None:
    target = _copy_artifacts(tmp_path)
    (target / GATE_LIVE).unlink()
    exit_code, record = _run(verification, target)
    assert exit_code == verification.FAIL_EXIT
    assert record["verification_status"] == "verification_failed"


def test_tampered_demo_report_fails_with_exit_three(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    demo = target / DEMO_LIVE
    demo.write_text(
        demo.read_text(encoding="utf-8").replace("- status: executed\n", "", 1),
        encoding="utf-8",
    )
    exit_code, record = _run(verification, target)
    assert exit_code == verification.FAIL_EXIT
    assert record["verification_status"] == "verification_failed"


def test_wrong_sha_archive_fails_with_exit_three(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    (target / GATE_DEEPSEEK).write_bytes(b'{"tampered":true}\n')
    exit_code, record = _run(verification, target)
    assert exit_code == verification.FAIL_EXIT
    assert record["verification_status"] == "verification_failed"


def test_main_rejects_command_line_arguments(verification: Any) -> None:
    with pytest.raises(
        ValueError, match="verification runner takes no command line arguments"
    ):
        verification.main(["extra"], verification_dir=VERIFICATION_DIR)


def test_live_selectors_serialized_blocked_not_executed(
    verification: Any, tmp_path: Path
) -> None:
    _, record = _run(verification, _copy_artifacts(tmp_path))
    assert record["live_selectors"] == {
        "gate_rerun": "blocked_not_executed",
        "demo_rerun": "blocked_not_executed",
    }


def test_live_selectors_never_marked_executed(
    verification: Any, tmp_path: Path
) -> None:
    assert verification.LIVE_SELECTORS == ("gate_rerun", "demo_rerun")
    _, record = _run(verification, _copy_artifacts(tmp_path))
    assert all(
        value == verification.BLOCKED_STATUS
        for value in record["live_selectors"].values()
    )
    assert verification.EXECUTED_STATUS not in record["live_selectors"].values()


def test_all_green_exit_zero_on_real_artifacts(
    verification: Any, tmp_path: Path
) -> None:
    exit_code, record = _run(verification, _copy_artifacts(tmp_path))
    assert exit_code == verification.OK_EXIT
    assert record["verification_status"] == "verified"
    assert record["checks_failed"] == 0
    assert record["gate_status"] == "executed"
    assert record["gate_exit_code"] == 0
    assert record["recall_hit_count"] == 3
    assert record["ingest_entities"] == 8
    assert record["demo_batches_executed"] == 2
    assert record["gate_evidence_sha256"] == verification.GATE_LIVE_SHA
    assert record["demo_report_sha256"] == verification.DEMO_LIVE_SHA


def test_record_allowlist_keys_exact_and_single_line(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    exit_code, record = _run(verification, target)
    assert exit_code == verification.OK_EXIT
    assert set(record.keys()) == RECORD_KEYS
    raw = (target / verification.VERIFICATION_EVIDENCE_NAME).read_text(encoding="utf-8")
    expected = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert raw == expected + "\n"


def test_gate_key_pin_is_sorted_nineteen_tuple(verification: Any) -> None:
    keys = verification.GATE_EVIDENCE_KEYS
    assert len(keys) == 19
    assert keys == tuple(sorted(keys))


def test_checks_failed_aggregates_two_tampered_artifacts(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    gate = target / GATE_LIVE
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            '"status":"executed"', '"status":"executed_failed"'
        ),
        encoding="utf-8",
    )
    demo = target / DEMO_LIVE
    demo.write_text(
        demo.read_text(encoding="utf-8").replace("- status: executed\n", "", 1),
        encoding="utf-8",
    )
    exit_code, record = _run(verification, target)
    assert exit_code == verification.FAIL_EXIT
    assert record["checks_failed"] >= 2


def test_constants_pin(verification: Any) -> None:
    assert verification.EXECUTED_STATUS == "executed"
    assert verification.BLOCKED_STATUS == "blocked_not_executed"
    assert verification.OK_EXIT == 0
    assert verification.FAIL_EXIT == 3
    assert verification.VERIFICATION_EVIDENCE_NAME == (
        "phase17_verification_evidence.md"
    )
    assert verification.LIVE_SELECTORS == ("gate_rerun", "demo_rerun")


def test_verification_evidence_written_into_target_dir(
    verification: Any, tmp_path: Path
) -> None:
    target = _copy_artifacts(tmp_path)
    _run(verification, target)
    assert (target / verification.VERIFICATION_EVIDENCE_NAME).is_file()
