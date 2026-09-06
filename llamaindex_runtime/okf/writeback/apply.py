"""Phase 18 W4: apply executor - merge an approved proposal into the bundle.

Pinned semantics:
- staging self-check mirrors W1: staging_dir must resolve to a directory named
  '.staging' with no 'raw' path component anywhere in it.
- the durable proposal file must exist at <staging>/<proposal_id>.json.
- journal gate: read_events + derive_status_for must report 'approved'.
- tamper check runs BEFORE any write: sha256 of the proposal file bytes must
  equal the latest journal event's payload_digest for this proposal.
- whitelist re-check (defense in depth) reuses proposal.TARGET_ROOTS.
- body replacement preserves an existing '---' frontmatter block verbatim;
  atomic write via a uuid4-hex *.tmp sibling + os.replace (no leftovers).
- journal.record_merge is appended AFTER the body write; a journal failure
  after a successful body write is recoverable by re-running apply (same
  content, idempotent body rewrite, then the merge event is recorded).
- sync seam: when provided, sync(bundle_root.resolve()) is called AFTER the
  merged journal event is durable; sync exceptions propagate to the caller.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from . import journal
from .proposal import TARGET_ROOTS, WritebackProposal

_STAGING_NAME = ".staging"


def _resolve_staging(staging_dir: Path | str) -> Path:
    """Mirror the W1 staging self-check: '.staging' directory, never under raw/."""
    staging = Path(staging_dir).resolve()
    if staging.name != _STAGING_NAME or "raw" in staging.parts:
        raise ValueError(
            "staging_dir must resolve to a .staging directory outside raw/"
        )
    return staging


def _payload_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_target_file(target_file: str) -> PurePosixPath:
    """Defense-in-depth whitelist re-check mirroring proposal validation."""
    rel = PurePosixPath(target_file)
    if rel.drive or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("target_file must be a relative bundle path")
    if not rel.parts or rel.parts[0] not in TARGET_ROOTS:
        raise ValueError("target_file must live under a writable root")
    return rel


def _merge_content(existing_text: str, patch: str) -> str:
    """Replace the body while preserving an existing '---' frontmatter block."""
    if not patch.endswith("\n"):
        patch += "\n"
    if not existing_text:
        return patch
    lines = existing_text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return patch
    head: str | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            head = "".join(lines[: index + 1])
            break
    if head is None:
        raise ValueError("existing frontmatter block is unterminated")
    if not head.endswith("\n"):
        head += "\n"
    return head + patch


def _atomic_write(target: Path, content: str) -> None:
    """Atomic write: uuid4-hex tmp sibling + os.replace; no leftovers on error."""
    tmp = target.with_name(target.stem + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def apply_proposal(
    proposal: WritebackProposal,
    *,
    bundle_root: Path | str,
    staging_dir: Path | str,
    actor: str,
    at: str,
    sync: Callable[[Path], object] | None = None,
) -> Path:
    """Merge an approved, untampered proposal into the bundle (W4 executor).

    Raises ValueError for staging/proposal/gate/tamper/whitelist/bundle
    violations. When the optional 'sync' callable is provided it is called
    with the resolved bundle root AFTER the merged journal event is durable;
    sync exceptions propagate to the caller. Re-running after a journal
    failure is safe: the body rewrite is idempotent and the merge event is
    recorded on retry.
    """
    staging = _resolve_staging(staging_dir)

    proposal_path = staging / (proposal.proposal_id + ".json")
    if not proposal_path.exists():
        raise ValueError("proposal not found: " + proposal.proposal_id)

    journal_path = staging / "journal.jsonl"
    events = journal.read_events(journal_path)
    status = journal.derive_status_for(events, proposal.proposal_id)
    if status != "approved":
        raise ValueError(
            "proposal must be approved before merge; current status: " + str(status)
        )

    digest = _payload_digest(proposal_path)
    latest_digest: str | None = None
    for event in events:
        if event.proposal_id == proposal.proposal_id:
            latest_digest = event.payload_digest
    if latest_digest != digest:
        raise ValueError(
            "proposal payload digest changed after review decision; " "tamper suspected"
        )

    rel = _validate_target_file(proposal.target_file)

    bundle = Path(bundle_root)
    if not bundle.is_dir():
        raise ValueError("bundle_root must be an existing directory")
    target = bundle.resolve().joinpath(*rel.parts)
    if not target.parent.is_dir():
        raise ValueError("target parent directory does not exist")

    try:
        existing_text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_text = ""
    content = _merge_content(existing_text, proposal.patch)

    _atomic_write(target, content)

    journal.record_merge(
        journal_path=journal_path,
        proposal_id=proposal.proposal_id,
        actor=actor,
        at=at,
        payload_digest=digest,
    )

    if sync is not None:
        sync(bundle.resolve())

    return target
