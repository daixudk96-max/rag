"""Writeback proposal lifecycle journal contracts (Phase 18 wave-2; canonical)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from llamaindex_runtime.okf.writeback.journal import (
    EVENT_TYPES,
    JOURNAL_VERSION_SEED,
    REJECTED_REASONS,
    STAGING_NAME,
    LifecycleEvent,
    append_event,
    approve,
    derive_status,
    discard,
    make_event_id,
    read_events,
    record_creation,
    record_merge,
    reject,
)

GOLDEN_PROPOSAL_ID = "32e71258-0224-5d5e-8626-98d3e1b62578"
GOLDEN_APPROVED_EVENT_ID = "a8dadcec-ddab-5578-b8ae-f0e6ba258b64"
GOLDEN_CREATED_EVENT_ID = "aa88340b-8e76-55c9-986a-543ebb3b1c2c"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _event(
    event_type: str,
    *,
    actor: str = "agent-1",
    at: str = "2026-09-03T00:00:00Z",
    digest: str = DIGEST_A,
    reason: str | None = None,
) -> LifecycleEvent:
    return LifecycleEvent(
        event_type=event_type,
        proposal_id=GOLDEN_PROPOSAL_ID,
        actor=actor,
        at=at,
        payload_digest=digest,
        rejected_reason=reason,
    )


def _journal(tmp_path: Path) -> Path:
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging / "journal.jsonl"


def _chain_events(chain: tuple[str, ...]) -> tuple[LifecycleEvent, ...]:
    return tuple(
        _event(t, reason="low-confidence" if t == "rejected" else None) for t in chain
    )


def test_constants_frozen() -> None:
    assert EVENT_TYPES == ("created", "approved", "rejected", "merged", "discarded")
    assert REJECTED_REASONS == (
        "low-confidence",
        "contradicted",
        "schema-violating",
        "provenance-violating",
        "imported",
        "manual-review-requested",
    )
    assert JOURNAL_VERSION_SEED == "okf-writeback-journal-v1"
    assert STAGING_NAME == ".staging"


def test_golden_approved_event_id() -> None:
    assert (
        make_event_id("approved", GOLDEN_PROPOSAL_ID, "human-1", "2026-09-04T00:00:00Z")
        == GOLDEN_APPROVED_EVENT_ID
    )


def test_golden_created_event_id() -> None:
    assert (
        make_event_id("created", GOLDEN_PROPOSAL_ID, "agent-1", "2026-09-03T00:00:00Z")
        == GOLDEN_CREATED_EVENT_ID
    )


def test_event_construction_pins_event_id() -> None:
    event = _event("created")
    assert event.event_id == GOLDEN_CREATED_EVENT_ID


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("archived")
    assert str(excinfo.value) == "unknown journal event type: 'archived'"


def test_invalid_proposal_id_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        LifecycleEvent(
            "created", "not-a-uuid", "agent-1", "2026-09-03T00:00:00Z", DIGEST_A
        )
    assert str(excinfo.value) == "proposal_id must be a canonical UUID string"


def test_blank_actor_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("created", actor="   ")
    assert str(excinfo.value) == "actor must be a non-blank string"


def test_loose_timestamp_rejected() -> None:
    with pytest.raises(ValueError):
        _event("created", at="2026-9-3T00:00:00Z")


@pytest.mark.parametrize(
    "digest",
    ["", "A" * 64, "a" * 63, "g" * 64, "a" * 63 + "G"],
)
def test_bad_digest_rejected(digest: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("created", digest=digest)
    assert str(excinfo.value) == "payload_digest must be a 64-char lowercase hex digest"


def test_rejected_without_reason_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("rejected")
    assert (
        str(excinfo.value) == "rejected_reason must be one of the frozen reasons: None"
    )


def test_rejected_with_unknown_reason_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("rejected", reason="nope")
    assert (
        str(excinfo.value)
        == "rejected_reason must be one of the frozen reasons: 'nope'"
    )


def test_non_rejected_with_reason_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        _event("approved", reason="contradicted")
    assert str(excinfo.value) == "rejected_reason is only valid on rejected events"


def test_event_id_not_constructible() -> None:
    with pytest.raises(TypeError):
        LifecycleEvent(  # type: ignore[call-arg]
            "created",
            GOLDEN_PROPOSAL_ID,
            "agent-1",
            "2026-09-03T00:00:00Z",
            DIGEST_A,
            event_id="00000000-0000-0000-0000-000000000000",
        )


def test_frozen() -> None:
    event = _event("created")
    with pytest.raises(Exception):
        event.event_type = "merged"  # type: ignore[misc]


def test_repr_redacts_payload_digest() -> None:
    event = _event("created")
    rendered = repr(event)
    assert "payload_digest=<sha256>" in rendered
    assert DIGEST_A not in rendered


def test_to_dict_keys_exact() -> None:
    data = _event("created").to_dict()
    assert set(data) == {
        "event_type",
        "proposal_id",
        "actor",
        "at",
        "payload_digest",
        "rejected_reason",
        "event_id",
    }


def test_rejected_reason_in_to_dict() -> None:
    data = _event("rejected", reason="contradicted").to_dict()
    assert data["rejected_reason"] == "contradicted"
    assert data["rejected_reason"] in REJECTED_REASONS
    assert data["payload_digest"] == DIGEST_A


def test_round_trip() -> None:
    event = _event("created")
    assert LifecycleEvent.from_dict(event.to_dict()) == event


def test_from_dict_non_mapping_rejected() -> None:
    for bad in ("nope", 42, ["x"], None):
        with pytest.raises(ValueError):
            LifecycleEvent.from_dict(bad)


def test_from_dict_missing_key_rejected() -> None:
    data = _event("created").to_dict()
    del data["actor"]
    with pytest.raises(ValueError):
        LifecycleEvent.from_dict(data)


def test_from_dict_unknown_key_rejected() -> None:
    data = _event("created").to_dict()
    data["bogus"] = 1
    with pytest.raises(ValueError):
        LifecycleEvent.from_dict(data)


def test_from_dict_event_id_mismatch_rejected() -> None:
    data = _event("created").to_dict()
    data["event_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValueError) as excinfo:
        LifecycleEvent.from_dict(data)
    assert str(excinfo.value) == "journal event_id mismatch"


def test_from_dict_rejected_bad_reason_rejected() -> None:
    data = _event("rejected", reason="contradicted").to_dict()
    data["rejected_reason"] = "nope"
    with pytest.raises(ValueError):
        LifecycleEvent.from_dict(data)


def test_from_dict_non_rejected_with_reason_rejected() -> None:
    data = _event("created").to_dict()
    data["rejected_reason"] = "contradicted"
    with pytest.raises(ValueError):
        LifecycleEvent.from_dict(data)


def test_append_then_read_round_trip(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    created = _event("created")
    approved = _event("approved", actor="human-1", at="2026-09-04T00:00:00Z")
    append_event(journal, created)
    append_event(journal, approved)
    events = read_events(journal)
    assert len(events) == 2
    assert events == (created, approved)
    assert derive_status(events) == "approved"
    assert events[0].event_id == GOLDEN_CREATED_EVENT_ID


def test_append_duplicate_event_id_rejected(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    created = _event("created")
    append_event(journal, created)
    with pytest.raises(ValueError) as excinfo:
        append_event(journal, created)
    assert (
        str(excinfo.value)
        == "journal event already recorded: " + GOLDEN_CREATED_EVENT_ID
    )


def test_append_rejects_non_staging_directory(tmp_path: Path) -> None:
    path = tmp_path / "outbox" / "journal.jsonl"
    path.parent.mkdir(parents=True)
    with pytest.raises(ValueError):
        append_event(path, _event("created"))


def test_append_rejects_raw_component(tmp_path: Path) -> None:
    path = tmp_path / "raw" / ".staging" / "journal.jsonl"
    path.parent.mkdir(parents=True)
    with pytest.raises(ValueError):
        append_event(path, _event("created"))


def test_append_rejects_wrong_filename(tmp_path: Path) -> None:
    journal = _journal(tmp_path).with_name("journal.log")
    with pytest.raises(ValueError):
        append_event(journal, _event("created"))


def test_append_first_event_must_be_created(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        append_event(journal, _event("approved"))
    assert str(excinfo.value) == "first journal event must be created"


def test_append_illegal_transition_rejected(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    append_event(journal, _event("created"))
    append_event(
        journal, _event("approved", actor="human-1", at="2026-09-04T00:00:00Z")
    )
    with pytest.raises(ValueError) as excinfo:
        append_event(
            journal, _event("approved", actor="human-1", at="2026-09-05T00:00:00Z")
        )
    assert str(excinfo.value) == "illegal transition: approved->approved"


def test_append_payload_digest_tamper_rejected(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    append_event(journal, _event("created"))
    with pytest.raises(ValueError) as excinfo:
        append_event(
            journal,
            _event(
                "approved", actor="human-1", at="2026-09-04T00:00:00Z", digest=DIGEST_B
            ),
        )
    assert (
        str(excinfo.value)
        == "proposal payload digest changed after review decision; tamper suspected"
    )


def test_append_payload_digest_check_can_be_disabled(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    append_event(journal, _event("created"))
    changed = _event(
        "approved", actor="human-1", at="2026-09-04T00:00:00Z", digest=DIGEST_B
    )
    append_event(journal, changed, payload_digest_check=False)
    assert read_events(journal)[1] == changed


def test_read_events_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_events(tmp_path / "nope.jsonl") == ()


def test_read_events_bad_json_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    created = json.dumps(_event("created").to_dict(), sort_keys=True)
    path.write_text(created + "\nnot json\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_events(path)
    assert str(excinfo.value) == "journal line 2 is not valid JSON"


def test_read_events_duplicate_event_id(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    line = json.dumps(_event("created").to_dict(), sort_keys=True)
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_events(path)
    assert str(excinfo.value) == (
        "journal contains duplicate event_id 'aa88340b-8e76-55c9-986a-543ebb3b1c2c'"
    )


def test_read_events_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    created = json.dumps(_event("created").to_dict(), sort_keys=True)
    approved = json.dumps(
        _event("approved", actor="human-1", at="2026-09-04T00:00:00Z").to_dict(),
        sort_keys=True,
    )
    path.write_text("\n" + created + "\n\n" + approved + "\n", encoding="utf-8")
    events = read_events(path)
    assert len(events) == 2
    assert derive_status(events) == "approved"


def test_derive_status_empty_is_none() -> None:
    assert derive_status(()) is None


def test_derive_status_accepts_mappings() -> None:
    created = _event("created").to_dict()
    approved = _event("approved", actor="human-1", at="2026-09-04T00:00:00Z").to_dict()
    assert derive_status((created, approved)) == "approved"


def test_derive_status_rejects_invalid_items() -> None:
    with pytest.raises(ValueError):
        derive_status((42,))
    with pytest.raises(ValueError):
        derive_status(("created",))


LEGAL_CHAINS = [
    ((), None),
    (("created",), "created"),
    (("created", "approved"), "approved"),
    (("created", "rejected"), "rejected"),
    (("created", "approved", "merged"), "merged"),
    (("created", "approved", "discarded"), "discarded"),
]


@pytest.mark.parametrize("chain,expected", LEGAL_CHAINS)
def test_legal_transition_chains(chain: tuple[str, ...], expected: str | None) -> None:
    assert derive_status(_chain_events(chain)) == expected


ILLEGAL_TRANSITIONS = [
    (("approved",), "None->approved"),
    (("created", "approved", "approved"), "approved->approved"),
    (("created", "rejected", "merged"), "rejected->merged"),
    (("created", "approved", "merged", "approved"), "merged->approved"),
    (("created", "approved", "discarded", "merged"), "discarded->merged"),
    (("created", "approved", "discarded", "approved"), "discarded->approved"),
    (("created", "merged"), "created->merged"),
    (("created", "discarded"), "created->discarded"),
]


@pytest.mark.parametrize("chain,when", ILLEGAL_TRANSITIONS)
def test_illegal_transition_chains(chain: tuple[str, ...], when: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        derive_status(_chain_events(chain))
    assert str(excinfo.value) == "illegal transition: " + when


def test_record_creation_flow(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    event = record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    assert event.event_type == "created"
    assert derive_status(read_events(journal)) == "created"


def test_approve_gate_from_created(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    approve(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    assert derive_status(read_events(journal)) == "approved"


def test_reject_gate_requires_created(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    reject(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=DIGEST_A,
        reason="low-confidence",
    )
    assert derive_status(read_events(journal)) == "rejected"


def test_reject_gate_bad_reason_code(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    with pytest.raises(ValueError) as excinfo:
        reject(
            journal,
            GOLDEN_PROPOSAL_ID,
            actor="human-1",
            at="2026-09-04T00:00:00Z",
            payload_digest=DIGEST_A,
            reason="nope",
        )
    assert str(excinfo.value) == "rejected_reason must be one of the frozen codes"


def test_discard_gate_requires_approved(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    with pytest.raises(ValueError) as excinfo:
        discard(
            journal,
            GOLDEN_PROPOSAL_ID,
            actor="human-1",
            at="2026-09-04T00:00:00Z",
            payload_digest=DIGEST_A,
            reason="contradicted",
        )
    assert str(excinfo.value) == "illegal transition: created->discarded"


def test_record_merge_gate_requires_approved(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    approve(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    record_merge(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    assert derive_status(read_events(journal)) == "merged"


def test_discard_gate_from_approved(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    approve(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    discard(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
        payload_digest=DIGEST_A,
        reason="contradicted",
    )
    events = read_events(journal)
    assert derive_status(events) == "discarded"
    assert events[-1].rejected_reason == "contradicted"


def test_full_lifecycle_via_gates(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    approve(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    record_merge(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
        payload_digest=DIGEST_A,
    )
    events = read_events(journal)
    assert len(events) == 3
    assert [e.event_type for e in events] == ["created", "approved", "merged"]
    assert derive_status(events) == "merged"


def test_ast_purity_allowlist_and_no_wall_clock() -> None:
    import llamaindex_runtime.okf.writeback.journal as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "json",
        "os",
        "typing",
        "uuid",
        "pathlib",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed, alias.name
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root in allowed, node.module
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "uuid1" not in source
