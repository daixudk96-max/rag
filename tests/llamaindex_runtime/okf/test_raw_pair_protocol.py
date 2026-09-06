"""Contract tests for strict bounded M-D-S-M raw-pair admission."""

from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import RawPairSnapshot, read_raw_pair
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanSidecar


def _write_pair(
    root: Path, *, extra: dict[str, object] | None = None
) -> tuple[Path, bytes, bytes]:
    raw = root / "raw"
    raw.mkdir()
    doc_id, version_id = str(uuid4()), str(uuid4())
    frontmatter: dict[str, object] = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
        **(extra or {}),
    }
    markdown = dump_raw_frontmatter(frontmatter, "body").encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    path = raw / "source.md"
    path.write_bytes(markdown)
    path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=path.name,
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    path.with_suffix(".pair.json").write_bytes(manifest)
    return path, markdown, sidecar_bytes


def _read(root: Path) -> RawPairSnapshot:
    with BundleAuthority(root) as authority:
        return read_raw_pair(authority, ("raw", "source.md"))


def test_reader_api_has_no_callback_or_accepted_escape_hatch() -> None:
    assert tuple(inspect.signature(read_raw_pair).parameters) == (
        "authority",
        "markdown_parts",
    )
    assert "accepted" not in RawPairSnapshot.__dataclass_fields__


class _PathCanary:
    def __getattribute__(self, _: str) -> object:
        raise AssertionError("invalid path member hook must not run")


class _TupleSubclass(tuple[str, ...]):
    pass


class _StringSubclass(str):
    def __eq__(self, _: object) -> bool:
        raise AssertionError("invalid path string hook must not run")


class _NoReadAuthority:
    def __init__(self) -> None:
        self.manifest_reads = self.document_reads = self.sidecar_reads = 0

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.manifest_reads += 1
        raise AssertionError("invalid raw-pair path must not read a manifest")

    def read_document(self, _: tuple[str, ...]) -> bytes:
        self.document_reads += 1
        raise AssertionError("invalid raw-pair path must not read a document")

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.sidecar_reads += 1
        raise AssertionError("invalid raw-pair path must not read a sidecar")


class _RecordingAuthority:
    def __init__(self, authority: BundleAuthority) -> None:
        self._authority = authority
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def read_manifest(self, parts: tuple[str, ...]) -> bytes:
        self.calls.append(("manifest", parts))
        return self._authority.read_manifest(parts)

    def read_document(self, parts: tuple[str, ...]) -> bytes:
        self.calls.append(("document", parts))
        return self._authority.read_document(parts)

    def read_sidecar(self, parts: tuple[str, ...]) -> bytes:
        self.calls.append(("sidecar", parts))
        return self._authority.read_sidecar(parts)


@pytest.mark.parametrize(
    "parts",
    (
        (),
        ("raw",),
        ("other", "source.md"),
        ("raw", ""),
        ("raw", "."),
        ("raw", ".."),
        ("raw", "nested/path", "source.md"),
        ("raw", "nested\\path", "source.md"),
        ("raw", "source.txt"),
        ("raw", "invalid_slug.md"),
        ["raw", "source.md"],
        _TupleSubclass(("raw", "source.md")),
        ("raw", _StringSubclass("source.md")),
        ("raw", _PathCanary()),
    ),
    ids=(
        "empty",
        "missing-filename",
        "wrong-root",
        "empty-component",
        "dot-component",
        "dotdot-component",
        "slash-component",
        "backslash-component",
        "wrong-extension",
        "invalid-slug",
        "list",
        "tuple-subclass",
        "string-subclass",
        "path-canary",
    ),
)
def test_reader_rejects_invalid_public_path_before_any_authority_read(
    parts: object,
) -> None:
    authority = _NoReadAuthority()

    with pytest.raises(ValueError, match="^pair_manifest_invalid$") as raised:
        read_raw_pair(authority, parts)  # type: ignore[arg-type]

    assert raised.value.__cause__ is None
    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (0, 0, 0)


