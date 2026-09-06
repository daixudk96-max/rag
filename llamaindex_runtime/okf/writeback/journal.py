"""Writeback proposal lifecycle journal (Phase 18 wave-2)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

JOURNAL_VERSION_SEED = "okf-writeback-journal-v1"
STAGING_NAME = ".staging"
EVENT_TYPES = ("created", "approved", "rejected", "merged", "discarded")
REJECTED_REASONS = (
    "low-confidence",
    "contradicted",
    "schema-violating",
    "provenance-violating",
    "imported",
    "manual-review-requested",
)

_TRANSITIONS: dict[str | None, tuple[str, ...]] = {
    None: ("created",),
    "created": ("approved", "rejected"),
    "approved": ("merged", "discarded"),
    "rejected": (),
    "merged": (),
    "discarded": (),
}


def _require_nonblank_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _require_iso_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must match %Y-%m-%dT%H:%M:%SZ")
    if (
        len(value) != 20
        or value[4] != "-"
        or value[7] != "-"
        or value[10] != "T"
        or value[13] != ":"
        or value[16] != ":"
        or value[19] != "Z"
        or not (
            value[0:4].isdigit()
            and value[5:7].isdigit()
            and value[8:10].isdigit()
            and value[11:13].isdigit()
            and value[14:16].isdigit()
            and value[17:19].isdigit()
        )
    ):
        raise ValueError(f"{label} must match %Y-%m-%dT%H:%M:%SZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError(f"{label} must match %Y-%m-%dT%H:%M:%SZ") from None
    return value


def _require_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("payload_digest must be a 64-char lowercase hex digest")
    return value


def _require_proposal_id(value: object) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("proposal_id must be a canonical UUID string")
    try:
        UUID(value)
    except ValueError:
        raise ValueError("proposal_id must be a canonical UUID string") from None
    return value


def make_event_id(event_type: str, proposal_id: str, actor: str, at: str) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown journal event type: " + repr(event_type))
    payload = json.dumps(
        [JOURNAL_VERSION_SEED, event_type, proposal_id, actor, at],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid5(NAMESPACE_URL, payload))


@dataclass(frozen=True, repr=False)
class LifecycleEvent:
    """Immutable journal event (Phase 18 wave-2)."""

    event_type: str
    proposal_id: str
    actor: str
    at: str
    payload_digest: str
    rejected_reason: str | None = field(kw_only=True, default=None)
    event_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError("unknown journal event type: " + repr(self.event_type))
        proposal_id = _require_proposal_id(self.proposal_id)
        actor = _require_nonblank_str(self.actor, "actor")
        at = _require_iso_timestamp(self.at, "at")
        _require_digest(self.payload_digest)
        reason = self.rejected_reason
        if self.event_type == "rejected":
            if reason not in REJECTED_REASONS:
                raise ValueError(
                    "rejected_reason must be one of the frozen reasons: " + repr(reason)
                )
        elif self.event_type == "discarded":
            if reason is not None and reason not in REJECTED_REASONS:
                raise ValueError(
                    "rejected_reason must be one of the frozen reasons: " + repr(reason)
                )
        elif reason is not None:
            raise ValueError("rejected_reason is only valid on rejected events")
        object.__setattr__(
            self, "event_id", make_event_id(self.event_type, proposal_id, actor, at)
        )

    def __repr__(self) -> str:
        return (
            "LifecycleEvent("
            f"event_type={self.event_type!r}, proposal_id={self.proposal_id!r}, "
            f"actor={self.actor!r}, at={self.at!r}, payload_digest=<sha256>, "
            f"rejected_reason={self.rejected_reason!r}, event_id={self.event_id!r})"
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "event_type": self.event_type,
            "proposal_id": self.proposal_id,
            "actor": self.actor,
            "at": self.at,
            "payload_digest": self.payload_digest,
            "rejected_reason": self.rejected_reason,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, raw: object) -> LifecycleEvent:
        if not isinstance(raw, Mapping):
            raise ValueError("journal event must be a mapping")
        required = {
            "event_type",
            "proposal_id",
            "actor",
            "at",
            "payload_digest",
            "rejected_reason",
            "event_id",
        }
        if set(raw) != required:
            raise ValueError("journal event must contain exactly the 7 schema keys")
        event_type = raw["event_type"]
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type must be a non-blank string")
        proposal_id = _require_proposal_id(raw["proposal_id"])
        actor = _require_nonblank_str(raw["actor"], "actor")
        at = _require_iso_timestamp(raw["at"], "at")
        payload_digest = _require_digest(raw["payload_digest"])
        reason = raw["rejected_reason"]
        if reason is not None and not isinstance(reason, str):
            raise ValueError("rejected_reason must be None or a string")
        event_id = _require_nonblank_str(raw["event_id"], "event_id")
        instance = cls(
            event_type=event_type,
            proposal_id=proposal_id,
            actor=actor,
            at=at,
            payload_digest=payload_digest,
            rejected_reason=reason,
        )
        if instance.event_id != event_id:
            raise ValueError("journal event_id mismatch")
        return instance


def derive_status(events: Sequence[object]) -> str | None:
    """Replay journal events against the lifecycle state machine.

    Pinned transition matrix: start->created; created->approved|rejected;
    approved->merged|discarded; rejected/merged/discarded are terminal states
    (any further event raises ValueError "illegal transition: <current>-><new>").
    discarded is never reachable directly from created; a proposal must first
    be reviewed and approved.
    """
    state: str | None = None
    for raw in events:
        if isinstance(raw, LifecycleEvent):
            new = raw.event_type
        elif isinstance(raw, Mapping):
            new = LifecycleEvent.from_dict(raw).event_type
        else:
            raise ValueError("journal event must be a LifecycleEvent or a mapping")
        if new not in _TRANSITIONS[state]:
            raise ValueError("illegal transition: " + str(state) + "->" + new)
        state = new
    return state


def _resolve_staging(journal_path: Path | str) -> Path:
    resolved = Path(journal_path).resolve()
    if (
        resolved.parent.name != STAGING_NAME
        or "raw" in resolved.parts
        or resolved.name != "journal.jsonl"
    ):
        raise ValueError(
            "journal path must resolve to .staging/journal.jsonl outside raw/"
        )
    return resolved


def read_events(journal_path: Path | str) -> tuple[LifecycleEvent, ...]:
    path = Path(journal_path)
    if not path.exists():
        return ()
    events: list[LifecycleEvent] = []
    seen: set[str] = set()
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            raise ValueError(f"journal line {lineno} is not valid JSON") from None
        event = LifecycleEvent.from_dict(raw)
        if event.event_id in seen:
            raise ValueError(f"journal contains duplicate event_id {event.event_id!r}")
        seen.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_event(
    journal_path: Path | str,
    event: LifecycleEvent,
    *,
    payload_digest_check: bool = True,
) -> LifecycleEvent:
    resolved = _resolve_staging(journal_path)
    existing = read_events(resolved)
    if any(other.event_id == event.event_id for other in existing):
        raise ValueError("journal event already recorded: " + event.event_id)
    if not existing:
        if event.event_type != "created":
            raise ValueError("first journal event must be created")
    else:
        prior = [e for e in existing if e.proposal_id == event.proposal_id]
        if not prior:
            if event.event_type != "created":
                raise ValueError(
                    "first journal event for proposal "
                    + event.proposal_id
                    + " must be created"
                )
        else:
            derive_status(tuple(prior) + (event,))
    if payload_digest_check:
        for other in existing:
            if (
                other.proposal_id == event.proposal_id
                and other.payload_digest != event.payload_digest
            ):
                raise ValueError(
                    "proposal payload digest changed after review decision; "
                    "tamper suspected"
                )
    record = json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=False) + "\n"
    with open(resolved, "a", encoding="utf-8") as handle:
        handle.write(record)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    return event


def record_creation(
    journal_path: Path | str,
    proposal_id: str,
    *,
    actor: str,
    at: str,
    payload_digest: str,
) -> LifecycleEvent:
    return append_event(
        journal_path,
        LifecycleEvent("created", proposal_id, actor, at, payload_digest),
    )


def approve(
    journal_path: Path | str,
    proposal_id: str,
    *,
    actor: str,
    at: str,
    payload_digest: str,
) -> LifecycleEvent:
    return append_event(
        journal_path,
        LifecycleEvent("approved", proposal_id, actor, at, payload_digest),
    )


def reject(
    journal_path: Path | str,
    proposal_id: str,
    *,
    actor: str,
    at: str,
    payload_digest: str,
    reason: str,
) -> LifecycleEvent:
    if reason not in REJECTED_REASONS:
        raise ValueError("rejected_reason must be one of the frozen codes")
    return append_event(
        journal_path,
        LifecycleEvent(
            "rejected",
            proposal_id,
            actor,
            at,
            payload_digest,
            rejected_reason=reason,
        ),
    )


def record_merge(
    journal_path: Path | str,
    proposal_id: str,
    *,
    actor: str,
    at: str,
    payload_digest: str,
) -> LifecycleEvent:
    return append_event(
        journal_path,
        LifecycleEvent("merged", proposal_id, actor, at, payload_digest),
    )


def discard(
    journal_path: Path | str,
    proposal_id: str,
    *,
    actor: str,
    at: str,
    payload_digest: str,
    reason: str,
) -> LifecycleEvent:
    if reason not in REJECTED_REASONS:
        raise ValueError("rejected_reason must be one of the frozen codes")
    return append_event(
        journal_path,
        LifecycleEvent(
            "discarded",
            proposal_id,
            actor,
            at,
            payload_digest,
            rejected_reason=reason,
        ),
    )


def derive_status_for(events: Sequence[object], proposal_id: str) -> str | None:
    """Replay only the events of one proposal.

    Scope the journal event sequence to the given proposal_id and replay the
    remaining events through the pinned lifecycle state machine.
    """
    scoped: list[object] = []
    for raw in events:
        if isinstance(raw, LifecycleEvent):
            event = raw
        elif isinstance(raw, Mapping):
            event = LifecycleEvent.from_dict(raw)
        else:
            raise ValueError("journal event must be a LifecycleEvent or a mapping")
        if event.proposal_id == proposal_id:
            scoped.append(event)
    return derive_status(scoped)
