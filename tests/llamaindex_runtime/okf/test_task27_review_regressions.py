"""Third-review regression contracts for raw-pair admission boundaries."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import _limits
from llamaindex_runtime.okf._raw_pair_admission import admit_raw_pair, thaw_frontmatter
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter, load_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.parser import OKFParser
from llamaindex_runtime.okf.raw_pair import read_raw_pair
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.rooted_write import publish_raw_pair
from llamaindex_runtime.okf.sidecar import SpanSidecar


def _raw_payload(body: str = "body") -> tuple[bytes, bytes, bytes]:
    doc_id, version_id = str(uuid4()), str(uuid4())
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, body).encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


class _Authority:
    def __init__(self, manifests: list[bytes], markdown: bytes, sidecar: bytes) -> None:
        self.manifests = iter(manifests)
        self.markdown = markdown
        self.sidecar = sidecar
        self.manifest_reads = self.document_reads = self.sidecar_reads = 0

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.manifest_reads += 1
        return next(self.manifests)

    def read_document(self, _: tuple[str, ...]) -> bytes:
        self.document_reads += 1
        return self.markdown

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.sidecar_reads += 1
        return self.sidecar


def test_success_parses_sidecar_once_with_mdsm_read_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llamaindex_runtime.okf import _raw_pair_admission as admission

    markdown, sidecar, manifest = _raw_payload()
    authority = _Authority([manifest, manifest], markdown, sidecar)
    calls = 0
    original = admission.SpanSidecar.from_bytes

    def record(value: bytes) -> SpanSidecar:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(admission.SpanSidecar, "from_bytes", record)
    read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert calls == 1
    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (2, 1, 1)


def test_canonical_error_waits_for_stable_m2_and_reads_it_each_attempt() -> None:
    markdown, sidecar, manifest = _raw_payload()
    invalid = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="f" * 64,
    ).to_bytes()
    authority = _Authority([invalid, manifest] * 3, markdown, sidecar)

    with pytest.raises(ValueError, match="^pair_unstable$"):
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (6, 3, 3)


def test_canonical_mismatch_reads_m2_before_reporting_each_attempt() -> None:
    markdown, sidecar, _ = _raw_payload()
    invalid = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="f" * 64,
    ).to_bytes()
    authority = _Authority([invalid] * 6, markdown, sidecar)

    with pytest.raises(ValueError, match="^pair_canonical_mismatch$"):
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (6, 3, 3)


def test_pairs_tuple_freezes_deeply_and_thaws_without_aliasing() -> None:
    doc_id, version_id = str(uuid4()), str(uuid4())
    markdown = (
        "---\ntype: raw\ndoc_id: "
        + doc_id
        + "\nversion_id: "
        + version_id
        + "\nsource_checksum: "
        + "a" * 64
        + "\ndocling_version: test\ngenerated_by: test\npairs: !!pairs [{one: [two]}]\n---\nbody\n"
    ).encode()
    frontmatter, _ = load_raw_frontmatter(markdown.decode())
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    admitted = admit_raw_pair(
        markdown,
        sidecar.to_bytes(),
        GenerationManifest.create(
            markdown_file="source.md",
            markdown_bytes=markdown,
            sidecar_file="source.spans.json",
            sidecar_bytes=sidecar.to_bytes(),
            canonical_hash=canonical_hash(frontmatter, sidecar),
        ),
    )

    with pytest.raises(AttributeError):
        admitted.frontmatter["pairs"][0][1].append("mutated")  # type: ignore[union-attr,index]
    parser_value = thaw_frontmatter(admitted.frontmatter)
    parser_value["pairs"][0][1].append("changed")
    assert admitted.frontmatter["pairs"][0][1] == ("two",)
    assert isinstance(parser_value["pairs"][0], tuple)


def test_nonraw_parse_extracts_frontmatter_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llamaindex_runtime.okf import parser as parser_module

    calls = 0
    original = parser_module.extract_bounded_frontmatter

    def record(content: str):
        nonlocal calls
        calls += 1
        return original(content)

    monkeypatch.setattr(parser_module, "extract_bounded_frontmatter", record)
    document = OKFParser()._parse_content(
        Path("legacy.md"), None, b"---\ntype: legacy\n---\n---\nbody"
    )
    assert (calls, document.body) == (1, "---\nbody")


def test_dynamic_limit_is_shared_by_reader_and_publisher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    markdown, sidecar, manifest = _raw_payload()
    monkeypatch.setattr(_limits, "MAX_DOCUMENT_BYTES", 1)
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("backend called"),
    )
    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "source", markdown, sidecar, manifest)
    path = tmp_path / "legacy.md"
    path.write_bytes(b"---\ntype: legacy\n---\nbody")
    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError, match="^document exceeds maximum size$"):
            authority.read_document(("legacy.md",))
    with pytest.raises(ValueError, match="^document exceeds maximum size$"):
        OKFParser().parse_document(path)


def test_real_limit_plus_one_rejects_before_publish_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    body = "x" * (_limits.MAX_DOCUMENT_BYTES + 1)
    markdown, sidecar, manifest = _raw_payload(body)
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("backend called"),
    )
    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "source", markdown, sidecar, manifest)
    assert not (tmp_path / "raw").exists()
