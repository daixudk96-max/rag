"""Task27 value-domain safety contracts for canonical raw-pair admission."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_serialize
from llamaindex_runtime.okf.diagnostics import (
    diagnostic_safe_path,
    diagnostic_safe_text,
    diagnostic_summary,
)
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import read_raw_pair
from llamaindex_runtime.okf.rooted_write import publish_raw_pair
from llamaindex_runtime.okf.sidecar import SpanSidecar


class _ThreeAttemptAuthority:
    def __init__(self, manifest: bytes, markdown: bytes, sidecar: bytes) -> None:
        self._manifests: Iterator[bytes] = iter([manifest] * 6)
        self._markdown = markdown
        self._sidecar = sidecar
        self.manifest_reads = 0
        self.document_reads = 0
        self.sidecar_reads = 0

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.manifest_reads += 1
        return next(self._manifests)

    def read_document(self, _: tuple[str, ...]) -> bytes:
        self.document_reads += 1
        return self._markdown

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.sidecar_reads += 1
        return self._sidecar


def _raw_payload(extra: str) -> tuple[bytes, bytes, bytes]:
    doc_id, version_id = str(uuid4()), str(uuid4())
    markdown = (
        "---\n"
        "type: raw\n"
        f"doc_id: {doc_id}\n"
        f"version_id: {version_id}\n"
        f"source_checksum: {'a' * 64}\n"
        "docling_version: test\n"
        "generated_by: test\n"
        f"{extra}"
        "---\nbody\n"
    ).encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ()).to_bytes()
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar,
        canonical_hash="f" * 64,
    ).to_bytes()
    return markdown, sidecar, manifest


@pytest.mark.parametrize(
    "value",
    (
        {"set": {"item"}},
        {"binary": b"item"},
        {"binary": bytearray(b"item")},
        {"uuid": UUID("b2191a11-cd8b-4c6e-b34a-7b5552e3c03c")},
        {"decimal": Decimal("1.5")},
        {"number": math.inf},
        {"number": math.nan},
        {1: "not-a-string-key"},
        {"surrogate": "\ud800"},
    ),
    ids=(
        "set",
        "bytes",
        "bytearray",
        "uuid",
        "decimal",
        "infinity",
        "nan",
        "int-key",
        "surrogate",
    ),
)
def test_canonical_serialize_rejects_unsupported_values_with_fixed_error(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_serialize(value)


def test_canonical_serialize_rejects_direct_self_list_without_recursion_error() -> None:
    value: list[object] = []
    value.append(value)

    with pytest.raises(ValueError, match="^frontmatter_canonical_cycle$"):
        canonical_serialize(value)


def test_canonical_serialize_rejects_direct_self_dict_without_recursion_error() -> None:
    value: dict[str, object] = {}
    value["self"] = value

    with pytest.raises(ValueError, match="^frontmatter_canonical_cycle$"):
        canonical_serialize(value)


def test_canonical_serialize_allows_shared_acyclic_aliases_deterministically() -> None:
    shared = ["same", {"value": 1}]
    value = {"first": shared, "second": shared}

    assert canonical_serialize(value) == canonical_serialize(value)
    assert canonical_serialize(value) == (
        b'{"first":["same",{"value":1}],"second":["same",{"value":1}]}'
    )


def test_canonical_serialize_bounds_alias_dag_expansion_work() -> None:
    value: object = ["leaf"]
    for _ in range(14):
        value = [value, value]

    with pytest.raises(ValueError, match="^frontmatter_canonical_resource_limit$"):
        canonical_serialize(value)


def test_canonical_hash_v1_golden_bytes_and_hash_are_unchanged() -> None:
    value = {"z": ["中", 2], "a": {"b": True}}

    assert canonical_serialize(value) == b'{"a":{"b":true},"z":["\xe4\xb8\xad",2]}'
    assert hashlib.sha256(canonical_serialize(value)).hexdigest() == (
        "908fa58e5d6712e8d4fd65e5c7954a0fd1b7e5b606dcaf5efdc6606292c178f9"
    )


@pytest.mark.parametrize(
    "extra",
    (
        "bad: !!set {item: null}\n",
        "bad: !!binary aXRlbQ==\n",
        "bad: &loop [*loop]\n",
    ),
    ids=("set", "binary", "cycle"),
)
def test_raw_reader_retries_exactly_three_times_and_redacts_canonical_errors(
    extra: str,
) -> None:
    markdown, sidecar, manifest = _raw_payload(extra)
    authority = _ThreeAttemptAuthority(manifest, markdown, sidecar)

    expected = (
        "frontmatter_canonical_cycle"
        if "loop" in extra
        else "frontmatter_canonical_unsupported"
    )
    with pytest.raises(ValueError, match=f"^{expected}$") as error:
        read_raw_pair(authority, ("raw", "source.md"))  # type: ignore[arg-type]

    assert error.value.__cause__ is None
    assert (
        authority.manifest_reads,
        authority.document_reads,
        authority.sidecar_reads,
    ) == (
        3,
        3,
        3,
    )


@pytest.mark.parametrize(
    "extra",
    (
        "bad: !!set {item: null}\n",
        "bad: !!binary aXRlbQ==\n",
        "bad: &loop [*loop]\n",
    ),
    ids=("set", "binary", "cycle"),
)
def test_raw_publisher_rejects_canonical_domain_before_backend(
    extra: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    markdown, sidecar, manifest = _raw_payload(extra)
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("publisher backend must not run"),
    )

    with pytest.raises(ValueError, match="^pair_publish_failed$") as error:
        publish_raw_pair(tmp_path, "source", markdown, sidecar, manifest)  # type: ignore[arg-type]

    assert error.value.__cause__ is None
    assert not (tmp_path / "raw").exists()


class _RaisingStringificationCanary:
    def __str__(self) -> str:
        raise RecursionError("must not be called")

    def __repr__(self) -> str:
        raise TypeError("must not be called")


class _EncodeOverride(str):
    def encode(self, *args: object, **kwargs: object) -> bytes:
        raise AssertionError("subclass encode override must not run")


def test_diagnostic_text_and_path_never_render_non_strings() -> None:
    canary = _RaisingStringificationCanary()

    assert diagnostic_summary(canary) == "invalid-type=non-string"
    assert diagnostic_safe_text(canary) == "invalid-type=non-string"
    assert diagnostic_safe_path(canary) == "invalid-type=non-string"


def test_diagnostic_text_and_path_bypass_string_subclass_encode_override() -> None:
    value = _EncodeOverride("canary")
    expected = "len=6 sha256=" + hashlib.sha256(b"canary").hexdigest()

    assert diagnostic_safe_text(value) == expected
    assert diagnostic_safe_path(value) == expected
