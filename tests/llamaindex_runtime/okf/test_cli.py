"""Canonical tests for the okf-writeback CLI (Phase 18 wave-3)."""

import ast
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from llamaindex_runtime.okf.writeback import journal as J
from llamaindex_runtime.okf.writeback import proposal as P
from llamaindex_runtime.okf.writeback import cli as C
from llamaindex_runtime.okf.writeback.cli import run_command

GOLDEN_PROPOSAL_ID = "32e71258-0224-5d5e-8626-98d3e1b62578"


def _golden_proposal(evidence=None) -> P.WritebackProposal:
    return P.WritebackProposal(
        target_file="entities/org/huawei.md",
        patch="REPLACE-BODY",
        reason="evidence-backed add",
        evidence=(
            evidence
            if evidence is not None
            else ["source: https://example.com/evidence/trace"]
        ),
        proposed_by="agent-1",
        created_at="2026-09-03T00:00:00Z",
    )


def _make_context(tmp_path: Path, *, evidence=None):
    staging = tmp_path / ".staging"
    proposal = _golden_proposal(evidence=evidence)
    proposal_file = P.write_proposal(staging, proposal)
    digest = hashlib.sha256(proposal_file.read_bytes()).hexdigest()
    journal = staging / "journal.jsonl"
    J.record_creation(
        journal,
        proposal.proposal_id,
        actor="agent-1",
        at="2026-09-03T00:00:01Z",
        payload_digest=digest,
    )
    return staging, journal, proposal, proposal_file


def _run(argv, staging, journal):
    out = io.StringIO()
    err = io.StringIO()
    rc = run_command(argv, staging_dir=staging, journal_path=journal, out=out, err=err)
    return rc, out.getvalue(), err.getvalue()


def _run_exit(argv, staging, journal):
    out = io.StringIO()
    err = io.StringIO()
    rc = run_command(argv, staging_dir=staging, journal_path=journal, out=out, err=err)
    raise AssertionError(f"expected SystemExit, got rc={rc}")


def _approve(staging, journal, proposal_id, actor="human-1"):
    return _run(["approve", proposal_id, "--actor", actor], staging, journal)


def _snapshot_tree(root: Path):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ---- module-level guards ----


def test_exit_code_table_in_docstring():
    src = Path(C.__file__).read_text(encoding="utf-8")
    assert "Exit codes (pinned)" in src
    assert "0: success" in src
    assert "1: proposal not found" in src
    assert "2: illegal transition or invalid argument/reason" in src
    assert "3: payload digest changed (tamper suspected)" in src


def test_cli_module_pure_stdlib_imports():
    allowed = {
        "__future__",
        "argparse",
        "collections",
        "dataclasses",
        "datetime",
        "hashlib",
        "io",
        "json",
        "os",
        "pathlib",
        "sys",
        "typing",
        "uuid",
    }
    tree = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            assert node.module.split(".")[0] in allowed, node.module


def test_cli_datetime_now_used_only_in_adapter():
    src = Path(C.__file__).read_text(encoding="utf-8")
    assert src.count("datetime.now(timezone.utc)") <= 1


# ---- list ----


