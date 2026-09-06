from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._sidecar_testkit import (
    _sidecar,
    _valid_sidecar_dict,
    _valid_sidecar_values,
    _valid_span_dict,
    _valid_span_values,
)


def test_sidecar_dump_load_round_trip_preserves_span_coordinates(tmp_path) -> None:
    sidecar = _sidecar()
    path = tmp_path / "document.spans.json"

    sidecar.dump(path)
    loaded = SpanSidecar.load(path)

    assert loaded == sidecar
    assert loaded.spans[0].page_no == 3
    assert loaded.spans[0].heading_path == ("Introduction", "Scope")
    assert loaded.spans[0].offset == 128
    assert loaded.spans[0].text == "Normalized first span."
    assert loaded.spans[0].span_id == sidecar.spans[0].span_id


def test_sidecar_rejects_unknown_schema_version(tmp_path) -> None:
    path = tmp_path / "document.spans.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "doc_id": str(uuid4()),
                "version_id": str(uuid4()),
                "spans": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        SpanSidecar.load(path)


def test_sidecar_rejects_missing_spans_field(tmp_path) -> None:
    path = tmp_path / "document.spans.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "doc_id": str(uuid4()),
                "version_id": str(uuid4()),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="spans"):
        SpanSidecar.load(path)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("span_id", "not-a-uuid"),
        ("page_no", -1),
        ("page_no", True),
        ("offset", -1),
        ("offset", True),
        ("text", ""),
        ("heading_path", ["Introduction"]),
        ("heading_path", ("Introduction", 1)),
    ),
)
def test_span_record_constructor_rejects_invalid_values(
    field: str,
    invalid_value: object,
) -> None:
    values = {**_valid_span_values(), field: invalid_value}

    with pytest.raises(ValueError, match=field):
        SpanRecord(**cast(Any, values))


@pytest.mark.parametrize("page_no", (None, 0))
def test_span_record_constructor_accepts_boundary_values(page_no: int | None) -> None:
    record = SpanRecord(
        span_id=str(uuid4()),
        page_no=page_no,
        heading_path=(),
        offset=0,
        text="Normalized span.",
    )

    assert record.page_no == page_no
    assert record.heading_path == ()
    assert record.offset == 0


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("schema_version", 2),
        ("schema_version", True),
        ("doc_id", "not-a-uuid"),
        ("version_id", "not-a-uuid"),
        ("spans", []),
        ("spans", ("not-a-span-record",)),
    ),
)
def test_span_sidecar_constructor_rejects_invalid_values(
    field: str,
    invalid_value: object,
) -> None:
    values = {**_valid_sidecar_values(), field: invalid_value}

    with pytest.raises(ValueError, match=field):
        SpanSidecar(**cast(Any, values))


def test_span_sidecar_constructor_accepts_empty_spans_tuple() -> None:
    sidecar = SpanSidecar(
        schema_version=1,
        doc_id=str(uuid4()),
        version_id=str(uuid4()),
        spans=(),
    )

    assert sidecar.spans == ()


class TestSpanRecordFromDictBoundaryValidation:
    """SpanRecord.from_dict must validate required fields with named errors."""

    def test_missing_span_id_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        del data["span_id"]

        with pytest.raises(ValueError, match="span_id"):
            SpanRecord.from_dict(data)

    def test_missing_offset_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        del data["offset"]

        with pytest.raises(ValueError, match="offset"):
            SpanRecord.from_dict(data)

    def test_missing_text_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        del data["text"]

        with pytest.raises(ValueError, match="text"):
            SpanRecord.from_dict(data)

    def test_missing_heading_path_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        del data["heading_path"]

        with pytest.raises(ValueError, match="heading_path"):
            SpanRecord.from_dict(data)

    def test_wrong_type_span_id_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        data["span_id"] = 12345

        with pytest.raises(ValueError, match="span_id"):
            SpanRecord.from_dict(data)

    def test_wrong_type_offset_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        data["offset"] = "128"

        with pytest.raises(ValueError, match="offset"):
            SpanRecord.from_dict(data)

    def test_wrong_type_text_raises_value_error_naming_field(self) -> None:
        data = _valid_span_dict()
        data["text"] = 42

        with pytest.raises(ValueError, match="text"):
            SpanRecord.from_dict(data)

    def test_missing_page_no_raises_value_error_naming_field(self) -> None:
        """Per frozen contract, page_no is required. JSON null is allowed, but omission is not."""
        data = _valid_span_dict()
        del data["page_no"]

        with pytest.raises(ValueError, match="page_no"):
            SpanRecord.from_dict(data)

    def test_page_no_null_is_allowed(self) -> None:
        """JSON null for page_no is valid and becomes None."""
        data = _valid_span_dict()
        data["page_no"] = None

        record = SpanRecord.from_dict(data)

        assert record.page_no is None


class TestSpanSidecarFromDictBoundaryValidation:
    """SpanSidecar.from_dict must validate required fields with named errors."""

    def test_missing_schema_version_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        del data["schema_version"]

        with pytest.raises(ValueError, match="schema_version"):
            SpanSidecar.from_dict(data)

    def test_missing_doc_id_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        del data["doc_id"]

        with pytest.raises(ValueError, match="doc_id"):
            SpanSidecar.from_dict(data)

    def test_missing_version_id_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        del data["version_id"]

        with pytest.raises(ValueError, match="version_id"):
            SpanSidecar.from_dict(data)

    def test_wrong_type_schema_version_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        data["schema_version"] = "1"

        with pytest.raises(ValueError, match="schema_version"):
            SpanSidecar.from_dict(data)

    def test_wrong_type_doc_id_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        data["doc_id"] = 42

        with pytest.raises(ValueError, match="doc_id"):
            SpanSidecar.from_dict(data)

    def test_wrong_type_version_id_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        data["version_id"] = []

        with pytest.raises(ValueError, match="version_id"):
            SpanSidecar.from_dict(data)

    def test_spans_not_list_raises_value_error_naming_field(self) -> None:
        data = _valid_sidecar_dict()
        data["spans"] = "not-a-list"

        with pytest.raises(ValueError, match="spans"):
            SpanSidecar.from_dict(data)

    def test_wrong_type_heading_path_not_list_raises_value_error(self) -> None:
        data = _valid_span_dict()
        data["heading_path"] = ("Introduction", "Scope")  # tuple instead of list

        with pytest.raises(ValueError, match="heading_path"):
            SpanRecord.from_dict(data)

    def test_wrong_type_page_no_bool_raises_value_error(self) -> None:
        data = _valid_span_dict()
        data["page_no"] = True  # bool should be rejected

        with pytest.raises(ValueError, match="page_no"):
            SpanRecord.from_dict(data)

    def test_wrong_type_offset_bool_raises_value_error(self) -> None:
        data = _valid_span_dict()
        data["offset"] = True  # bool should be rejected

        with pytest.raises(ValueError, match="offset"):
            SpanRecord.from_dict(data)

    def test_schema_version_bool_raises_value_error(self) -> None:
        data = _valid_sidecar_dict()
        data["schema_version"] = True  # bool should be rejected

        with pytest.raises(ValueError, match="schema_version"):
            SpanSidecar.from_dict(data)