def test_reader_admits_safe_nested_raw_descendant_path(tmp_path: Path) -> None:
    nested = tmp_path / "raw" / "nested"
    nested.mkdir(parents=True)
    doc_id, version_id = str(uuid4()), str(uuid4())
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "body").encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ()).to_bytes()
    (nested / "source.md").write_bytes(markdown)
    (nested / "source.spans.json").write_bytes(sidecar)
    (nested / "source.pair.json").write_bytes(
        GenerationManifest.create(
            markdown_file="source.md",
            markdown_bytes=markdown,
            sidecar_file="source.spans.json",
            sidecar_bytes=sidecar,
            canonical_hash=canonical_hash(frontmatter, SpanSidecar.from_bytes(sidecar)),
        ).to_bytes()
    )

    with BundleAuthority(tmp_path) as opened_authority:
        authority = _RecordingAuthority(opened_authority)
        snapshot = read_raw_pair(authority, ("raw", "nested", "source.md"))  # type: ignore[arg-type]

    assert snapshot.body == "body"
    assert authority.calls == [
        ("manifest", ("raw", "nested", "source.pair.json")),
        ("document", ("raw", "nested", "source.md")),
        ("sidecar", ("raw", "nested", "source.spans.json")),
        ("manifest", ("raw", "nested", "source.pair.json")),
    ]


def test_mdsm_admits_immutable_complete_frontmatter_body_and_sidecar(
    tmp_path: Path,
) -> None:
    _, markdown, sidecar_bytes = _write_pair(tmp_path, extra={"future_field": "保留"})

    snapshot = _read(tmp_path)

    assert snapshot.markdown_bytes == markdown
    assert snapshot.sidecar_bytes == sidecar_bytes
    assert snapshot.frontmatter["future_field"] == "保留"
    assert snapshot.body == "body"
    assert snapshot.sidecar.spans == ()
    with pytest.raises(TypeError):
        snapshot.frontmatter["future_field"] = "changed"  # type: ignore[index]
    with pytest.raises(AttributeError):
        snapshot.body = "changed"  # type: ignore[misc]


def test_mdsm_deep_freezes_nested_frontmatter_without_aliasing_parser_values(
    tmp_path: Path,
) -> None:
    _write_pair(
        tmp_path,
        extra={"future_field": {"nested": ["preserved", {"value": "stable"}]}},
    )

    snapshot = _read(tmp_path)
    nested = snapshot.frontmatter["future_field"]

    with pytest.raises(TypeError):
        nested["nested"] = ()  # type: ignore[index]
    with pytest.raises(AttributeError):
        nested["nested"].append("changed")  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        nested["nested"][1]["value"] = "changed"  # type: ignore[index]

    parser_value = {"future_field": {"nested": ["changed"]}}
    assert snapshot.frontmatter["future_field"] == {
        "nested": ("preserved", {"value": "stable"})
    }
    assert parser_value["future_field"]["nested"] == ["changed"]


class _ChangingAuthority:
    def __init__(
        self,
        *,
        manifests: list[bytes],
        markdowns: list[bytes],
        sidecars: list[bytes],
    ) -> None:
        self._manifests = iter(manifests)
        self._markdowns = iter(markdowns)
        self._sidecars = iter(sidecars)
        self.manifest_reads = 0
        self.document_reads = 0
        self.sidecar_reads = 0

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.manifest_reads += 1
        return next(self._manifests)

    def read_document(self, _: tuple[str, ...]) -> bytes:
        self.document_reads += 1
        return next(self._markdowns)

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.sidecar_reads += 1
        return next(self._sidecars)


