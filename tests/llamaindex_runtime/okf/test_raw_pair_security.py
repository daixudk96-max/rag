"""Sidecar raw-pair authority regressions."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanSidecar


def test_from_bytes_has_no_filesystem_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "schema_version": 1,
            "doc_id": str(uuid4()),
            "version_id": str(uuid4()),
            "spans": [],
        }
    ).encode()
    monkeypatch.setattr(
        "llamaindex_runtime.okf.sidecar._read_sidecar_bytes_bounded",
        lambda _: pytest.fail("filesystem read"),
    )
    parsed = SpanSidecar.from_bytes(payload)
    assert parsed.spans == ()


def test_from_bytes_preserves_utf8_boundary_error() -> None:
    with pytest.raises(ValueError, match="^sidecar must be valid UTF-8$") as error:
        SpanSidecar.from_bytes(b"\xff")
    assert error.value.__cause__ is None


def test_document_invalid_utf8_has_no_public_exception_cause(tmp_path) -> None:
    from llamaindex_runtime.okf.parser import OKFParser

    path = tmp_path / "invalid.md"
    path.write_bytes(b"\xff")

    with pytest.raises(ValueError, match="^document must be valid UTF-8$") as error:
        OKFParser().parse_document(path)

    assert error.value.__cause__ is None
