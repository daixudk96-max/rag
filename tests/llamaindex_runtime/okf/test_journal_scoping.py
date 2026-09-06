"""Phase 18 W2.1: per-proposal journal scoping (multi-proposal coexistence).

The W2 journal replays the GLOBAL event sequence against the lifecycle
state machine, which raises ``illegal transition: created->created`` as
soon as a second proposal is staged.  Production staging holds many
proposals at once, so the journal must scope the state machine per
``proposal_id`` while keeping every other guarantee (tamper check,
event_id uniqueness, containment) intact.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from llamaindex_runtime.okf.writeback import cli as cli
from llamaindex_runtime.okf.writeback import journal as journal
from llamaindex_runtime.okf.writeback.journal import (
    LifecycleEvent,
    append_event,
    derive_status,
    derive_status_for,
    read_events,
)
from llamaindex_runtime.okf.writeback.proposal import (
    WritebackProposal,
    write_proposal,
)

_A_ID = "32e71258-0224-5d5e-8626-98d3e1b62578"
_B_ID = "22222222-2222-4222-8222-222222222222"
_AT_1 = "2026-09-03T00:00:00Z"
_AT_2 = "2026-09-04T00:00:00Z"
_AT_3 = "2026-09-05T00:00:00Z"


def _created(proposal_id: str, at: str, seed: str) -> LifecycleEvent:
    return LifecycleEvent("created", proposal_id, "agent-1", at, seed * 64)


def _approved(proposal_id: str, at: str, seed: str) -> LifecycleEvent:
    return LifecycleEvent("approved", proposal_id, "human-1", at, seed * 64)


def _journal(tmp_path: Path) -> Path:
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging / "journal.jsonl"


def test_interleaved_two_proposals_are_legal(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    append_event(path, _created(_B_ID, _AT_1, "b"))
    append_event(path, _approved(_A_ID, _AT_2, "a"))
    append_event(path, _approved(_B_ID, _AT_2, "b"))
    events = read_events(path)
    assert len(events) == 4
    assert derive_status_for(events, _A_ID) == "approved"
    assert derive_status_for(events, _B_ID) == "approved"


def test_per_proposal_illegal_transition_still_rejected(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    append_event(path, _created(_B_ID, _AT_1, "b"))
    append_event(path, _approved(_A_ID, _AT_2, "a"))
    with pytest.raises(ValueError, match="illegal transition"):
        append_event(path, _approved(_A_ID, _AT_3, "a"))


def test_global_derive_single_chain_unchanged(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    append_event(path, _approved(_A_ID, _AT_2, "a"))
    assert derive_status(read_events(path)) == "approved"


def test_derive_status_for_unknown_proposal_is_none(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    assert derive_status_for(read_events(path), _B_ID) is None


def test_tamper_check_is_per_proposal(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    append_event(path, _created(_B_ID, _AT_1, "b"))
    append_event(path, _approved(_A_ID, _AT_2, "a"))
    append_event(path, _approved(_B_ID, _AT_2, "b"))
    append_event(path, LifecycleEvent("merged", _B_ID, "human-1", _AT_3, "b" * 64))
    assert derive_status_for(read_events(path), _B_ID) == "merged"


def test_record_creation_second_proposal_ok(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    journal.record_creation(
        path, _A_ID, actor="agent-1", at=_AT_1, payload_digest="a" * 64
    )
    journal.record_creation(
        path, _B_ID, actor="agent-1", at=_AT_2, payload_digest="b" * 64
    )
    assert derive_status_for(read_events(path), _B_ID) == "created"


def test_second_proposal_first_event_must_be_created(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_event(path, _created(_A_ID, _AT_1, "a"))
    with pytest.raises(ValueError, match="first journal event for proposal"):
        append_event(path, _approved(_B_ID, _AT_2, "b"))


def test_cli_list_with_two_proposals(tmp_path: Path) -> None:
    staging = tmp_path / ".staging"
    bundle = tmp_path / "bundle"
    (bundle / "entities").mkdir(parents=True)
    first = WritebackProposal(
        target_file="entities/a.md",
        patch="A",
        reason="add a",
        evidence=("s1",),
        proposed_by="agent-1",
        created_at=_AT_1,
    )
    second = WritebackProposal(
        target_file="entities/b.md",
        patch="B",
        reason="add b",
        evidence=("s2",),
        proposed_by="agent-1",
        created_at=_AT_1,
    )
    write_proposal(staging, first)
    write_proposal(staging, second)
    journal.record_creation(
        staging / "journal.jsonl",
        first.proposal_id,
        actor="agent-1",
        at=_AT_1,
        payload_digest="a" * 64,
    )
    journal.record_creation(
        staging / "journal.jsonl",
        second.proposal_id,
        actor="agent-1",
        at=_AT_1,
        payload_digest="b" * 64,
    )
    out, err = io.StringIO(), io.StringIO()
    rc = cli.run_command(
        ["list"],
        staging_dir=staging,
        journal_path=staging / "journal.jsonl",
        out=out,
        err=err,
    )
    assert rc == 0
    text = out.getvalue()
    assert first.proposal_id in text
    assert second.proposal_id in text


def test_ast_purity_and_no_wall_clock() -> None:
    source = Path(journal.__file__).read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "uuid1" not in source
