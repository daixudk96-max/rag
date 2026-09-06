"""Phase-15 Wave-1 seventh-remediation application regression coverage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.rooted_open import BundleAuthority

_RAW_FILES = (
    ("raw", "source.md"),
    ("raw", "source.pair.json"),
    ("raw", "source.spans.json"),
)
_ENUMERATION_LIMITS = {
    "maximum_files": e2a_admission.MAX_E2A_CANDIDATES,
    "maximum_entries": e2a_admission.MAX_E2A_DIRECTORY_ENTRIES,
    "maximum_depth": e2a_admission.MAX_E2A_DEPTH,
}


def _write_relation(
    path: Path,
    *,
    subject_entity_id: str,
    object_entity_id: str,
    qualifiers: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: relation\n"
        f"subject_entity_id: {subject_entity_id}\n"
        "predicate: protects\n"
        f"object_entity_id: {object_entity_id}\n"
        "timestamp: '2026-07-18T00:00:00Z'\n"
        f"{qualifiers}"
        "---\n"
        "relation body\n",
        encoding="utf-8",
    )


def test_bundle_authority_rejects_nested_bool_int_relation_qualifier_collision(
    tmp_path: Path,
) -> None:
    subject_entity_id, object_entity_id = str(uuid4()), str(uuid4())
    _write_relation(
        tmp_path / "relations" / "bool.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers="qualifiers:\n  scope:\n    enabled: true\n",
    )
    _write_relation(
        tmp_path / "relations" / "int.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers="qualifiers:\n  scope:\n    enabled: 1\n",
    )

    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError, match="^e2a_admission_natural_key_collision$"):
            e2a_admission.admit_e2a_corpus(authority)


def test_bundle_authority_coalesces_key_order_compatible_duplicate_relations(
    tmp_path: Path,
) -> None:
    subject_entity_id, object_entity_id = str(uuid4()), str(uuid4())
    _write_relation(
        tmp_path / "relations" / "first.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers=(
            "qualifiers:\n"
            "  timeline:\n"
            "    start: today\n"
            "    end: tomorrow\n"
            "  reviewed: true\n"
        ),
    )
    _write_relation(
        tmp_path / "relations" / "second.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers=(
            "qualifiers:\n"
            "  reviewed: true\n"
            "  timeline:\n"
            "    end: tomorrow\n"
            "    start: today\n"
        ),
    )

    with BundleAuthority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)

    assert len(state.manual_relations) == 1
    assert {owner.relative_path for owner in state.ownership_facts} == {
        "relations/first.md",
        "relations/second.md",
    }
    assert {
        str(artifact["path"])
        for artifact in state.corpus_manifest["artifacts"]  # type: ignore[index]
        if artifact["kind"] == "relation"  # type: ignore[index]
    } == {"relations/first.md", "relations/second.md"}


def test_bundle_authority_rejects_compatible_duplicate_concept_natural_key_early(
    tmp_path: Path,
) -> None:
    for name, title in (("primary", "Cat"), ("copy", "cat")):
        concept = tmp_path / "concepts" / f"{name}.md"
        concept.parent.mkdir(parents=True, exist_ok=True)
        concept.write_text(
            "---\n"
            "type: concept\n"
            f"title: {title}\n"
            "timestamp: '2026-07-18T00:00:00Z'\n"
            "---\n"
            "concept body\n",
            encoding="utf-8",
        )

    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError, match="^e2a_admission_duplicate_concept_fact$"):
            e2a_admission.admit_e2a_corpus(authority)


class _EnumeratingAuthority:
    def __init__(self, snapshots: tuple[tuple[tuple[str, ...], ...], ...]) -> None:
        self._snapshots = snapshots
        self.calls: list[dict[str, int]] = []
        self.events: list[str] = []

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]:
        self.calls.append(
            {
                "maximum_files": maximum_files,
                "maximum_entries": maximum_entries,
                "maximum_depth": maximum_depth,
            }
        )
        self.events.append("enumerate")
        return self._snapshots[len(self.calls) - 1]


def _admitted_raw_pair(pair_path: tuple[str, ...], events: list[str]) -> tuple[
    e2a_admission.E2aParent,
    tuple[e2a_admission.E2aSpan, ...],
    dict[str, object],
]:
    events.append("admit")
    document_id, version_id = str(uuid4()), str(uuid4())
    parent = e2a_admission.E2aParent(
        document_id, version_id, "/".join(pair_path), "a" * 64
    )
    return (
        parent,
        (),
        {
            "kind": "raw_pair",
            "path": parent.relative_path,
            "identity": f"{document_id}:{version_id}",
            "canonical_hash": parent.canonical_hash,
        },
    )


def _stub_admit_pair(events: list[str]) -> Callable[..., object]:
    def admit_pair(_: object, pair_path: tuple[str, ...]) -> object:
        return _admitted_raw_pair(pair_path, events)

    return admit_pair


def test_admission_reenumerates_exact_membership_after_reads_before_state_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _EnumeratingAuthority((_RAW_FILES, _RAW_FILES))
    monkeypatch.setattr(
        e2a_admission, "_admit_pair", _stub_admit_pair(authority.events)
    )

    state = e2a_admission.admit_e2a_corpus(authority)  # type: ignore[arg-type]

    assert len(state.parents) == 1
    assert authority.calls == [_ENUMERATION_LIMITS, _ENUMERATION_LIMITS]
    assert authority.events == ["enumerate", "admit", "enumerate"]


@pytest.mark.parametrize(
    ("initial", "after_reads"),
    (
        (_RAW_FILES, (*_RAW_FILES, ("raw", "added.md"))),
        (_RAW_FILES, _RAW_FILES[:-1]),
        (
            (*_RAW_FILES, ("support", "old.md")),
            (*_RAW_FILES, ("support", "new.md")),
        ),
    ),
    ids=("added_member", "removed_member", "excluded_support_member_changed"),
)
def test_admission_rejects_membership_changes_after_reads(
    monkeypatch: pytest.MonkeyPatch,
    initial: tuple[tuple[str, ...], ...],
    after_reads: tuple[tuple[str, ...], ...],
) -> None:
    authority = _EnumeratingAuthority((initial, after_reads))
    monkeypatch.setattr(
        e2a_admission, "_admit_pair", _stub_admit_pair(authority.events)
    )

    with pytest.raises(ValueError, match="^e2a_admission_corpus_unstable$"):
        e2a_admission.admit_e2a_corpus(authority)  # type: ignore[arg-type]

    assert authority.calls == [_ENUMERATION_LIMITS, _ENUMERATION_LIMITS]
    assert authority.events == ["enumerate", "admit", "enumerate"]