def test_run_list_empty(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    rc, out, err = _run(["list"], staging, staging / "journal.jsonl")
    assert rc == 0
    assert out == "no proposals\n"
    assert err == ""


def test_run_list_no_proposals_when_only_journal(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    journal = staging / "journal.jsonl"
    J.record_creation(
        journal,
        GOLDEN_PROPOSAL_ID,
        actor="agent-1",
        at="2026-09-03T00:00:01Z",
        payload_digest="a" * 64,
    )
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert out == "no proposals\n"
    assert err == ""


def test_run_list_happy_path_created(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    assert proposal.proposal_id == GOLDEN_PROPOSAL_ID
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert out == f"created  {GOLDEN_PROPOSAL_ID}  entities/org/huawei.md\n"
    assert err == ""


def test_run_list_journal_missing_means_created(tmp_path):
    staging = tmp_path / ".staging"
    proposal = _golden_proposal()
    P.write_proposal(staging, proposal)
    missing = staging / "does-not-exist.jsonl"
    rc, out, err = _run(["list"], staging, missing)
    assert rc == 0
    assert out == f"created  {GOLDEN_PROPOSAL_ID}  entities/org/huawei.md\n"
    assert err == ""


def test_run_list_derived_approved_status(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc1, _, err1 = _approve(staging, journal, proposal.proposal_id)
    assert rc1 == 0 and err1 == ""
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert out == f"approved  {GOLDEN_PROPOSAL_ID}  entities/org/huawei.md\n"
    assert err == ""


def test_run_list_unverified_marker(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path, evidence=[])
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert (
        out == f"created  {GOLDEN_PROPOSAL_ID}  entities/org/huawei.md  [unverified]\n"
    )
    assert err == ""


def test_run_list_verified_no_marker(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert "[unverified]" not in out
    assert err == ""


def test_run_list_sorted_by_proposal_id(tmp_path):
    staging = tmp_path / ".staging"
    p1 = P.WritebackProposal(
        target_file="entities/alpha.md",
        patch="P1",
        reason="r",
        evidence=["e1"],
        proposed_by="agent-1",
        created_at="2026-09-03T00:00:00Z",
    )
    p2 = P.WritebackProposal(
        target_file="entities/beta.md",
        patch="P2",
        reason="r",
        evidence=["e2"],
        proposed_by="agent-2",
        created_at="2026-09-04T00:00:00Z",
    )
    P.write_proposal(staging, p1)
    # p2's payload is stored under a deliberately non-id filename whose lexicographic
    # order differs from p2's proposal_id, proving rows sort by id, not filename.
    (staging / "aaa.json").write_text(
        json.dumps(p2.to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rc, out, err = _run(["list"], staging, staging / "journal.jsonl")
    assert rc == 0 and err == ""
    rows = out.splitlines()
    ids = [line.split("  ")[1] for line in rows]
    assert ids == sorted([p1.proposal_id, p2.proposal_id])
    assert rows == [
        f"created  {id_}  {target}"
        for id_, target in sorted(
            [(p1.proposal_id, p1.target_file), (p2.proposal_id, p2.target_file)]
        )
    ]


def test_run_list_malformed_tolerated(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    (staging / "not-a-uuid.json").write_text('{"broken": true', encoding="utf-8")
    rc, out, err = _run(["list"], staging, journal)
    assert rc == 0
    assert (
        out
        == f"MALFORMED not-a-uuid\ncreated  {GOLDEN_PROPOSAL_ID}  entities/org/huawei.md\n"
    )
    assert err == ""


def test_run_list_only_malformed_no_crash(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    (staging / "bad.json").write_text("not json at all", encoding="utf-8")
    rc, out, err = _run(["list"], staging, staging / "journal.jsonl")
    assert rc == 0
    assert out == "MALFORMED bad\n"
    assert err == ""


# ---- show ----


def test_run_show_full_json_contains_evidence(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(["show", proposal.proposal_id], staging, journal)
    assert rc == 0
    expected = json.dumps(proposal.to_dict(), sort_keys=True, indent=2) + "\n"
    assert out == expected + "status: created\n"
    assert "evidence-backed add" in out
    assert "https://example.com/evidence/trace" in out
    assert err == ""


def test_run_show_status_line(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(["show", proposal.proposal_id], staging, journal)
    assert rc == 0
    assert out.splitlines()[-1] == "status: created"
    assert err == ""


def test_run_show_approved_status_line(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    rc, out, err = _run(["show", proposal.proposal_id], staging, journal)
    assert rc == 0
    assert out.splitlines()[-1] == "status: approved"
    assert err == ""


def test_run_show_not_found(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    missing = "00000000-0000-4000-8000-000000000000"
    rc, out, err = _run(["show", missing], staging, journal)
    assert rc == 1
    assert out == ""
    assert err == "proposal not found\n"


# ---- approve ----


def test_run_approve_happy_path(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _approve(staging, journal, proposal.proposal_id)
    assert rc == 0
    assert out == f"approved: {GOLDEN_PROPOSAL_ID}\n"
    assert err == ""


def test_run_approve_writes_journal_event(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    events = J.read_events(journal)
    assert len(events) == 2
    assert events[-1].event_type == "approved"
    assert events[-1].proposal_id == GOLDEN_PROPOSAL_ID
    assert events[-1].actor == "human-1"
    assert len(events[-1].payload_digest) == 64


def test_run_approve_derived_approved(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    assert J.derive_status(J.read_events(journal)) == "approved"


def test_run_approve_explicit_at(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(
        [
            "approve",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--at",
            "2026-09-05T10:00:00Z",
        ],
        staging,
        journal,
    )
    assert rc == 0
    events = J.read_events(journal)
    assert events[-1].at == "2026-09-05T10:00:00Z"


def test_run_approve_default_at_utc_iso(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _approve(staging, journal, proposal.proposal_id)
    assert rc == 0
    at = J.read_events(journal)[-1].at
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", at)


def test_run_approve_not_found(tmp_path):
    staging, journal, proposal, proposal_file = _make_context(tmp_path)
    proposal_file.unlink()
    rc, out, err = _approve(staging, journal, proposal.proposal_id)
    assert rc == 1
    assert out == ""
    assert err == f"proposal not found: {GOLDEN_PROPOSAL_ID}\n"


def test_run_approve_missing_actor_system_exit(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _run_exit(["approve", proposal.proposal_id], staging, journal)
    assert excinfo.value.code == 2


def test_run_approve_illegal_transition(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc1, _, _ = _approve(staging, journal, proposal.proposal_id)
    assert rc1 == 0
    # Distinct explicit --at avoids a same-second event_id collision so the
    # second approve reaches the transition check (approved->approved).
    rc, out, err = _run(
        [
            "approve",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--at",
            "2026-09-05T10:00:01Z",
        ],
        staging,
        journal,
    )
    assert rc == 2
    assert out == ""
    assert err == "error: illegal transition: approved->approved\n"


def test_run_approve_tamper(tmp_path):
    staging, journal, proposal, proposal_file = _make_context(tmp_path)
    proposal_file.write_bytes(proposal_file.read_bytes() + b" ")
    rc, out, err = _approve(staging, journal, proposal.proposal_id)
    assert rc == 3
    assert out == ""
    assert "tamper suspected" in err
    assert "payload digest changed" in err


def test_run_approve_out_err_separation(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _approve(staging, journal, proposal.proposal_id)
    assert rc == 0
    assert out.startswith("approved: ")
    assert err == ""


# ---- reject ----


@pytest.mark.parametrize("code", J.REJECTED_REASONS)
def test_run_reject_valid_code(tmp_path, code):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(
        ["reject", proposal.proposal_id, "--actor", "human-1", "--reason", code],
        staging,
        journal,
    )
    assert rc == 0
    assert out == f"rejected: {GOLDEN_PROPOSAL_ID} ({code})\n"
    assert err == ""
    events = J.read_events(journal)
    assert events[-1].event_type == "rejected"
    assert events[-1].rejected_reason == code


def test_run_reject_invalid_reason(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(
        [
            "reject",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "bogus-code",
        ],
        staging,
        journal,
    )
    assert rc == 2
    assert out == ""
    assert err == "invalid --reason bogus-code\n"


def test_run_reject_not_found(tmp_path):
    staging, journal, proposal, proposal_file = _make_context(tmp_path)
    proposal_file.unlink()
    rc, out, err = _run(
        [
            "reject",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "low-confidence",
        ],
        staging,
        journal,
    )
    assert rc == 1
    assert out == ""
    assert err == f"proposal not found: {GOLDEN_PROPOSAL_ID}\n"


def test_run_reject_illegal_transition_after_rejected(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc1, _, _ = _run(
        [
            "reject",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "low-confidence",
            "--at",
            "2026-09-05T10:00:00Z",
        ],
        staging,
        journal,
    )
    assert rc1 == 0
    rc, out, err = _run(
        [
            "reject",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
            "--at",
            "2026-09-05T10:00:01Z",
        ],
        staging,
        journal,
    )
    assert rc == 2
    assert out == ""
    assert err == "error: illegal transition: rejected->rejected\n"


def test_run_reject_persists_event(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    _run(
        [
            "reject",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "schema-violating",
        ],
        staging,
        journal,
    )
    events = J.read_events(journal)
    assert len(events) == 2
    assert events[-1].event_type == "rejected"
    assert events[-1].rejected_reason == "schema-violating"


# ---- discard ----


def test_run_discard_happy_path(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc1, _, _ = _approve(staging, journal, proposal.proposal_id)
    assert rc1 == 0
    rc, out, err = _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
        ],
        staging,
        journal,
    )
    assert rc == 0
    assert out == f"discarded: {GOLDEN_PROPOSAL_ID}\n"
    assert err == ""
    assert J.derive_status(J.read_events(journal)) == "discarded"


def test_run_discard_from_created_illegal(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
        ],
        staging,
        journal,
    )
    assert rc == 2
    assert out == ""
    assert err == "error: illegal transition: created->discarded\n"


def test_run_discard_invalid_reason(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    rc, out, err = _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "bogus-code",
        ],
        staging,
        journal,
    )
    assert rc == 2
    assert out == ""
    assert err == "invalid --reason bogus-code\n"


def test_run_discard_not_found(tmp_path):
    staging, journal, proposal, proposal_file = _make_context(tmp_path)
    proposal_file.unlink()
    rc, out, err = _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "low-confidence",
        ],
        staging,
        journal,
    )
    assert rc == 1
    assert out == ""
    assert err == f"proposal not found: {GOLDEN_PROPOSAL_ID}\n"


def test_run_discard_persists_reason(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "manual-review-requested",
        ],
        staging,
        journal,
    )
    events = J.read_events(journal)
    assert events[-1].event_type == "discarded"
    assert events[-1].rejected_reason == "manual-review-requested"


def test_run_discard_tamper(tmp_path):
    staging, journal, proposal, proposal_file = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    proposal_file.write_bytes(proposal_file.read_bytes() + b" ")
    rc, out, err = _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
        ],
        staging,
        journal,
    )
    assert rc == 3
    assert out == ""
    assert "tamper suspected" in err


# ---- argparse SystemExit(2) guards ----


def test_run_unknown_command_system_exit(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    with pytest.raises(SystemExit) as excinfo:
        _run_exit(["frobnicate"], staging, staging / "journal.jsonl")
    assert excinfo.value.code == 2


def test_run_missing_command_system_exit(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    with pytest.raises(SystemExit) as excinfo:
        _run_exit([], staging, staging / "journal.jsonl")
    assert excinfo.value.code == 2


def test_run_missing_proposal_id_system_exit(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir(parents=True)
    with pytest.raises(SystemExit) as excinfo:
        _run_exit(["show"], staging, staging / "journal.jsonl")
    assert excinfo.value.code == 2


def test_run_unknown_flag_system_exit(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _run_exit(
            ["approve", proposal.proposal_id, "--actor", "x", "--bogus"],
            staging,
            journal,
        )
    assert excinfo.value.code == 2


# ---- red lines: CLI never writes bundle body or extra files ----


def test_commands_never_write_bundle_body(tmp_path):
    bundle = tmp_path / "bundle"
    target = bundle / "entities/org/huawei.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Huawei org\nbody\n", encoding="utf-8")
    (bundle / "entities/org/other.md").write_text("other\n", encoding="utf-8")
    before = _snapshot_tree(bundle)

    staging, journal, proposal, _ = _make_context(tmp_path)
    _approve(staging, journal, proposal.proposal_id)
    _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
        ],
        staging,
        journal,
    )
    _run(["list"], staging, journal)
    _run(["show", proposal.proposal_id], staging, journal)

    after = _snapshot_tree(bundle)
    assert after == before


def test_staging_never_accumulates_extra_files(tmp_path):
    staging, journal, proposal, _ = _make_context(tmp_path)
    before = set(staging.iterdir())
    _approve(staging, journal, proposal.proposal_id)
    _run(
        [
            "discard",
            proposal.proposal_id,
            "--actor",
            "human-1",
            "--reason",
            "contradicted",
        ],
        staging,
        journal,
    )
    _run(["list"], staging, journal)
    _run(["show", proposal.proposal_id], staging, journal)
    after = set(staging.iterdir())
    assert after == before
    assert {path.name for path in after} == {
        GOLDEN_PROPOSAL_ID + ".json",
        "journal.jsonl",
    }
