"""Consume on-disk Phase 17 evidence artifacts (17-VER pattern, Phase 16-18).

This orchestrator reads the Phase 17 evidence artifacts already on disk and
verifies their integrity.  It does NOT re-run live gates, does NOT fabricate
evidence, and touches no database, no model, and no network.  Both live
selectors (gate_rerun, demo_rerun) are default-denied: re-running them needs a
disposable PG instance plus real LLM and DashScope access, so they serialize as
blocked_not_executed and are never auto-run.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Final

EXECUTED_STATUS: Final = "executed"
BLOCKED_STATUS: Final = "blocked_not_executed"
OK_EXIT: Final = 0
FAIL_EXIT: Final = 3
VERIFICATION_EVIDENCE_NAME: Final = "phase17_verification_evidence.md"
LIVE_SELECTORS: Final = ("gate_rerun", "demo_rerun")

GATE_EVIDENCE_NAME: Final = "graph_recall_acceptance_evidence.md"
GATE_FIRST_ARCHIVE_NAME: Final = (
    "graph_recall_acceptance_evidence_executed_2026-09-03.md"
)
GATE_DEEPSEEK_ARCHIVE_NAME: Final = (
    "graph_recall_acceptance_evidence_executed_deepseek_2026-09-03.md"
)
GATE_PRE_FIX17_ARCHIVE_NAME: Final = (
    "graph_recall_acceptance_evidence_pre_fix17_2026-09-03.md"
)
GATE_LLM500_ARCHIVE_NAME: Final = (
    "graph_recall_acceptance_evidence_llm500_2026-09-03.md"
)
DEMO_REPORT_NAME: Final = "phase17_demo_report.md"
DEMO_FIRST_ARCHIVE_NAME: Final = "phase17_demo_report_executed_2026-09-03.md"
DEMO_DEEPSEEK_ARCHIVE_NAME: Final = (
    "phase17_demo_report_executed_deepseek_2026-09-03.md"
)
DEMO_PRE_FIX17_ARCHIVE_NAME: Final = "phase17_demo_report_pre_fix17_2026-09-03.md"

# sha256 pins verified by the coordinator on 2026-09-04.  The deepseek-era
# archives are byte-identical to the live artifacts, so their pins alias the
# live pins.
GATE_LIVE_SHA: Final = (
    "853bb353db2ee566082c1276f35afea9597321d961ff9bbcb45f4587b3d9fce4"
)
GATE_DEEPSEEK_ARCHIVE_SHA: Final = GATE_LIVE_SHA
GATE_FIRST_ARCHIVE_SHA: Final = (
    "20a4de975fbac845e4295c4bccb82020f3f79aa262996dda97dec12011401fe1"
)
GATE_LLM500_ARCHIVE_SHA: Final = (
    "cda8790aab4bdeaa64826341b8be8f697cd4b9ffdd9a5e804f24ba184fa2f394"
)
DEMO_LIVE_SHA: Final = (
    "c2ae8ea3bede7ff97451c59a0db6a9f5565eea66def0effe13587c7825c90325"
)
DEMO_DEEPSEEK_ARCHIVE_SHA: Final = DEMO_LIVE_SHA
DEMO_FIRST_ARCHIVE_SHA: Final = (
    "9ea91f0d7406e5a783037a11fc899d039f951b8eab484c47570bba5a3520622e"
)

GATE_EVIDENCE_KEYS: Final = (
    "basket_items",
    "basket_pending",
    "batch_id",
    "coverage_ratio",
    "exit_code",
    "fusion_max_score",
    "identities_count",
    "ingest_chunks",
    "ingest_entities",
    "ingest_relations",
    "mentions_count",
    "recall_hit_count",
    "rejected_mentions_count",
    "relations_pending",
    "relations_supported",
    "relations_total",
    "relations_unlinked",
    "route",
    "status",
)


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_gate_evidence_contract(directory: Path) -> list[str]:
    path = directory / GATE_EVIDENCE_NAME
    if not path.is_file():
        return [GATE_EVIDENCE_NAME + ": gate evidence file is missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return [GATE_EVIDENCE_NAME + ": gate evidence is not valid JSON"]
    if not isinstance(payload, dict):
        return [GATE_EVIDENCE_NAME + ": gate evidence is not a JSON object"]
    failures: list[str] = []
    if set(payload.keys()) != set(GATE_EVIDENCE_KEYS):
        failures.append(GATE_EVIDENCE_NAME + ": gate evidence key set mismatch")
    if payload.get("status") != EXECUTED_STATUS:
        failures.append(GATE_EVIDENCE_NAME + ": gate status is not executed")
    if payload.get("exit_code") != 0:
        failures.append(GATE_EVIDENCE_NAME + ": gate exit_code is not 0")
    recall = payload.get("recall_hit_count")
    if not isinstance(recall, int) or isinstance(recall, bool) or recall < 1:
        failures.append(GATE_EVIDENCE_NAME + ": recall_hit_count is not >= 1")
    entities = payload.get("ingest_entities")
    if not isinstance(entities, int) or isinstance(entities, bool) or entities <= 0:
        failures.append(GATE_EVIDENCE_NAME + ": ingest_entities is not > 0")
    if payload.get("route") != "PURE_UIE":
        failures.append(GATE_EVIDENCE_NAME + ": route is not PURE_UIE")
    return failures


def _check_gate_live_sha(directory: Path) -> list[str]:
    if _sha256_file(directory / GATE_EVIDENCE_NAME) != GATE_LIVE_SHA:
        return [GATE_EVIDENCE_NAME + ": sha256 does not match the live pin"]
    return []


def _check_gate_deepseek_archive_sha(directory: Path) -> list[str]:
    if _sha256_file(directory / GATE_DEEPSEEK_ARCHIVE_NAME) != (
        GATE_DEEPSEEK_ARCHIVE_SHA
    ):
        return [GATE_DEEPSEEK_ARCHIVE_NAME + ": sha256 does not match the pin"]
    return []


def _check_gate_first_archive_pair(directory: Path) -> list[str]:
    failures: list[str] = []
    if _sha256_file(directory / GATE_FIRST_ARCHIVE_NAME) != GATE_FIRST_ARCHIVE_SHA:
        failures.append(GATE_FIRST_ARCHIVE_NAME + ": sha256 does not match the pin")
    if _sha256_file(directory / GATE_PRE_FIX17_ARCHIVE_NAME) != GATE_FIRST_ARCHIVE_SHA:
        failures.append(GATE_PRE_FIX17_ARCHIVE_NAME + ": sha256 does not match the pin")
    return failures


def _check_gate_llm500_archive_sha(directory: Path) -> list[str]:
    if _sha256_file(directory / GATE_LLM500_ARCHIVE_NAME) != (GATE_LLM500_ARCHIVE_SHA):
        return [GATE_LLM500_ARCHIVE_NAME + ": sha256 does not match the pin"]
    return []


def _check_demo_live_sha(directory: Path) -> list[str]:
    if _sha256_file(directory / DEMO_REPORT_NAME) != DEMO_LIVE_SHA:
        return [DEMO_REPORT_NAME + ": sha256 does not match the live pin"]
    return []


def _check_demo_deepseek_archive_sha(directory: Path) -> list[str]:
    if _sha256_file(directory / DEMO_DEEPSEEK_ARCHIVE_NAME) != (
        DEMO_DEEPSEEK_ARCHIVE_SHA
    ):
        return [DEMO_DEEPSEEK_ARCHIVE_NAME + ": sha256 does not match the pin"]
    return []


def _check_demo_first_archive_pair(directory: Path) -> list[str]:
    failures: list[str] = []
    if _sha256_file(directory / DEMO_FIRST_ARCHIVE_NAME) != DEMO_FIRST_ARCHIVE_SHA:
        failures.append(DEMO_FIRST_ARCHIVE_NAME + ": sha256 does not match the pin")
    if _sha256_file(directory / DEMO_PRE_FIX17_ARCHIVE_NAME) != DEMO_FIRST_ARCHIVE_SHA:
        failures.append(DEMO_PRE_FIX17_ARCHIVE_NAME + ": sha256 does not match the pin")
    return failures


def _check_demo_report_contract(directory: Path) -> list[str]:
    path = directory / DEMO_REPORT_NAME
    if not path.is_file():
        return [DEMO_REPORT_NAME + ": demo report file is missing"]
    report = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if "## batch: similar" not in report:
        failures.append(DEMO_REPORT_NAME + ": '## batch: similar' section missing")
    if "## batch: mixed" not in report:
        failures.append(DEMO_REPORT_NAME + ": '## batch: mixed' section missing")
    if report.count("status: executed") != 2:
        failures.append(DEMO_REPORT_NAME + ": expected exactly 2 'status: executed'")
    if report.count("route: PURE_UIE") != 2:
        failures.append(DEMO_REPORT_NAME + ": expected exactly 2 'route: PURE_UIE'")
    return failures


_CHECKS: Final = (
    ("gate_evidence_contract", _check_gate_evidence_contract),
    ("gate_live_sha", _check_gate_live_sha),
    ("gate_deepseek_archive_sha", _check_gate_deepseek_archive_sha),
    ("gate_first_archive_pair", _check_gate_first_archive_pair),
    ("gate_llm500_archive_sha", _check_gate_llm500_archive_sha),
    ("demo_live_sha", _check_demo_live_sha),
    ("demo_deepseek_archive_sha", _check_demo_deepseek_archive_sha),
    ("demo_first_archive_pair", _check_demo_first_archive_pair),
    ("demo_report_contract", _check_demo_report_contract),
)


def _gate_record_fields(
    directory: Path,
) -> tuple[str | None, int | None, int | None, int | None]:
    try:
        payload = json.loads(
            (directory / GATE_EVIDENCE_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None, None, None, None
    if not isinstance(payload, dict):
        return None, None, None, None
    status = payload.get("status")
    exit_code = payload.get("exit_code")
    recall = payload.get("recall_hit_count")
    entities = payload.get("ingest_entities")

    def _int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return (
        status if isinstance(status, str) else None,
        _int(exit_code),
        _int(recall),
        _int(entities),
    )


def _demo_batches_executed(directory: Path) -> int:
    path = directory / DEMO_REPORT_NAME
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("status: executed")


def serialize_evidence(record: dict[str, object]) -> str:
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    )


def main(argv: list[str], *, verification_dir: Path) -> int:
    if argv:
        raise ValueError("verification runner takes no command line arguments")
    failures: list[str] = []
    for _name, check in _CHECKS:
        failures.extend(check(verification_dir))
    gate_status, gate_exit_code, recall_hit_count, ingest_entities = (
        _gate_record_fields(verification_dir)
    )
    record: dict[str, object] = {
        "gate_evidence_sha256": _sha256_file(verification_dir / GATE_EVIDENCE_NAME),
        "demo_report_sha256": _sha256_file(verification_dir / DEMO_REPORT_NAME),
        "gate_status": gate_status,
        "gate_exit_code": gate_exit_code,
        "recall_hit_count": recall_hit_count,
        "ingest_entities": ingest_entities,
        "demo_batches_executed": _demo_batches_executed(verification_dir),
        "live_selectors": {name: BLOCKED_STATUS for name in LIVE_SELECTORS},
        "verification_status": ("verified" if not failures else "verification_failed"),
        "checks_run": len(_CHECKS),
        "checks_failed": len(failures),
    }
    evidence_path = verification_dir / VERIFICATION_EVIDENCE_NAME
    evidence_path.write_text(serialize_evidence(record), encoding="utf-8")
    return OK_EXIT if not failures else FAIL_EXIT


if __name__ == "__main__":
    raise SystemExit(
        main(sys.argv[1:], verification_dir=Path(__file__).resolve().parent)
    )