def test_mdsm_success_reads_each_payload_once_and_manifest_twice(
    tmp_path: Path,
) -> None:
    _, markdown, sidecar = _write_pair(tmp_path)
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash=canonical_hash(
            {
                "type": "raw",
                "doc_id": SpanSidecar.from_bytes(sidecar).doc_id,
                "version_id": SpanSidecar.from_bytes(sidecar).version_id,
                "source_checksum": "a" * 64,
                "docling_version": "test",
                "generated_by": "test",
            },
            SpanSidecar.from_bytes(sidecar),
        ),
    ).to_bytes()
    authority = _ChangingAuthority(
        manifests=[manifest, manifest], markdowns=[markdown], sidecars=[sidecar]
    )

    snapshot = read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert snapshot.body == "body"
    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (
        2,
        1,
        1,
    )


def test_mdsm_retries_invalid_sidecar_after_digest_binding(tmp_path: Path) -> None:
    path, markdown, _ = _write_pair(tmp_path)
    invalid_sidecar = b"{"
    path.with_suffix(".spans.json").write_bytes(invalid_sidecar)
    manifest_path = path.with_suffix(".pair.json")
    original = GenerationManifest.from_bytes(manifest_path.read_bytes())
    manifest_path.write_bytes(
        GenerationManifest.create(
            markdown_file=path.name,
            markdown_bytes=markdown,
            sidecar_file="source.spans.json",
            sidecar_bytes=invalid_sidecar,
            canonical_hash=original.canonical_hash,
        ).to_bytes()
    )

    with pytest.raises(ValueError, match="^sidecar contains invalid JSON$") as raised:
        _read(tmp_path)

    assert raised.value.__cause__ is None


def test_mdsm_retries_canonical_mismatch_after_stable_manifest_confirmation(
    tmp_path: Path,
) -> None:
    _, markdown, sidecar = _write_pair(tmp_path)
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="f" * 64,
    ).to_bytes()
    authority = _ChangingAuthority(
        manifests=[manifest] * 6,
        markdowns=[markdown] * 3,
        sidecars=[sidecar] * 3,
    )

    with pytest.raises(ValueError, match="^pair_canonical_mismatch$") as raised:
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert raised.value.__cause__ is None
    assert authority.manifest_reads == 6
    assert authority.document_reads == 3
    assert authority.sidecar_reads == 3


def test_mdsm_invalid_sidecar_fails_before_second_manifest_read(tmp_path: Path) -> None:
    _, markdown, sidecar = _write_pair(tmp_path)
    invalid_sidecar = b"{"
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=invalid_sidecar,
        canonical_hash=canonical_hash(
            {
                "type": "raw",
                "doc_id": SpanSidecar.from_bytes(sidecar).doc_id,
                "version_id": SpanSidecar.from_bytes(sidecar).version_id,
                "source_checksum": "a" * 64,
                "docling_version": "test",
                "generated_by": "test",
            },
            SpanSidecar.from_bytes(sidecar),
        ),
    ).to_bytes()
    authority = _ChangingAuthority(
        manifests=[manifest] * 3,
        markdowns=[markdown] * 3,
        sidecars=[invalid_sidecar] * 3,
    )

    with pytest.raises(ValueError, match="^sidecar contains invalid JSON$"):
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert authority.manifest_reads == 3
    assert authority.document_reads == 3
    assert authority.sidecar_reads == 3


def test_mdsm_manifest_change_restarts_exactly_three_times_then_is_unstable(
    tmp_path: Path,
) -> None:
    _, markdown, sidecar = _write_pair(tmp_path)
    canonical = canonical_hash(
        {
            "type": "raw",
            "doc_id": SpanSidecar.from_bytes(sidecar).doc_id,
            "version_id": SpanSidecar.from_bytes(sidecar).version_id,
            "source_checksum": "a" * 64,
            "docling_version": "test",
            "generated_by": "test",
        },
        SpanSidecar.from_bytes(sidecar),
    )
    first = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash=canonical,
    ).to_bytes()
    second = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="b" * 64,
    ).to_bytes()
    authority = _ChangingAuthority(
        manifests=[first, second] * 3,
        markdowns=[markdown] * 3,
        sidecars=[sidecar] * 3,
    )

    with pytest.raises(ValueError, match="^pair_unstable$") as raised:
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert raised.value.__cause__ is None
    assert authority.manifest_reads == 6
    assert authority.document_reads == 3
    assert authority.sidecar_reads == 3


