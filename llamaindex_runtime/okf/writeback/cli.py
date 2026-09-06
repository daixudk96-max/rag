"""okf-writeback — human review CLI for writeback proposals (Phase 18 wave-3).

Exit codes (pinned):
    0: success
    1: proposal not found
    2: illegal transition or invalid argument/reason
    3: payload digest changed (tamper suspected)

Discipline: this CLI only appends lifecycle events to the journal. It never
writes bundle body files and never modifies proposal JSON files; proposal
files are read-only inputs to list/show/review decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, TextIO

from . import journal as J
from .proposal import read_proposal

_NOW_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_TAMPER_MARKER = "tamper suspected"


def _now_utc() -> str:
    """CLI adapter: current UTC time in the pinned journal timestamp format."""
    return datetime.now(timezone.utc).strftime(_NOW_FORMAT)


def _proposal_path(staging_dir: Path, proposal_id: str) -> Path:
    return staging_dir / (proposal_id + ".json")


def _payload_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _journal_events(journal_path: Path) -> Sequence[object] | None:
    """Read journal events; a missing or malformed journal yields None."""
    try:
        return J.read_events(journal_path)
    except ValueError:
        return None


def _handle_gate_error(message: str, err: TextIO) -> int:
    if _TAMPER_MARKER in message:
        err.write(message + "\n")
        return 3
    err.write("error: " + message + "\n")
    return 2


def _do_list(staging: Path, journal: Path, out: TextIO) -> int:
    files = sorted(staging.glob("*.json"))
    if not files:
        out.write("no proposals\n")
        return 0
    events = _journal_events(journal)
    malformed: list[str] = []
    rows: list[tuple[str, str, bool]] = []
    for path in files:
        try:
            proposal = read_proposal(path)
        except ValueError:
            malformed.append(f"MALFORMED {path.stem}")
            continue
        rows.append((proposal.proposal_id, proposal.target_file, proposal.unverified))
    for line in malformed:
        out.write(line + "\n")
    for proposal_id, target_file, unverified in sorted(rows):
        status = (
            J.derive_status_for(events, proposal_id) if events is not None else None
        )
        line = f"{(status or 'created')}  {proposal_id}  {target_file}"
        if unverified:
            line += "  [unverified]"
        out.write(line + "\n")
    return 0


def _do_show(
    staging: Path, journal: Path, proposal_id: str, out: TextIO, err: TextIO
) -> int:
    path = _proposal_path(staging, proposal_id)
    if not path.exists():
        err.write("proposal not found\n")
        return 1
    try:
        proposal = read_proposal(path)
    except ValueError as exc:
        err.write("error: " + str(exc) + "\n")
        return 2
    events = _journal_events(journal)
    status = (
        J.derive_status_for(events, proposal.proposal_id)
        if events is not None
        else None
    ) or "created"
    out.write(json.dumps(proposal.to_dict(), sort_keys=True, indent=2) + "\n")
    out.write("status: " + status + "\n")
    return 0


def _do_approve(
    staging: Path,
    journal: Path,
    proposal_id: str,
    actor: str,
    at: str,
    out: TextIO,
    err: TextIO,
) -> int:
    path = _proposal_path(staging, proposal_id)
    if not path.exists():
        err.write("proposal not found: " + proposal_id + "\n")
        return 1
    digest = _payload_digest(path)
    try:
        J.approve(journal, proposal_id, actor=actor, at=at, payload_digest=digest)
    except ValueError as exc:
        return _handle_gate_error(str(exc), err)
    out.write("approved: " + proposal_id + "\n")
    return 0


def _do_reject(
    staging: Path,
    journal: Path,
    proposal_id: str,
    actor: str,
    at: str,
    reason: str,
    out: TextIO,
    err: TextIO,
) -> int:
    path = _proposal_path(staging, proposal_id)
    if not path.exists():
        err.write("proposal not found: " + proposal_id + "\n")
        return 1
    digest = _payload_digest(path)
    try:
        J.reject(
            journal,
            proposal_id,
            actor=actor,
            at=at,
            payload_digest=digest,
            reason=reason,
        )
    except ValueError as exc:
        return _handle_gate_error(str(exc), err)
    out.write(f"rejected: {proposal_id} ({reason})\n")
    return 0


def _do_discard(
    staging: Path,
    journal: Path,
    proposal_id: str,
    actor: str,
    at: str,
    reason: str,
    out: TextIO,
    err: TextIO,
) -> int:
    path = _proposal_path(staging, proposal_id)
    if not path.exists():
        err.write("proposal not found: " + proposal_id + "\n")
        return 1
    digest = _payload_digest(path)
    try:
        J.discard(
            journal,
            proposal_id,
            actor=actor,
            at=at,
            payload_digest=digest,
            reason=reason,
        )
    except ValueError as exc:
        return _handle_gate_error(str(exc), err)
    out.write("discarded: " + proposal_id + "\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okf-writeback")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list staged proposals")

    p_show = sub.add_parser("show", help="show a proposal in full")
    p_show.add_argument("proposal_id")

    p_approve = sub.add_parser("approve", help="approve a proposal")
    p_approve.add_argument("proposal_id")
    p_approve.add_argument("--actor", required=True)
    p_approve.add_argument("--at", default=None)

    p_reject = sub.add_parser("reject", help="reject a proposal")
    p_reject.add_argument("proposal_id")
    p_reject.add_argument("--actor", required=True)
    p_reject.add_argument("--reason", required=True)
    p_reject.add_argument("--at", default=None)

    p_discard = sub.add_parser("discard", help="discard an approved proposal")
    p_discard.add_argument("proposal_id")
    p_discard.add_argument("--actor", required=True)
    p_discard.add_argument("--reason", required=True)
    p_discard.add_argument("--at", default=None)
    return parser


def run_command(
    argv: Sequence[str],
    *,
    staging_dir: str | Path,
    journal_path: str | Path,
    out: TextIO,
    err: TextIO,
) -> int:
    """Execute one okf-writeback command; returns the pinned exit code.

    argparse errors (unknown arguments, missing required flags, no command)
    surface as SystemExit(2) and propagate to the caller.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    staging = Path(staging_dir).resolve()
    journal = Path(journal_path)

    if args.command == "list":
        return _do_list(staging, journal, out)

    proposal_id = args.proposal_id
    if args.command == "show":
        return _do_show(staging, journal, proposal_id, out, err)

    at = args.at if args.at is not None else _now_utc()
    if args.command == "approve":
        return _do_approve(staging, journal, proposal_id, args.actor, at, out, err)

    reason = args.reason
    if reason not in J.REJECTED_REASONS:
        err.write(f"invalid --reason {reason}\n")
        return 2
    if args.command == "reject":
        return _do_reject(
            staging, journal, proposal_id, args.actor, at, reason, out, err
        )
    if args.command == "discard":
        return _do_discard(
            staging, journal, proposal_id, args.actor, at, reason, out, err
        )
    raise AssertionError(f"unreachable command {args.command!r}")
