"""Hostile-hook closure tests for Task 27 public OKF boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path, PurePath
from typing import Any, cast
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_serialize
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_write import publish_raw_pair
from llamaindex_runtime.okf.roundtrip import (
    persisted_span_id_mismatch,
    recompute_span_dicts,
    recompute_span_id,
    validate_span_identity_admission,
)
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar


class _Canary:
    calls = 0

    @classmethod
    def reset(cls) -> None:
        cls.calls = 0


class _HostileTimezone(tzinfo):
    def utcoffset(self, _: datetime | None) -> timedelta:
        _Canary.calls += 1
        raise AssertionError("utcoffset must not run")

    def dst(self, _: datetime | None) -> timedelta:
        _Canary.calls += 1
        raise AssertionError("dst must not run")

    def tzname(self, _: datetime | None) -> str:
        _Canary.calls += 1
        raise AssertionError("tzname must not run")


class _HostileStr(str):
    def encode(self, *args: object, **kwargs: object) -> bytes:
        _Canary.calls += 1
        raise AssertionError("str hook must not run")

    def __format__(self, _: str) -> str:
        _Canary.calls += 1
        raise AssertionError("str hook must not run")


class _HostileInt(int):
    def __ge__(self, _: object) -> bool:
        _Canary.calls += 1
        raise AssertionError("int hook must not run")


class _HostileTuple(tuple[object, ...]):
    def __iter__(self):  # type: ignore[no-untyped-def]
        _Canary.calls += 1
        raise AssertionError("tuple hook must not run")


class _HostileList(list[object]):
    def __iter__(self):  # type: ignore[no-untyped-def]
        _Canary.calls += 1
        raise AssertionError("list hook must not run")


class _HostileDict(dict[str, object]):
    def keys(self):  # type: ignore[no-untyped-def]
        _Canary.calls += 1
        raise AssertionError("dict hook must not run")


class _HostileSpan(SpanRecord):
    def __getattribute__(self, _: str) -> object:
        _Canary.calls += 1
        raise AssertionError("SpanRecord subclass hook must not run")


class _HostilePath(Path):
    _flavour = cast(Any, type(Path()))._flavour

    def __fspath__(self) -> str:
        _Canary.calls += 1
        raise AssertionError("path hook must not run")


class _HostilePathLike:
    def __fspath__(self) -> str:
        _Canary.calls += 1
        raise AssertionError("path hook must not run")


class _HostileBytes(bytes):
    def __bytes__(self) -> bytes:
        _Canary.calls += 1
        raise AssertionError("bytes hook must not run")


def _span() -> SpanRecord:
    return SpanRecord(str(uuid4()), None, ("heading",), 0, "text")


def _payload(slug: str = "source") -> tuple[bytes, bytes, bytes]:
    doc_id, version_id = str(uuid4()), str(uuid4())
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "body").encode("utf-8")
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file=f"{slug}.md",
        markdown_bytes=markdown,
        sidecar_file=f"{slug}.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash="0" * 64,
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


def test_canonical_datetime_rejects_custom_tzinfo_without_calling_hooks() -> None:
    _Canary.reset()
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=_HostileTimezone())

    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_serialize(value)

    assert _Canary.calls == 0


@pytest.mark.parametrize(
    "value, expected",
    (
        (datetime(2026, 1, 2, 3, 4, 5), b'"2026-01-02T03:04:05"'),
        (
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            b'"2026-01-02T03:04:05+00:00"',
        ),
        (
            datetime(
                2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
            b'"2026-01-02T03:04:05+05:30"',
        ),
    ),
)
def test_canonical_datetime_keeps_frozen_naive_and_timezone_values(
    value: datetime, expected: bytes
) -> None:
    assert canonical_serialize(value) == expected


@pytest.mark.parametrize(
    "field, value",
    (
        ("span_id", _HostileStr(str(uuid4()))),
        ("page_no", _HostileInt(0)),
        ("heading_path", _HostileTuple(("heading",))),
        ("offset", _HostileInt(0)),
        ("text", _HostileStr("text")),
    ),
    ids=("span-id", "page-number", "heading-path", "offset", "text"),
)
def test_span_record_constructor_rejects_subclass_fields_without_hooks(
    field: str, value: object
) -> None:
    values: dict[str, Any] = {
        "span_id": str(uuid4()),
        "page_no": None,
        "heading_path": ("heading",),
        "offset": 0,
        "text": "text",
    }
    values[field] = value
    _Canary.reset()

    with pytest.raises(ValueError):
        SpanRecord(**cast(Any, values))

    assert _Canary.calls == 0


def test_span_record_from_dict_rejects_dict_list_and_string_subclasses_without_hooks() -> (
    None
):
    valid = {
        "span_id": str(uuid4()),
        "page_no": None,
        "heading_path": ["heading"],
        "offset": 0,
        "text": "text",
    }
    for value in (
        _HostileDict(valid),
        {**valid, "heading_path": _HostileList(["heading"])},
        {**valid, "text": _HostileStr("text")},
    ):
        _Canary.reset()
        with pytest.raises(ValueError):
            SpanRecord.from_dict(value)  # type: ignore[arg-type]
        assert _Canary.calls == 0


def test_sidecar_rejects_tuple_dict_and_span_subclasses_without_hooks() -> None:
    doc_id, version_id = str(uuid4()), str(uuid4())
    hostile_span = object.__new__(_HostileSpan)
    object.__setattr__(hostile_span, "span_id", str(uuid4()))
    object.__setattr__(hostile_span, "page_no", None)
    object.__setattr__(hostile_span, "heading_path", ())
    object.__setattr__(hostile_span, "offset", 0)
    object.__setattr__(hostile_span, "text", "text")
    for value in (
        ("spans", _HostileTuple((_span(),))),
        ("spans", (hostile_span,)),
    ):
        _Canary.reset()
        with pytest.raises(ValueError):
            SpanSidecar(1, doc_id, version_id, value[1])  # type: ignore[arg-type]
        assert _Canary.calls == 0
    _Canary.reset()
    with pytest.raises(ValueError):
        SpanSidecar.from_dict(_HostileDict())
    assert _Canary.calls == 0


def test_roundtrip_identity_operations_reject_malformed_or_subclass_spans_without_hooks() -> (
    None
):
    malformed = object.__new__(SpanRecord)
    object.__setattr__(malformed, "span_id", _HostileStr(str(uuid4())))
    object.__setattr__(malformed, "page_no", _HostileInt(0))
    object.__setattr__(malformed, "heading_path", _HostileTuple(("heading",)))
    object.__setattr__(malformed, "offset", _HostileInt(0))
    object.__setattr__(malformed, "text", _HostileStr("text"))
    hostile_subclass = object.__new__(_HostileSpan)
    for span in (malformed, hostile_subclass):
        _Canary.reset()
        with pytest.raises(ValueError):
            recompute_span_id(span, doc_id=str(uuid4()), version_id=str(uuid4()))
        with pytest.raises(ValueError):
            recompute_span_dicts((span,), doc_id=str(uuid4()), version_id=str(uuid4()))
        with pytest.raises(ValueError):
            validate_span_identity_admission(
                (span,), doc_id=str(uuid4()), version_id=str(uuid4())
            )
        assert _Canary.calls == 0
    _Canary.reset()
    assert persisted_span_id_mismatch((malformed,), [{"span_id": str(uuid4())}]) == (
        "SIDECAR SPAN ID MISMATCH at span[0]: invalid-type=non-string"
    )
    assert _Canary.calls == 0


@pytest.mark.parametrize(
    "root, slug, markdown, sidecar, manifest",
    (
        (_HostilePathLike(), "source", *_payload()),
        (_HostilePath("."), "source", *_payload()),
        (Path("."), _HostileStr("source"), *_payload()),
        (Path("."), "source", _HostileBytes(_payload()[0]), *_payload()[1:]),
    ),
    ids=("path-like", "path-subclass", "slug-subclass", "bytes-subclass"),
)
def test_publisher_rejects_nonexact_public_inputs_before_backend_or_hooks(
    root: object,
    slug: object,
    markdown: object,
    sidecar: object,
    manifest: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _Canary.reset()
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("publisher backend must not run"),
    )

    with pytest.raises(ValueError, match="^pair_publish_failed$") as error:
        publish_raw_pair(root, slug, markdown, sidecar, manifest)  # type: ignore[arg-type]

    assert error.value.__cause__ is None
    assert _Canary.calls == 0
    assert not (tmp_path / "raw").exists()


def test_publisher_rejects_pure_path_before_backend_or_hooks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _Canary.reset()
    monkeypatch.setattr(
        "llamaindex_runtime.okf.rooted_write._publish",
        lambda *_: pytest.fail("publisher backend must not run"),
    )
    markdown, sidecar, manifest = _payload()

    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(PurePath("."), "source", markdown, sidecar, manifest)  # type: ignore[arg-type]

    assert _Canary.calls == 0
    assert not (tmp_path / "raw").exists()
