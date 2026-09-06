"""Writeback proposal durable schema (Phase 18 wave-1)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid4, uuid5

WRITEBACK_PROPOSAL_NAMESPACE_SEED = "okf-writeback-proposal-v1"
TARGET_ROOTS = ("entities", "concepts", "synthesis")


@dataclass(frozen=True)
class WritebackProposal:
    """Immutable durable schema for a writeback proposal (Phase 18 wave-1)."""

    target_file: str
    patch: str
    reason: str
    evidence: tuple[str, ...]
    proposed_by: str
    created_at: str
    status: str = field(init=False)
    unverified: bool = field(init=False)
    proposal_id: str = field(init=False)

    def __post_init__(self) -> None:
        evidence = self._normalize_evidence(self.evidence)
        target_file = self._require_nonblank_str("target_file", self.target_file)
        if target_file != target_file.strip():
            raise ValueError("target_file must not have leading or trailing whitespace")
        self._validate_target_file_root(target_file)
        patch = self._require_nonblank_str("patch", self.patch)
        reason = self._require_nonblank_str("reason", self.reason)
        proposed_by = self._require_nonblank_str("proposed_by", self.proposed_by)
        created_at = self._require_created_at(self.created_at)
        proposal_id = str(
            uuid5(
                NAMESPACE_URL,
                json.dumps(
                    [
                        WRITEBACK_PROPOSAL_NAMESPACE_SEED,
                        target_file,
                        patch,
                        reason,
                        proposed_by,
                        created_at,
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "status", "created")
        object.__setattr__(self, "unverified", len(evidence) == 0)
        object.__setattr__(self, "proposal_id", proposal_id)

    @staticmethod
    def _require_nonblank_str(name: str, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-blank string")
        return value

    @staticmethod
    def _validate_target_file_root(target_file: str) -> None:
        path = PurePosixPath(target_file)
        if path.drive or path.is_absolute() or ".." in path.parts:
            raise ValueError("target_file must be a relative bundle path")
        first = target_file.split("/", 1)[0]
        if first not in TARGET_ROOTS:
            raise ValueError("target_file must live under a writable root")

    @staticmethod
    def _require_created_at(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("created_at must be a string")
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
            raise ValueError("created_at must match %Y-%m-%dT%H:%M:%SZ")
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise ValueError("created_at must match %Y-%m-%dT%H:%M:%SZ") from None
        return value

    @staticmethod
    def _normalize_evidence(value: object) -> tuple[str, ...]:
        if isinstance(value, (str, bytes, set)) or not isinstance(value, (list, tuple)):
            raise ValueError("evidence must be a list or tuple of non-empty strings")
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("evidence items must be non-empty strings")
            items.append(item)
        return tuple(items)

    def to_dict(self) -> dict[str, str | list[str] | bool]:
        """Return the durable JSON payload (9 keys, evidence as a list)."""
        return {
            "target_file": self.target_file,
            "patch": self.patch,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "proposed_by": self.proposed_by,
            "created_at": self.created_at,
            "status": self.status,
            "unverified": self.unverified,
            "proposal_id": self.proposal_id,
        }

    @classmethod
    def from_dict(cls, raw: object) -> WritebackProposal:
        """Rehydrate a persisted proposal from its durable JSON payload.

        Wave-1 deliberately supports rehydration of the 'created' status
        only; other lifecycle statuses land with the W2 state machine.
        """
        if not isinstance(raw, dict):
            raise ValueError("proposal must be a mapping")
        required = {
            "target_file",
            "patch",
            "reason",
            "evidence",
            "proposed_by",
            "created_at",
            "status",
            "unverified",
            "proposal_id",
        }
        if set(raw) != required:
            raise ValueError("proposal mapping must contain exactly the 9 schema keys")
        target_file = cls._require_nonblank_str("target_file", raw["target_file"])
        patch = cls._require_nonblank_str("patch", raw["patch"])
        reason = cls._require_nonblank_str("reason", raw["reason"])
        proposed_by = cls._require_nonblank_str("proposed_by", raw["proposed_by"])
        created_at = cls._require_created_at(raw["created_at"])
        evidence = raw["evidence"]
        if not isinstance(evidence, (list, tuple)) or not all(
            isinstance(item, str) for item in evidence
        ):
            raise ValueError("evidence must be a list or tuple of non-empty strings")
        status = raw["status"]
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-blank string")
        if status != "created":
            raise ValueError(
                f"durable status {status!r} is not rehydratable until the W2 lifecycle state machine; wave-1 supports 'created' only"
            )
        if not isinstance(raw["unverified"], bool):
            raise ValueError("unverified must be a boolean")
        given_proposal_id = cls._require_nonblank_str("proposal_id", raw["proposal_id"])
        instance = cls(
            target_file=target_file,
            patch=patch,
            reason=reason,
            evidence=tuple(evidence),
            proposed_by=proposed_by,
            created_at=created_at,
        )
        if instance.proposal_id != given_proposal_id:
            raise ValueError("proposal_id does not match the proposal inputs")
        return instance


def _remove_if_empty(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size == 0:
            path.unlink()
    except OSError:
        pass


def _remove_tmp(tmp: Path) -> None:
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass


def write_proposal(staging_dir: Path, proposal: WritebackProposal) -> Path:
    """Persist a proposal JSON atomically under a .staging directory."""
    destination_dir = Path(staging_dir).resolve()
    if destination_dir.name != ".staging" or "raw" in destination_dir.parts:
        raise ValueError(
            "staging_dir must resolve to a .staging directory outside raw/"
        )
    destination_dir.mkdir(parents=True, exist_ok=True)
    path = destination_dir / (proposal.proposal_id + ".json")
    if os.path.lexists(path):
        raise ValueError(f"proposal already exists: {proposal.proposal_id}")
    content = (
        json.dumps(
            proposal.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    try:
        os.close(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise ValueError(f"proposal already exists: {proposal.proposal_id}") from None
    tmp = path.with_name(path.stem + "." + uuid4().hex + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        _remove_tmp(tmp)
        _remove_if_empty(path)
        raise
    return path


def read_proposal(path: Path) -> WritebackProposal:
    """Load a persisted proposal JSON file back into a WritebackProposal."""
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposal file was not valid JSON: {exc}") from None
    return WritebackProposal.from_dict(raw)
