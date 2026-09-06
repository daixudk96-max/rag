"""RED contracts for filesystem-free publisher payload admission."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import rooted_write
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_write import publish_raw_pair
from llamaindex_runtime.okf.sidecar import SpanSidecar


def _payload() -> tuple[bytes, bytes, bytes]:
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
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file="report.md",
        markdown_bytes=markdown,
        sidecar_file="report.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


def _replace_manifest(manifest: bytes, **changes: object) -> bytes:
    value = json.loads(manifest)
    value.update(changes)
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode() + b"\n"


def _rebind(markdown: bytes, sidecar: bytes, canonical_hash: str) -> bytes:
    return GenerationManifest.create(
        markdown_file="report.md",
        markdown_bytes=markdown,
        sidecar_file="report.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash=canonical_hash,
    ).to_bytes()


_INVALID_BOUND_PAYLOAD_TRANSFORMS = (
    lambda markdown, sidecar, manifest: (
        markdown,
        sidecar,
        _replace_manifest(manifest, canonical_hash="f" * 64),
    ),
    lambda markdown, sidecar, manifest: (
        markdown,
        b'{"schema_version":1}',
        _replace_manifest(
            manifest,
            sidecar_sha256=__import__("hashlib")
            .sha256(b'{"schema_version":1}')
            .hexdigest(),
        ),
    ),
    lambda markdown, sidecar, manifest: (
        markdown.replace(b"version_id:", b"version_id: not-a-uuid #"),
        sidecar,
        manifest,
    ),
    lambda markdown, sidecar, manifest: (
        b"type: raw\n",
        sidecar,
        _replace_manifest(
            manifest,
            markdown_sha256=__import__("hashlib").sha256(b"type: raw\n").hexdigest(),
        ),
    ),
)


@pytest.mark.parametrize("transform", _INVALID_BOUND_PAYLOAD_TRANSFORMS)
def test_publish_rejects_semantically_invalid_bound_payload_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transform
) -> None:
    calls = 0

    def backend(*_: object) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("llamaindex_runtime.okf.rooted_write._publish", backend)
    with pytest.raises(ValueError, match="^pair_publish_failed$") as raised:
        publish_raw_pair(tmp_path, "report", *transform(*_payload()))

    assert raised.value.__cause__ is None
    assert calls == 0
    assert not (tmp_path / "raw").exists()


def test_publish_rejects_bound_frontmatter_sidecar_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    markdown, sidecar, manifest = _payload()
    changed = markdown.replace(
        b"doc_id:", b"doc_id: 33333333-3333-3333-3333-333333333333 #"
    )
    bound = _rebind(
        changed, sidecar, GenerationManifest.from_bytes(manifest).canonical_hash
    )
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("backend must not be called"),
    )

    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "report", changed, sidecar, bound)

    assert not (tmp_path / "raw").exists()


def test_publish_admits_valid_canonical_serializer_shape_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[object] = []
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *args: received.append(args),
    )

    publish_raw_pair(tmp_path, "report", *_payload())

    assert len(received) == 1


def test_publisher_calls_shared_admission_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original_admission = rooted_write.admit_raw_pair

    def record_admission(*args: object):
        calls.append("admission")
        return original_admission(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(rooted_write, "admit_raw_pair", record_admission)
    monkeypatch.setattr(rooted_write, "_publish", lambda *_: calls.append("backend"))

    publish_raw_pair(tmp_path, "report", *_payload())

    assert calls == ["admission", "backend"]


def test_publish_uses_shared_document_size_limit_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    markdown, sidecar, manifest = _payload()
    calls: list[object] = []
    monkeypatch.setattr(
        "llamaindex_runtime.okf._limits.MAX_DOCUMENT_BYTES", len(markdown) - 1
    )
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish", lambda *args: calls.append(args)
    )

    with pytest.raises(ValueError, match="^pair_publish_failed$") as raised:
        publish_raw_pair(tmp_path, "report", markdown, sidecar, manifest)

    assert raised.value.__cause__ is None
    assert calls == []
    assert not (tmp_path / "raw").exists()


def test_document_size_limit_boundary_helper_matches_reader_and_publisher_contract() -> (
    None
):
    from llamaindex_runtime.okf._limits import (
        MAX_DOCUMENT_BYTES,
        document_size_exceeds_limit,
    )

    assert not document_size_exceeds_limit(MAX_DOCUMENT_BYTES)
    assert document_size_exceeds_limit(MAX_DOCUMENT_BYTES + 1)