@pytest.mark.parametrize("member", ("markdown", "sidecar"))
def test_mdsm_rejects_changed_member_then_accepts_one_stable_retry(
    tmp_path: Path, member: str
) -> None:
    path, markdown, sidecar = _write_pair(tmp_path)
    canonical = GenerationManifest.from_bytes(
        path.with_suffix(".pair.json").read_bytes()
    ).canonical_hash
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash=canonical,
    ).to_bytes()
    changed = (
        markdown + b"in-place-change"
        if member == "markdown"
        else sidecar + b"replacement-change"
    )
    authority = _ChangingAuthority(
        manifests=[manifest] * 3,
        markdowns=[changed, markdown] if member == "markdown" else [markdown] * 2,
        sidecars=[sidecar] * 2 if member == "markdown" else [changed, sidecar],
    )

    snapshot = read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert snapshot.markdown_bytes == markdown
    assert snapshot.sidecar_bytes == sidecar
    assert authority.document_reads == 2
    assert authority.sidecar_reads == (1 if member == "markdown" else 2)
    assert authority.manifest_reads == 3


class _CanaryAuthority:
    def __init__(
        self,
        stage: str,
        valid_manifest: bytes,
        bad_canonical_manifest: bytes,
        markdown: bytes,
        sidecar: bytes,
        canary: str,
    ) -> None:
        self.stage = stage
        self.valid_manifest = valid_manifest
        self.bad_canonical_manifest = bad_canonical_manifest
        self.markdown = markdown
        self.sidecar = sidecar
        self.canary = canary
        self.manifest_calls = 0

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        if self.stage == "manifest":
            raise ValueError(self.canary)
        if self.stage == "m2" and self.manifest_calls % 2:
            self.manifest_calls += 1
            raise ValueError(self.canary)
        self.manifest_calls += 1
        return (
            self.bad_canonical_manifest
            if self.stage == "canonical"
            else self.valid_manifest
        )

    def read_document(self, _: tuple[str, ...]) -> bytes:
        if self.stage == "document":
            raise ValueError(self.canary)
        return self.markdown

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        if self.stage == "sidecar":
            raise ValueError(self.canary)
        return self.sidecar


def _canary_manifests(markdown: bytes, sidecar: bytes) -> tuple[bytes, bytes]:
    frontmatter = {
        "type": "raw",
        "doc_id": SpanSidecar.from_bytes(sidecar).doc_id,
        "version_id": SpanSidecar.from_bytes(sidecar).version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    valid = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash=canonical_hash(frontmatter, SpanSidecar.from_bytes(sidecar)),
    ).to_bytes()
    invalid = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="f" * 64,
    ).to_bytes()
    return valid, invalid


@pytest.mark.parametrize(
    "stage", ("manifest", "document", "sidecar", "canonical", "m2")
)
def test_mdsm_redacts_pair_canaries_from_every_failure_stage(
    tmp_path: Path, stage: str
) -> None:
    _, markdown, sidecar = _write_pair(tmp_path)
    valid_manifest, bad_canonical_manifest = _canary_manifests(markdown, sidecar)
    canary = "CANARY /absolute/path credential=not-a-secret"
    authority = _CanaryAuthority(
        stage, valid_manifest, bad_canonical_manifest, markdown, sidecar, canary
    )

    with pytest.raises(ValueError) as raised:
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert canary not in str(raised.value)
    assert "/absolute/path" not in str(raised.value)
    assert "credential=" not in str(raised.value)
    assert raised.value.__cause__ is None
