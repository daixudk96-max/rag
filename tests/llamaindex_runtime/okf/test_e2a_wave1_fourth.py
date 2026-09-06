"""Wave-1 fourth-remediation regression tests (all filesystem tests are fakes)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from llamaindex_runtime.okf import _rooted_posix as posix
from llamaindex_runtime.okf import _rooted_windows as windows
from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aEvidenceObject,
    E2aEvidenceReference,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import read_raw_pair
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanSidecar

_GLOBAL_SCOPE = "00000000-0000-0000-0000-000000000000"
_DIGEST = "a" * 64


def _write_valid_raw_pair(root: Path) -> tuple[tuple[str, ...], int, int, int]:
    """Write one fully valid raw pair without mocking raw-pair admission."""
    raw = root / "raw"
    raw.mkdir()
    document_id, version_id = str(uuid4()), str(uuid4())
    frontmatter = {
        "type": "raw",
        "doc_id": document_id,
        "version_id": version_id,
        "source_checksum": _DIGEST,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "body").encode("utf-8")
    sidecar = SpanSidecar(1, document_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    markdown_path = raw / "source.md"
    markdown_path.write_bytes(markdown)
    markdown_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    markdown_path.with_suffix(".pair.json").write_bytes(manifest)
    return ("raw", "source.md"), len(manifest), len(markdown), len(sidecar_bytes)


def test_real_bundle_authority_admits_raw_pair_and_charges_each_mdsm_read(
    tmp_path: Path,
) -> None:
    parts, manifest_size, markdown_size, sidecar_size = _write_valid_raw_pair(tmp_path)

    with BundleAuthority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)
        budgeted = e2a_admission._BudgetedAuthority(authority)  # noqa: SLF001
        snapshot = read_raw_pair(budgeted, parts)

    assert snapshot.body == "body"
    assert len(state.parents) == 1
    assert budgeted._ledger.used == {  # noqa: SLF001
        "manifest": manifest_size * 2,
        "markdown": markdown_size,
        "sidecar": sidecar_size,
        "manual": 0,
    }


def test_real_bundle_authority_blocks_mdsm_before_an_under_cap_retry_read(
    tmp_path: Path,
) -> None:
    parts, _, _, _ = _write_valid_raw_pair(tmp_path)

    with BundleAuthority(tmp_path) as authority:
        budgeted = e2a_admission._BudgetedAuthority(authority)  # noqa: SLF001
        budgeted._ledger = e2a_admission._ReadLedger(  # noqa: SLF001
            {
                "manifest": (16 * 1024) - 1,
                "markdown": 64 * 1024 * 1024,
                "sidecar": 64 * 1024 * 1024,
                "manual": 1,
            },
            {"manifest": 0, "markdown": 0, "sidecar": 0, "manual": 0},
        )
        with pytest.raises(ValueError, match="^pair_manifest_invalid$"):
            read_raw_pair(budgeted, parts)

    assert budgeted._ledger.used == {  # noqa: SLF001
        "manifest": 0,
        "markdown": 0,
        "sidecar": 0,
        "manual": 0,
    }


def _entity_fact(
    *,
    path: str = "entities/cat.md",
    digest: str = _DIGEST,
    qualifiers: dict[str, object] | None = None,
) -> E2aManualFact:
    natural_key = canonical_json({"entity_type": "animal", "title": "cat"})
    return E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        path,
        digest,
        qualifiers or {},
        natural_key,
    )


def _parent_and_span(
    *, document_id: str | None = None, version_id: str | None = None
) -> tuple[E2aParent, E2aSpan]:
    parent_document_id = document_id or str(uuid4())
    parent_version_id = version_id or str(uuid4())
    return (
        E2aParent(
            parent_document_id, parent_version_id, "raw/source.pair.json", _DIGEST
        ),
        E2aSpan(parent_document_id, parent_version_id, str(uuid4()), 0, "body"),
    )


def _state_values(
    *,
    parent: E2aParent,
    span: E2aSpan,
    facts: tuple[E2aManualFact, ...],
    ownership: tuple[E2aOwnershipFact, ...],
    objects: tuple[E2aEvidenceObject, ...],
    links: tuple[E2aEvidenceReference, ...],
) -> dict[str, object]:
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            },
            *[
                {
                    "kind": owner.fact_kind,
                    "path": owner.relative_path,
                    "identity": owner.fact_id,
                    "source_digest": owner.source_digest,
                }
                for owner in ownership
            ],
        ]
    }
    return {
        "corpus_manifest": manifest,
        "corpus_manifest_sha256": canonical_json_sha256(manifest),
        "parents": (parent,),
        "canonical_spans": (span,),
        "vector_chunks": (),
        "vector_chunk_span_links": (),
        "tree_nodes": (),
        "tree_node_span_links": (),
        "manual_entities": facts,
        "manual_relations": (),
        "manual_concepts": (),
        "evidence_objects": objects,
        "evidence_links": links,
        "ownership_facts": ownership,
        "sync_state_rows": (),
        "validation_metadata": {},
        "provenance_metadata": {},
    }


def test_manual_and_ownership_identifiers_are_bound_to_natural_keys() -> None:
    fact = _entity_fact()
    ownership = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )

    with pytest.raises(ValueError, match="manual fact identity"):
        E2aManualFact(
            str(uuid4()),
            fact.fact_kind,
            fact.relative_path,
            fact.source_digest,
            fact.qualifiers,
            fact.natural_key,
        )
    with pytest.raises(ValueError, match="ownership identity"):
        E2aOwnershipFact(
            str(uuid4()),
            ownership.relative_path,
            ownership.fact_kind,
            ownership.fact_id,
            ownership.source_digest,
            ownership.document_id,
            ownership.version_id,
        )
    with pytest.raises(ValueError, match="ownership fact kind"):
        E2aOwnershipFact.create(
            relative_path="concepts/cat.md",
            fact_kind="concept",
            fact_id=deterministic_id("concept", "cat"),
            source_digest=_DIGEST,
        )


def test_desired_state_rejects_orphan_or_mismatched_ownership_and_evidence() -> None:
    fact = _entity_fact()
    parent, span = _parent_and_span()
    ownership = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    evidence = E2aEvidenceObject.create(
        version_id=parent.version_id,
        entity_id=fact.fact_id,
        relation_id=None,
    )
    link = E2aEvidenceReference(
        document_id=parent.document_id,
        version_id=parent.version_id,
        span_id=span.span_id,
        entity_id=fact.fact_id,
        relation_id=None,
        evidence_id=evidence.evidence_id,
        ownership_id=ownership.ownership_id,
        ownership_scope_version_id=_GLOBAL_SCOPE,
    )
    values = _state_values(
        parent=parent,
        span=span,
        facts=(fact,),
        ownership=(ownership,),
        objects=(evidence,),
        links=(link,),
    )

    assert E2aDesiredState(**values).evidence_links == (link,)
    with pytest.raises(ValueError, match="admitted ownership"):
        E2aDesiredState(**{**values, "ownership_facts": ()})
    with pytest.raises(ValueError, match="admitted evidence object"):
        E2aDesiredState(**{**values, "evidence_objects": ()})
    mismatched_owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest="b" * 64,
    )
    with pytest.raises(ValueError, match="ownership does not match"):
        E2aDesiredState(
            **{
                **values,
                "ownership_facts": (mismatched_owner,),
                "evidence_links": (
                    E2aEvidenceReference(
                        parent.document_id,
                        parent.version_id,
                        span.span_id,
                        fact.fact_id,
                        None,
                        evidence.evidence_id,
                        mismatched_owner.ownership_id,
                        _GLOBAL_SCOPE,
                    ),
                ),
            }
        )


def test_desired_state_supports_multi_owner_evidence_and_cross_version_groups() -> None:
    fact = _entity_fact(path="entities/cat-one.md")
    first_parent, first_span = _parent_and_span()
    second_parent, second_span = _parent_and_span(document_id=first_parent.document_id)
    first_owner = E2aOwnershipFact.create(
        relative_path="entities/cat-one.md",
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    second_owner = E2aOwnershipFact.create(
        relative_path="entities/cat-two.md",
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    first_evidence = E2aEvidenceObject.create(
        version_id=first_parent.version_id,
        entity_id=fact.fact_id,
        relation_id=None,
    )
    second_evidence = E2aEvidenceObject.create(
        version_id=second_parent.version_id,
        entity_id=fact.fact_id,
        relation_id=None,
    )
    links = (
        E2aEvidenceReference(
            first_parent.document_id,
            first_parent.version_id,
            first_span.span_id,
            fact.fact_id,
            None,
            first_evidence.evidence_id,
            first_owner.ownership_id,
            _GLOBAL_SCOPE,
        ),
        E2aEvidenceReference(
            first_parent.document_id,
            first_parent.version_id,
            first_span.span_id,
            fact.fact_id,
            None,
            first_evidence.evidence_id,
            second_owner.ownership_id,
            _GLOBAL_SCOPE,
        ),
        E2aEvidenceReference(
            second_parent.document_id,
            second_parent.version_id,
            second_span.span_id,
            fact.fact_id,
            None,
            second_evidence.evidence_id,
            first_owner.ownership_id,
            _GLOBAL_SCOPE,
        ),
    )
    values = _state_values(
        parent=first_parent,
        span=first_span,
        facts=(fact,),
        ownership=(first_owner, second_owner),
        objects=(first_evidence, second_evidence),
        links=links,
    )
    values["parents"] = (first_parent, second_parent)
    values["canonical_spans"] = (first_span, second_span)
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
            for parent in (first_parent, second_parent)
        ]
        + values["corpus_manifest"]["artifacts"][1:]
    }
    values["corpus_manifest"] = manifest
    values["corpus_manifest_sha256"] = canonical_json_sha256(manifest)

    state = E2aDesiredState(**values)

    assert len(state.evidence_links) == 3
    assert {link.evidence_id for link in state.evidence_links} == {
        first_evidence.evidence_id,
        second_evidence.evidence_id,
    }
    with pytest.raises(ValueError, match="duplicate evidence link"):
        E2aDesiredState(**{**values, "evidence_links": (*links, links[0])})


def test_conflicting_same_deterministic_fact_is_rejected_but_compatible_state_is_canonicalized() -> (
    None
):
    first = _entity_fact(path="entities/cat-one.md")
    compatible = _entity_fact(path="entities/cat-two.md", digest="b" * 64)
    conflicting = _entity_fact(
        path="entities/cat-conflict.md", qualifiers={"confidence": 0.5}
    )
    parent, span = _parent_and_span()
    first_owner = E2aOwnershipFact.create(
        relative_path=first.relative_path,
        fact_kind="entity",
        fact_id=first.fact_id,
        source_digest=first.source_digest,
    )
    compatible_owner = E2aOwnershipFact.create(
        relative_path=compatible.relative_path,
        fact_kind="entity",
        fact_id=compatible.fact_id,
        source_digest=compatible.source_digest,
    )
    admitted = (
        (
            first,
            first_owner,
            (),
            {
                "kind": "entity",
                "path": first.relative_path,
                "identity": first.fact_id,
                "source_digest": first.source_digest,
            },
        ),
        (
            compatible,
            compatible_owner,
            (),
            {
                "kind": "entity",
                "path": compatible.relative_path,
                "identity": compatible.fact_id,
                "source_digest": compatible.source_digest,
            },
        ),
    )

    raw_artifact = {
        "kind": "raw_pair",
        "path": parent.relative_path,
        "identity": f"{parent.document_id}:{parent.version_id}",
        "canonical_hash": parent.canonical_hash,
    }
    state = e2a_admission._desired_state(((parent, (span,), raw_artifact),), admitted)

    assert state.manual_entities == (first,)
    assert state.ownership_facts == (first_owner, compatible_owner)
    with pytest.raises(ValueError, match="^e2a_admission_natural_key_collision$"):
        e2a_admission._desired_state(
            ((parent, (span,), raw_artifact),),
            (
                (first, first_owner, (), {}),
                (conflicting, compatible_owner, (), {}),
            ),
        )


def test_desired_state_rejects_ownership_path_and_scoped_link_mismatches() -> None:
    fact = _entity_fact()
    parent, span = _parent_and_span()
    evidence = E2aEvidenceObject.create(
        version_id=parent.version_id,
        entity_id=fact.fact_id,
        relation_id=None,
    )
    original_owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    path_owner = E2aOwnershipFact.create(
        relative_path="entities/other.md",
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    path_link = E2aEvidenceReference(
        parent.document_id,
        parent.version_id,
        span.span_id,
        fact.fact_id,
        None,
        evidence.evidence_id,
        path_owner.ownership_id,
        _GLOBAL_SCOPE,
    )
    values = _state_values(
        parent=parent,
        span=span,
        facts=(fact,),
        ownership=(original_owner,),
        objects=(evidence,),
        links=(path_link,),
    )
    with pytest.raises(ValueError, match="ownership does not match"):
        E2aDesiredState(**{**values, "ownership_facts": (path_owner,)})

    scoped_owner = E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
        document_id=parent.document_id,
        version_id=parent.version_id,
    )
    scoped_link = E2aEvidenceReference(
        parent.document_id,
        parent.version_id,
        span.span_id,
        fact.fact_id,
        None,
        evidence.evidence_id,
        scoped_owner.ownership_id,
        _GLOBAL_SCOPE,
    )
    scoped_values = _state_values(
        parent=parent,
        span=span,
        facts=(fact,),
        ownership=(scoped_owner,),
        objects=(evidence,),
        links=(scoped_link,),
    )
    with pytest.raises(ValueError, match="scope does not match"):
        E2aDesiredState(**scoped_values)


class _FdClosingScan:
    def __init__(self, owner: "_FdOwningPosixOS", descriptor: int) -> None:
        self._owner = owner
        self._descriptor = descriptor
        self._entries = iter(owner.directories[descriptor])

    def __enter__(self) -> "_FdClosingScan":
        self._owner.scans_open += 1
        self._owner.maximum_scans_open = max(
            self._owner.maximum_scans_open, self._owner.scans_open
        )
        return self

    def __exit__(self, *_: object) -> None:
        self._owner.scans_open -= 1
        self._owner.close(self._descriptor)

    def __iter__(self) -> "_FdClosingScan":
        return self

    def __next__(self) -> SimpleNamespace:
        return SimpleNamespace(name=next(self._entries))


class _FdOwningPosixOS:
    """Protocol fake: scandir owns and closes only its duplicated descriptor."""

    O_RDONLY = 1
    O_DIRECTORY = 2
    O_NOFOLLOW = 4
    O_CLOEXEC = 8
    O_NONBLOCK = 16

    def __init__(self, *, fail_close: int | None = None) -> None:
        self.fail_close = fail_close
        self.next_fd = 2
        self.closed: list[int] = []
        self.close_attempts: list[int] = []
        self.live = {1}
        self.scans_open = 0
        self.maximum_scans_open = 0
        self.directories: dict[int, tuple[str, ...]] = {}
        self.modes: dict[int, int] = {1: 0o040000}
        self.children: dict[tuple[int, str], int] = {}

    def _allocate(self, source: int) -> int:
        descriptor = self.next_fd
        self.next_fd += 1
        self.live.add(descriptor)
        self.modes[descriptor] = self.modes[source]
        if source in self.directories:
            self.directories[descriptor] = self.directories[source]
        return descriptor

    def dup(self, descriptor: int) -> int:
        return self._allocate(descriptor)

    def scandir(self, descriptor: int) -> _FdClosingScan:
        if descriptor not in self.directories:
            raise OSError
        return _FdClosingScan(self, descriptor)

    def open(self, name: str, _flags: int, *, dir_fd: int) -> int:
        source = self.children[(dir_fd, name)]
        return self._allocate(source)

    def fstat(self, descriptor: int) -> SimpleNamespace:
        return SimpleNamespace(st_mode=self.modes[descriptor])

    def close(self, descriptor: int) -> None:
        self.close_attempts.append(descriptor)
        if descriptor not in self.live:
            raise OSError("double close")
        self.live.remove(descriptor)
        if descriptor == self.fail_close:
            raise OSError("close failure")
        self.closed.append(descriptor)


def _fd_owning_posix_tree(*, fail_close: int | None = None) -> _FdOwningPosixOS:
    fake = _FdOwningPosixOS(fail_close=fail_close)
    # The first walker duplicate is fd 2; its scan duplicate is fd 3.
    fake.directories[1] = ("nested", "top.md")
    fake.children[(2, "nested")] = 1
    fake.children[(2, "top.md")] = 1
    fake.modes[1] = 0o040000
    return fake


def test_posix_fake_scandir_owns_only_duplicated_fds_during_nested_dfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fd_owning_posix_tree()

    def allocate_open(name: str, _flags: int, *, dir_fd: int) -> int:
        if name == "nested":
            descriptor = fake._allocate(1)
            fake.directories[descriptor] = ("deep.md",)
            fake.children[(descriptor, "deep.md")] = 1
            return descriptor
        descriptor = fake._allocate(1)
        fake.modes[descriptor] = 0o100000
        return descriptor

    monkeypatch.setattr(fake, "open", allocate_open)
    monkeypatch.setattr(posix, "os", fake)
    monkeypatch.setattr(
        posix,
        "stat",
        SimpleNamespace(
            S_ISDIR=lambda mode: mode == 0o040000,
            S_ISREG=lambda mode: mode == 0o100000,
        ),
    )

    values = posix.PosixBundleBackend(1).enumerate_regular_files(
        maximum_files=2, maximum_entries=3, maximum_depth=2
    )

    assert values == (("nested", "deep.md"), ("top.md",))
    assert fake.maximum_scans_open == 2
    assert fake.live == {1}
    assert len(fake.close_attempts) == len(set(fake.close_attempts))


def test_posix_fake_scandir_close_failure_closes_walker_chain_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fd_owning_posix_tree(fail_close=3)
    monkeypatch.setattr(posix, "os", fake)
    monkeypatch.setattr(
        posix,
        "stat",
        SimpleNamespace(S_ISDIR=lambda _: True, S_ISREG=lambda _: True),
    )

    with pytest.raises(ValueError, match="^bundle enumeration cannot be read$"):
        posix.PosixBundleBackend(1).enumerate_regular_files(
            maximum_files=2, maximum_entries=3, maximum_depth=2
        )

    assert fake.close_attempts.count(2) == 1
    assert fake.close_attempts.count(3) == 1


class _MetadataFailureKernel:
    def __init__(self, *, close_result: bool = True) -> None:
        self.close_result = close_result
        self.closed: list[int] = []

    def GetFileInformationByHandle(self, _handle: int, _info: object) -> bool:
        return False

    def GetFileType(self, _handle: int) -> int:
        return windows.FILE_TYPE_DISK

    def CloseHandle(self, handle: int) -> bool:
        self.closed.append(handle)
        return self.close_result


def _failing_child_create(handle: object, *_: object) -> int:
    handle._obj.value = 42  # type: ignore[attr-defined]
    return 0


@pytest.mark.parametrize("directory", (False, True))
def test_windows_fake_metadata_failure_rejects_leaf_and_directory(
    monkeypatch: pytest.MonkeyPatch, directory: bool
) -> None:
    kernel = _MetadataFailureKernel()
    api = windows._WindowsApi(
        kernel, SimpleNamespace(NtCreateFile=_failing_child_create)
    )

    with pytest.raises(OSError):
        windows._open_child(api, 17, "child", directory=directory)

    assert kernel.closed == [42]


def test_windows_fake_metadata_failure_surfaces_transient_close_failure() -> None:
    kernel = _MetadataFailureKernel(close_result=False)
    api = windows._WindowsApi(
        kernel, SimpleNamespace(NtCreateFile=_failing_child_create)
    )

    with pytest.raises(OSError):
        windows._open_child(api, 17, "leaf", directory=False)

    assert kernel.closed == [42]


@pytest.mark.parametrize("root", ("false", "0", "[]", "''", "- item"))
def test_e2a_yaml_rejects_every_non_mapping_root(root: str) -> None:
    from llamaindex_runtime.okf.e2a_frontmatter import load_strict_e2a_frontmatter

    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        load_strict_e2a_frontmatter(f"---\n{root}\n---\nbody")


def test_e2a_yaml_only_converts_an_empty_document_to_an_empty_mapping() -> None:
    from llamaindex_runtime.okf.e2a_frontmatter import load_strict_e2a_frontmatter

    parsed, body = load_strict_e2a_frontmatter("---\n\n---\nbody")

    assert parsed == {}
    assert body == "body"


def test_expected_ids_are_canonical_uuid_values() -> None:
    """Guard fixtures from silently testing malformed IDs rather than graph checks."""
    assert UUID(_GLOBAL_SCOPE).int == 0
