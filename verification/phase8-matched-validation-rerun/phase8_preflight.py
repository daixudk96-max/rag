"""Phase 8 preflight gate for matched validation rerun.

The gate consumes Phase 7 DB-backed evidence artifacts and fails closed before
retrieval, judgment collection, metrics, or Level assessment work can start.
It writes only sanitized status values and never reads or serializes secrets.
"""

from __future__ import annotations

import json
from pathlib import Path

PHASE8_DIR = Path(__file__).parent
PHASE7_DIR = PHASE8_DIR.parent / "phase7-db-backed-evidence-chain-rerun"
EVIDENCE_DELTA_FILE = PHASE7_DIR / "evidence_chain_delta.json"
DB_READINESS_FILE = PHASE7_DIR / "db_readiness.json"
OUTPUT_FILE = PHASE8_DIR / "phase8_preflight_status.json"
REMEDIATION_FILE = PHASE8_DIR / "remediation_required.json"

READY_STATUS = "READY_FOR_MATCHED_VALIDATION"
REMEDIATION_STATUS = "EVIDENCE_CHAIN_REMEDIATION_REQUIRED"
MISSING_STATUS = "PHASE7_EVIDENCE_MISSING"
LEVEL_BASELINE = "Level 2 remains authoritative"
REQUIREMENT_ID = "REQ-P8-MATCHED-VALIDATION-RERUN"


def load_json(path: Path) -> dict[str, object]:
    """Load a JSON object from a path, returning an empty object if absent."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_codes(*groups: object) -> list[str]:
    """Return unique sanitized blocker reason codes from list-like values."""
    reasons: list[str] = []
    for group in groups:
        if not isinstance(group, list):
            continue
        for reason in group:
            text = str(reason)
            if text and text not in reasons:
                reasons.append(text)
    return reasons


def _string_field(payload: dict[str, object], key: str) -> str | None:
    """Return a string JSON field or None when the field has an unexpected type."""
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _bool_field(payload: dict[str, object], key: str) -> bool:
    """Return a boolean JSON field, treating unexpected types as False."""
    value = payload.get(key)
    return value if isinstance(value, bool) else False


def build_preflight_status() -> dict[str, object]:
    """Build the Phase 8 preflight status from Phase 7 sanitized artifacts."""
    evidence_delta = load_json(EVIDENCE_DELTA_FILE)
    db_readiness = load_json(DB_READINESS_FILE)

    final_classification = (
        _string_field(evidence_delta, "final_classification")
        or "missing_phase7_evidence"
    )
    active_version_id = _string_field(
        evidence_delta, "active_version_id"
    ) or _string_field(db_readiness, "active_version_id")
    database_url_configured = _bool_field(db_readiness, "database_url_configured")
    blocking_reasons = _reason_codes(
        evidence_delta.get("blocking_reasons"),
        db_readiness.get("blocking_reasons"),
    )

    if final_classification == "DB_EVIDENCE_READY":
        ready = True
        status = READY_STATUS
        next_allowed_action = "run_matched_retrieval"
        blocking_reasons = []
    elif final_classification == "DB_EVIDENCE_BLOCKED":
        ready = False
        status = REMEDIATION_STATUS
        next_allowed_action = "fix_evidence_chain_before_phase8"
        if not blocking_reasons:
            blocking_reasons = ["phase7_evidence_blocked"]
    else:
        ready = False
        status = MISSING_STATUS
        next_allowed_action = "fix_evidence_chain_before_phase8"
        blocking_reasons = blocking_reasons or ["phase7_evidence_missing"]

    return {
        "requirement_id": REQUIREMENT_ID,
        "phase7_final_classification": final_classification,
        "database_url_configured": database_url_configured,
        "active_version_id": active_version_id,
        "ready_for_matched_validation": ready,
        "status": status,
        "blocking_reasons": blocking_reasons,
        "next_allowed_action": next_allowed_action,
        "level_baseline": LEVEL_BASELINE,
    }


def write_outputs(status: dict[str, object]) -> None:
    """Write preflight status and remediation evidence when blocked."""
    PHASE8_DIR.mkdir(parents=True, exist_ok=True)
    output_text = json.dumps(status, indent=2, ensure_ascii=False)
    OUTPUT_FILE.write_text(output_text, encoding="utf-8")
    if status.get("status") == REMEDIATION_STATUS:
        REMEDIATION_FILE.write_text(output_text, encoding="utf-8")
    elif REMEDIATION_FILE.exists():
        REMEDIATION_FILE.unlink()


def main() -> int:
    """CLI entry point for Phase 8 preflight."""
    status = build_preflight_status()
    write_outputs(status)
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status.get("ready_for_matched_validation") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
