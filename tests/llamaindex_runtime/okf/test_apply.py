"""Phase 18 W4: apply executor (approved proposal -> bundle body, journal-gated)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

from llamaindex_runtime.okf.writeback import journal as journal
from llamaindex_runtime.okf.writeback.apply import apply_proposal
from llamaindex_runtime.okf.writeback.proposal import (
    WritebackProposal,
    write_proposal,
)


def _proposal() -> WritebackProposal:
    return WritebackProposal(
        target_file="entities/org/huawei.md",
        patch="华为是一家公司",
        reason="evidence-backed add",
        evidence=("span-1",),
        proposed_by="agent-1",
        created_at="2026-09-03T00:00:00Z",
    )


def _setup(
    tmp_path: Path,
    *,
    approved: bool = True,
    existing: str | None = "---\ntype: entity\nname: 华为\n---\nold body\n",
) -> tuple[Path, Path, WritebackProposal]:
    staging = tmp_path / ".staging"
    bundle = tmp_path / "bundle"
    (bundle / "entities" / "org").mkdir(parents=True)
    proposal = _proposal()
    write_proposal(staging, proposal)
    proposal_path = staging / (proposal.proposal_id + ".json")
    digest = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    journal.record_creation(
        staging / "journal.jsonl",
        proposal.proposal_id,
        actor="agent-1",
        at="2026-09-03T00:00:00Z",
        payload_digest=digest,
    )
    if approved:
        journal.approve(
            staging / "journal.jsonl",
            proposal.proposal_id,
            actor="human-1",
            at="2026-09-04T00:00:00Z",
            payload_digest=digest,
        )
    if existing is not None:
        (bundle / "entities" / "org" / "huawei.md").write_text(
            existing, encoding="utf-8"
        )
    return staging, bundle, proposal


def test_happy_path_replaces_body_preserving_frontmatter(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    returned = apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    content = (bundle / "entities" / "org" / "huawei.md").read_text(encoding="utf-8")
    assert content == "---\ntype: entity\nname: 华为\n---\n华为是一家公司\n"
    events = journal.read_events(staging / "journal.jsonl")
    assert events[-1].event_type == "merged"
    assert journal.derive_status_for(events, proposal.proposal_id) == "merged"
    assert returned == bundle / "entities" / "org" / "huawei.md"


def test_gate_rejects_created(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path, approved=False)
    with pytest.raises(ValueError, match="proposal must be approved before merge"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )


def test_gate_rejects_remerged(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    with pytest.raises(ValueError, match="proposal must be approved before merge"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-06T00:00:00Z",
        )


def test_gate_rejects_rejected(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path, approved=False)
    digest = hashlib.sha256(
        (staging / (proposal.proposal_id + ".json")).read_bytes()
    ).hexdigest()
    journal.reject(
        staging / "journal.jsonl",
        proposal.proposal_id,
        actor="human-1",
        at="2026-09-04T00:00:00Z",
        payload_digest=digest,
        reason="low-confidence",
    )
    with pytest.raises(ValueError, match="proposal must be approved before merge"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )


def test_tampered_proposal_file_rejected_before_write(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    target = bundle / "entities" / "org" / "huawei.md"
    before = target.read_text(encoding="utf-8")
    path = staging / (proposal.proposal_id + ".json")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "evidence-backed add", "evidence-backed HACK"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tamper suspected"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )
    assert target.read_text(encoding="utf-8") == before


def test_existing_file_without_frontmatter_replaced(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path, existing="plain old body")
    apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    content = (bundle / "entities" / "org" / "huawei.md").read_text(encoding="utf-8")
    assert content == "华为是一家公司\n"


def test_new_file_created_when_parent_exists(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path, existing=None)
    apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    content = (bundle / "entities" / "org" / "huawei.md").read_text(encoding="utf-8")
    assert content == "华为是一家公司\n"


def test_missing_parent_directory_rejected(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path, existing=None)
    (bundle / "entities" / "org").rmdir()
    with pytest.raises(ValueError, match="target parent directory does not exist"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )


def test_no_tmp_leftovers_after_success(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    leftovers = [item.name for item in bundle.rglob("*.tmp")] + [
        item.name for item in staging.glob("*.tmp")
    ]
    assert leftovers == []


def test_sync_seam_invoked_with_bundle_root(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    calls: list[Path] = []
    apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
        sync=cast(Any, calls.append),
    )
    assert len(calls) == 1
    assert calls[0] == bundle.resolve()


def test_sync_omitted_runs_clean(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    returned = apply_proposal(
        proposal,
        bundle_root=bundle,
        staging_dir=staging,
        actor="human-1",
        at="2026-09-05T00:00:00Z",
    )
    assert returned == bundle / "entities" / "org" / "huawei.md"


def test_sync_failure_propagates_after_merge_recorded(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)

    def boom(root: Path) -> int:
        raise RuntimeError("sync down")

    with pytest.raises(RuntimeError, match="sync down"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
            sync=boom,
        )
    events = journal.read_events(staging / "journal.jsonl")
    assert journal.derive_status_for(events, proposal.proposal_id) == "merged"


def test_missing_bundle_root_rejected(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    with pytest.raises(ValueError, match="bundle_root must be an existing directory"):
        apply_proposal(
            proposal,
            bundle_root=tmp_path / "absent",
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )


def test_proposal_file_missing_rejected(tmp_path: Path) -> None:
    staging, bundle, proposal = _setup(tmp_path)
    (staging / (proposal.proposal_id + ".json")).unlink()
    with pytest.raises(ValueError, match="proposal not found"):
        apply_proposal(
            proposal,
            bundle_root=bundle,
            staging_dir=staging,
            actor="human-1",
            at="2026-09-05T00:00:00Z",
        )


def test_ast_purity_and_no_wall_clock() -> None:
    import llamaindex_runtime.okf.writeback.apply as apply_module

    source = Path(apply_module.__file__).read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "uuid1" not in source
