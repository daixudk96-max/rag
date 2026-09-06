from __future__ import annotations

import json
import stat
from pathlib import Path
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


def _record_read_size(read_sizes: list[int], size: int) -> bytes:
    read_sizes.append(size)
    return b"x" * size


class TestSpanSidecarResourceLimits:
    """Sidecar loading has bounded reads and non-echoing boundary errors."""

    def test_fstat_oversize_rejects_without_reading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_BYTES", 3)
        monkeypatch.setattr(
            sidecar_module.os,
            "lstat",
            lambda _: type(
                "S", (), {"st_mode": stat.S_IFREG, "st_dev": 1, "st_ino": 2}
            )(),
        )
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(
            sidecar_module.os,
            "fstat",
            lambda _: type("S", (), {"st_mode": stat.S_IFREG, "st_size": 4})(),
        )
        monkeypatch.setattr(
            sidecar_module.os, "read", lambda *_: pytest.fail("no read")
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert str(exc_info.value) == "sidecar exceeds maximum size"

    def test_growing_file_is_rejected_by_bounded_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        read_sizes: list[int] = []
        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_BYTES", 3)
        monkeypatch.setattr(
            sidecar_module.os,
            "lstat",
            lambda _: type(
                "S", (), {"st_mode": stat.S_IFREG, "st_dev": 1, "st_ino": 2}
            )(),
        )
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(
            sidecar_module.os,
            "fstat",
            lambda _: type(
                "S",
                (),
                {"st_mode": stat.S_IFREG, "st_size": 0, "st_dev": 1, "st_ino": 2},
            )(),
        )
        monkeypatch.setattr(
            sidecar_module.os,
            "read",
            lambda _, size: _record_read_size(read_sizes, size),
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert str(exc_info.value) == "sidecar exceeds maximum size"
        assert read_sizes == [4]

    def test_exact_byte_limit_is_accepted(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "sidecar.json"
        path.write_bytes(b"{}")
        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_BYTES", 2)

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)

        assert str(exc_info.value) == "spans is required"

    @pytest.mark.parametrize(
        ("payload", "expected_message"),
        (
            (b"\xff", "sidecar must be valid UTF-8"),
            (b"{bad", "sidecar contains invalid JSON"),
            (b"[]", "sidecar root must be a JSON object"),
        ),
    )
    def test_load_rejects_invalid_payloads_without_details(
        self, tmp_path, payload: bytes, expected_message: str
    ) -> None:
        path = tmp_path / "canary-sidecar.json"
        path.write_bytes(payload)

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)

        assert str(exc_info.value) == expected_message
        assert str(path) not in str(exc_info.value)

    def test_depth_limit_ignores_braces_and_escaped_quotes_inside_strings(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "depth.json"
        path.write_text('{"text":"{[\\"\\\\]}"}', encoding="utf-8")
        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_JSON_DEPTH", 1)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)
        assert str(exc_info.value) == "sidecar contains unknown field"

        path.write_text("[" * 65 + "0" + "]" * 65, encoding="utf-8")
        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_JSON_DEPTH", 64)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)
        assert str(exc_info.value) == "sidecar JSON exceeds maximum depth"

    def test_from_dict_enforces_span_and_payload_budgets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_SPAN_COUNT", 1)
        data = _valid_sidecar_dict()
        data["spans"] = [_valid_span_dict(), _valid_span_dict()]
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.from_dict(data)
        assert str(exc_info.value) == "sidecar exceeds maximum span count"

        monkeypatch.setattr(sidecar_module, "MAX_SPAN_TEXT_BYTES", 3)
        data = _valid_sidecar_dict()
        data["spans"] = [{**_valid_span_dict(), "text": "éé"}]
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.from_dict(data)
        assert str(exc_info.value) == "span text exceeds maximum size"

        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENTS", 1)
        data = _valid_sidecar_dict()
        data["spans"] = [{**_valid_span_dict(), "heading_path": ["one", "two"]}]
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.from_dict(data)
        assert str(exc_info.value) == "heading_path exceeds maximum segment count"

        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENT_BYTES", 3)
        data = _valid_sidecar_dict()
        data["spans"] = [{**_valid_span_dict(), "heading_path": ["éé"]}]
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.from_dict(data)
        assert str(exc_info.value) == "heading_path segment exceeds maximum size"

    def test_open_and_read_errors_are_sanitized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(
            sidecar_module.os,
            "open",
            lambda *_: (_ for _ in ()).throw(OSError("canary-secret-path")),
        )
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert str(exc_info.value) == "sidecar cannot be read"
        assert exc_info.value.__cause__ is None
        assert "canary-secret-path" not in str(exc_info.value)

        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(
            sidecar_module.os,
            "fstat",
            lambda _: type(
                "S",
                (),
                {"st_mode": stat.S_IFREG, "st_size": 0, "st_dev": 1, "st_ino": 2},
            )(),
        )
        monkeypatch.setattr(
            sidecar_module.os,
            "read",
            lambda *_: (_ for _ in ()).throw(OSError("canary-secret-read")),
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert str(exc_info.value) == "sidecar cannot be read"
        assert exc_info.value.__cause__ is None
        assert "canary-secret-read" not in str(exc_info.value)

    def test_invalid_uuid_error_does_not_echo_canary_and_dump_load_at_boundaries(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_SPAN_TEXT_BYTES", 4)
        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENTS", 1)
        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENT_BYTES", 4)
        sidecar = SpanSidecar(
            schema_version=1,
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            spans=(
                SpanRecord(
                    span_id=str(uuid4()),
                    page_no=None,
                    heading_path=("éé",),
                    offset=0,
                    text="éé",
                ),
            ),
        )
        path = tmp_path / "boundary.json"
        sidecar.dump(path)
        assert SpanSidecar.load(path) == sidecar

        data = _valid_sidecar_dict()
        data["doc_id"] = "canary-invalid-uuid"
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.from_dict(data)
        assert "canary-invalid-uuid" not in str(exc_info.value)


class TestSidecarConstructorAndDumpInvariants:
    """Public construction and serialization cannot produce unloadable artifacts."""

    def test_span_record_constructor_enforces_utf8_payload_budgets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_SPAN_TEXT_BYTES", 3)
        with pytest.raises(ValueError, match="span text exceeds maximum size"):
            SpanRecord(**cast(Any, {**_valid_span_values(), "text": "éé"}))

        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENTS", 1)
        with pytest.raises(
            ValueError, match="heading_path exceeds maximum segment count"
        ):
            SpanRecord(
                **cast(Any, {**_valid_span_values(), "heading_path": ("one", "two")})
            )

        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENT_BYTES", 3)
        with pytest.raises(
            ValueError, match="heading_path segment exceeds maximum size"
        ):
            SpanRecord(**cast(Any, {**_valid_span_values(), "heading_path": ("éé",)}))

    def test_sidecar_constructor_enforces_span_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_SPAN_COUNT", 1)
        values = _valid_sidecar_values()
        values["spans"] = (
            SpanRecord(**_valid_span_values()),
            SpanRecord(**_valid_span_values()),
        )

        with pytest.raises(ValueError, match="sidecar exceeds maximum span count"):
            SpanSidecar(**cast(Any, values))

    def test_dump_rejects_serialized_output_above_total_byte_limit(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        sidecar = _sidecar()
        expected = json.dumps(sidecar.to_dict(), ensure_ascii=False, indent=2) + "\n"
        monkeypatch.setattr(
            sidecar_module, "MAX_SIDECAR_BYTES", len(expected.encode()) - 1
        )
        path = tmp_path / "too-large.json"

        with pytest.raises(ValueError) as exc_info:
            sidecar.dump(path)

        assert str(exc_info.value) == "sidecar exceeds maximum size"
        assert not path.exists()

    def test_dump_accepts_serialized_output_at_exact_total_byte_limit(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        sidecar = _sidecar()
        expected = json.dumps(sidecar.to_dict(), ensure_ascii=False, indent=2) + "\n"
        monkeypatch.setattr(sidecar_module, "MAX_SIDECAR_BYTES", len(expected.encode()))
        path = tmp_path / "exact-limit.json"

        sidecar.dump(path)

        assert path.read_bytes() == expected.encode()
        assert SpanSidecar.load(path) == sidecar

    def test_unpaired_surrogates_are_rejected_with_fixed_messages(self) -> None:
        with pytest.raises(ValueError) as text_error:
            SpanRecord(**cast(Any, {**_valid_span_values(), "text": "\ud800canary"}))
        assert str(text_error.value) == "span text must be valid UTF-8"
        assert text_error.value.__cause__ is None

        with pytest.raises(ValueError) as heading_error:
            SpanRecord(
                **cast(Any, {**_valid_span_values(), "heading_path": ("\ud800canary",)})
            )
        assert str(heading_error.value) == "heading_path segment must be valid UTF-8"
        assert heading_error.value.__cause__ is None

    def test_load_rejects_json_unpaired_surrogate_with_fixed_message(
        self, tmp_path
    ) -> None:
        payload = _valid_sidecar_dict()
        payload["spans"] = [{**_valid_span_dict(), "text": "\ud800canary"}]
        path = tmp_path / "unpaired.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)

        assert str(exc_info.value) == "span text must be valid UTF-8"
        assert exc_info.value.__cause__ is None
        assert "canary" not in str(exc_info.value)

    @pytest.mark.parametrize(
        "payload_value",
        ("😀", r"literal \ud800"),
    )
    def test_load_accepts_paired_and_literal_backslash_unicode_sequences(
        self, tmp_path, payload_value: str
    ) -> None:
        payload = _valid_sidecar_dict()
        payload["spans"] = [{**_valid_span_dict(), "text": payload_value}]
        path = tmp_path / "valid-unicode.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        loaded = SpanSidecar.load(path)

        assert loaded.spans[0].text == payload_value

    def test_boundary_parse_errors_have_no_cause_or_sensitive_details(
        self, tmp_path
    ) -> None:
        path = tmp_path / "canary-parse.json"
        for payload, expected in (
            (b"\xff", "sidecar must be valid UTF-8"),
            (b"{canary", "sidecar contains invalid JSON"),
        ):
            path.write_bytes(payload)
            with pytest.raises(ValueError) as exc_info:
                SpanSidecar.load(path)
            assert str(exc_info.value) == expected
            assert exc_info.value.__cause__ is None
            assert str(path) not in str(exc_info.value)
            assert "canary" not in str(exc_info.value)

    def test_read_and_fstat_errors_have_no_cause_or_sensitive_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(
            sidecar_module.os,
            "fstat",
            lambda _: (_ for _ in ()).throw(OSError("canary-fstat")),
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert str(exc_info.value) == "sidecar cannot be read"
        assert exc_info.value.__cause__ is None
        assert "canary" not in str(exc_info.value)
