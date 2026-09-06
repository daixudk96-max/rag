"""Task 27 regression tests for exact-type diagnostic and admission boundaries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

import pytest

from llamaindex_runtime.okf._raw_pair_admission import admit_raw_pair, thaw_frontmatter
from llamaindex_runtime.okf.canonical_hash import canonical_hash, canonical_serialize
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.diagnostics import diagnostic_safe_path
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import (
    _prepare_raw_directory_pair,
    _read_sidecar,
    _redacted,
)
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.roundtrip import (
    first_roundtrip_mismatch,
    persisted_span_id_mismatch,
)
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar


class _ProtocolCanary:
    calls = 0

    def __str__(self) -> str:
        type(self).calls += 1
        raise AssertionError("__str__ must not run")

    def __repr__(self) -> str:
        type(self).calls += 1
        raise AssertionError("__repr__ must not run")

    def __iter__(self) -> Iterator[object]:
        type(self).calls += 1
        raise AssertionError("__iter__ must not run")

    def __len__(self) -> int:
        type(self).calls += 1
        raise AssertionError("__len__ must not run")

    def __getitem__(self, _: object) -> object:
        type(self).calls += 1
        raise AssertionError("__getitem__ must not run")

    def __eq__(self, _: object) -> bool:
        type(self).calls += 1
        raise AssertionError("__eq__ must not run")


class _HostileValueError(ValueError):
    def __str__(self) -> str:
        _ProtocolCanary.calls += 1
        raise AssertionError("exception __str__ must not run")

    def __repr__(self) -> str:
        _ProtocolCanary.calls += 1
        raise AssertionError("exception __repr__ must not run")


class _HostileMapping(Mapping[str, Any]):
    def __iter__(self) -> Iterator[str]:
        _ProtocolCanary.calls += 1
        raise AssertionError("mapping iteration must not run")

    def __len__(self) -> int:
        _ProtocolCanary.calls += 1
        raise AssertionError("mapping length must not run")

    def __getitem__(self, _: str) -> Any:
        _ProtocolCanary.calls += 1
        raise AssertionError("mapping lookup must not run")

    def items(self) -> object:  # type: ignore[override]
        _ProtocolCanary.calls += 1
        raise AssertionError("mapping items must not run")


class _DictSubclass(dict[str, Any]):
    def items(self) -> object:  # type: ignore[override]
        _ProtocolCanary.calls += 1
        raise AssertionError("dict subclass items must not run")


class _PathSubclass(PurePosixPath):
    def __str__(self) -> str:
        _ProtocolCanary.calls += 1
        raise AssertionError("path subclass __str__ must not run")


class _PathLike:
    def __fspath__(self) -> str:
        _ProtocolCanary.calls += 1
        raise AssertionError("__fspath__ must not run")


def _reset() -> None:
    _ProtocolCanary.calls = 0


def _frontmatter() -> dict[str, Any]:
    return {
        "type": "raw",
        "doc_id": str(uuid4()),
        "version_id": str(uuid4()),
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }


def _span() -> SpanRecord:
    return SpanRecord("00000000-0000-0000-0000-000000000001", None, (), 0, "text")


@pytest.mark.parametrize(
    "error",
    (_HostileValueError("pair_hash_mismatch"), ValueError("unknown")),
)
def test_raw_pair_redaction_rejects_untrusted_error_rendering(
    error: ValueError,
) -> None:
    _reset()

    assert _redacted(error).args == ("pair_manifest_invalid",)
    assert _ProtocolCanary.calls == 0


def test_raw_pair_special_error_rewrites_require_exact_trusted_value_error() -> None:
    class _Manifest:
        sidecar_file = "x.spans.json"

    class _Authority:
        def read_sidecar(self, _: tuple[str, ...]) -> bytes:
            raise _HostileValueError("sidecar cannot be read")

    _reset()
    with pytest.raises(_HostileValueError):
        _read_sidecar(
            cast(BundleAuthority, _Authority()),
            ("raw", "x.md"),
            cast(GenerationManifest, _Manifest()),
        )
    with pytest.raises(ValueError, match="^raw file requires adjacent sidecar$"):
        _read_sidecar(
            type(
                "Authority",
                (),
                {
                    "read_sidecar": lambda *_: (_ for _ in ()).throw(
                        ValueError("sidecar cannot be read")
                    )
                },
            )(),
            ("raw", "x.md"),
            cast(GenerationManifest, _Manifest()),
        )
    with pytest.raises(
        ValueError, match="^raw directory document must declare type 'raw'$"
    ):
        _prepare_raw_directory_pair(
            b"---\ntype: legacy\n---\nbody",
            SpanSidecar(1, str(uuid4()), str(uuid4()), ()).to_bytes(),
        )
    assert _ProtocolCanary.calls == 0


def test_canonical_hash_rejects_proxy_custom_mapping_and_dict_subclass_without_hooks() -> (
    None
):
    sidecar = SpanSidecar(1, str(uuid4()), str(uuid4()), ())
    values = (_HostileMapping(), MappingProxyType(_HostileMapping()), _DictSubclass())
    for value in values:
        _reset()
        with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
            canonical_hash(cast(Any, value), sidecar)
        assert _ProtocolCanary.calls == 0


def test_thawed_admitted_frontmatter_rehashes_to_manifest() -> None:
    frontmatter = _frontmatter()
    markdown = dump_raw_frontmatter(frontmatter, "body").encode()
    sidecar = SpanSidecar(1, frontmatter["doc_id"], frontmatter["version_id"], ())
    manifest = GenerationManifest.create(
        markdown_file="source.md",
        markdown_bytes=markdown,
        sidecar_file="source.spans.json",
        sidecar_bytes=sidecar.to_bytes(),
        canonical_hash=canonical_hash(frontmatter, sidecar),
    )

    admitted = admit_raw_pair(markdown, sidecar.to_bytes(), manifest)
    thawed = thaw_frontmatter(admitted.frontmatter)
    assert type(thawed) is dict
    assert canonical_hash(thawed, sidecar) == manifest.canonical_hash
    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_hash(cast(Any, admitted.frontmatter), sidecar)


def test_roundtrip_rejects_hostile_containers_and_both_invalid_sides_without_hooks() -> (
    None
):
    _reset()
    mismatch = first_roundtrip_mismatch(
        cast(Any, _ProtocolCanary()),
        cast(Any, _ProtocolCanary()),
        doc_id="doc",
        file_path="raw/x.md",
    )

    assert mismatch is not None
    assert "invalid-type=non-string" in mismatch
    assert _ProtocolCanary.calls == 0


def test_roundtrip_rejects_invalid_span_fields_without_comparing_hooks() -> None:
    valid: dict[str, Any] = {
        "page_no": None,
        "heading_path": [],
        "offset": 0,
        "text": "x",
        "span_id": "id",
    }
    hostile = {**valid, "text": _ProtocolCanary()}
    _reset()

    mismatch = first_roundtrip_mismatch(
        [hostile], [valid], doc_id="doc", file_path="raw/x.md"
    )

    assert mismatch is not None
    assert "invalid-type=non-string" in mismatch
    assert _ProtocolCanary.calls == 0


def test_persisted_span_diagnostics_reject_hostile_containers_without_hooks() -> None:
    _reset()
    assert persisted_span_id_mismatch(
        cast(Any, _ProtocolCanary()), cast(Any, _ProtocolCanary())
    ) == ("SIDECAR SPAN ID MISMATCH: invalid-type=non-canonical")
    assert _ProtocolCanary.calls == 0


def test_diagnostic_safe_path_accepts_only_exact_standard_path_types() -> None:
    trusted = PurePosixPath("private", "source.md")
    expected = diagnostic_safe_path(str(trusted))
    assert diagnostic_safe_path(trusted) == expected
    for hostile in (_PathLike(), _PathSubclass("private/source.md")):
        _reset()
        assert diagnostic_safe_path(hostile) == "invalid-type=non-string"
        assert _ProtocolCanary.calls == 0


def test_canonical_serialize_rejects_string_subclasses_without_hooks() -> None:
    class _StringSubclass(str):
        def __str__(self) -> str:
            _ProtocolCanary.calls += 1
            raise AssertionError("string subclass must not render")

    _reset()
    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_serialize(_StringSubclass("value"))
    assert _ProtocolCanary.calls == 0
