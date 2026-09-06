from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._sidecar_testkit import (
    _sidecar,
    _valid_sidecar_dict,
    _valid_span_dict,
    _valid_span_values,
)


class TestSidecarPhase14Boundaries:
    """Pre-parse resource checks and atomic dump behavior are observable contracts."""

    def test_unknown_numeric_array_is_rejected_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "numeric-array.json"
        path.write_bytes(b'{"unknown":[' + b"0," * (4 * 1024 * 1024) + b"0]}")
        monkeypatch.setattr(
            sidecar_module.json,
            "loads",
            lambda _: pytest.fail("json.loads must not materialize numeric array"),
        )
        with pytest.raises(ValueError, match="unknown field"):
            SpanSidecar.load(path)

    def test_unknown_root_and_span_fields_are_rejected(self) -> None:
        root = _valid_sidecar_dict()
        root["unexpected_root"] = "canary"
        with pytest.raises(ValueError, match="unknown field") as exc_info:
            SpanSidecar.from_dict(root)
        assert "canary" not in str(exc_info.value)

        span = _valid_span_dict()
        span["unexpected_span"] = "canary"
        with pytest.raises(ValueError, match="unknown field") as exc_info:
            SpanRecord.from_dict(span)
        assert "canary" not in str(exc_info.value)

    @pytest.mark.parametrize("suffix", (b',"doc_id":"duplicate"}', b',"spans":[]}'))
    def test_duplicate_keys_are_rejected(self, tmp_path, suffix: bytes) -> None:
        path = tmp_path / "duplicate.json"
        base = (
            b'{"schema_version":1,"doc_id":"'
            + str(uuid4()).encode()
            + b'","version_id":"'
            + str(uuid4()).encode()
            + b'","spans":[]'
        )
        path.write_bytes(base + suffix)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)
        assert str(exc_info.value) == "sidecar contains duplicate JSON key"
        assert exc_info.value.__cause__ is None

    def test_duplicate_span_key_is_rejected(self, tmp_path) -> None:
        path = tmp_path / "duplicate-span.json"
        identifier = str(uuid4()).encode()
        path.write_bytes(
            b'{"schema_version":1,"doc_id":"'
            + str(uuid4()).encode()
            + b'","version_id":"'
            + str(uuid4()).encode()
            + b'","spans":[{"span_id":"'
            + identifier
            + b'","span_id":"'
            + identifier
            + b'","page_no":0,"heading_path":[],"offset":0,"text":"x"}]}'
        )
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)
        assert str(exc_info.value) == "sidecar contains duplicate JSON key"
        assert exc_info.value.__cause__ is None

    @pytest.mark.parametrize("constant", (b"NaN", b"Infinity", b"-Infinity"))
    def test_non_json_constants_are_rejected(self, tmp_path, constant: bytes) -> None:
        path = tmp_path / "constant.json"
        path.write_bytes(b'{"schema_version":' + constant + b"}")
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)
        assert str(exc_info.value) == "sidecar contains invalid JSON"
        assert exc_info.value.__cause__ is None

    def test_huge_number_and_span_count_reject_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "huge-number.json"
        path.write_bytes(b'{"unknown":' + b"9" * 65 + b"}")
        monkeypatch.setattr(
            sidecar_module.json,
            "loads",
            lambda *_args, **_kwargs: pytest.fail(
                "json.loads must not receive huge number"
            ),
        )
        with pytest.raises(ValueError, match="unknown field"):
            SpanSidecar.load(path)

        span = (
            b'{"span_id":"00000000-0000-0000-0000-000000000000",'
            b'"page_no":0,"heading_path":[],"offset":0,"text":"x"}'
        )
        path.write_bytes(b'{"spans":[' + b",".join([span] * 100_001) + b"]}")
        with pytest.raises(ValueError, match="maximum span count"):
            SpanSidecar.load(path)

    def test_heading_aggregate_rejects_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(sidecar_module, "MAX_HEADING_SEGMENTS", 100_000)
        path = tmp_path / "headings.json"
        span = (
            b'{"span_id":"00000000-0000-0000-0000-000000000000",'
            b'"page_no":0,"heading_path":['
            + b",".join([b'"x"'] * 64)
            + b'],"offset":0,"text":"x"}'
        )
        path.write_bytes(b'{"spans":[' + b",".join([span] * 1_563) + b"]}")
        monkeypatch.setattr(
            sidecar_module.json,
            "loads",
            lambda *_args, **_kwargs: pytest.fail(
                "json.loads must not materialize headings"
            ),
        )
        with pytest.raises(ValueError, match="maximum segment count"):
            SpanSidecar.load(path)

    def test_strings_with_escapes_do_not_count_structural_characters(
        self, tmp_path
    ) -> None:
        path = tmp_path / "escaped.json"
        payload = _valid_sidecar_dict()
        payload["spans"] = [
            {
                **_valid_span_dict(),
                "text": '{[,,]}\\\\\\" and \\u2603',
                "heading_path": ['{[\\"\\\\]}'],
            }
        ]
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert SpanSidecar.load(path).spans[0].text == '{[,,]}\\\\\\" and \\u2603'

    def test_non_regular_descriptor_is_rejected_before_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(
            sidecar_module.os,
            "lstat",
            lambda _: type(
                "S", (), {"st_mode": stat.S_IFREG, "st_dev": 1, "st_ino": 2}
            )(),
        )
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 42)
        monkeypatch.setattr(
            sidecar_module.os,
            "fstat",
            lambda _: type("S", (), {"st_mode": stat.S_IFIFO, "st_size": 0})(),
        )
        monkeypatch.setattr(
            sidecar_module.os, "read", lambda *_: pytest.fail("no read")
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)
        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(Path("canary-fifo"))
        assert str(exc_info.value) == "sidecar cannot be read"
        assert exc_info.value.__cause__ is None

    def test_dump_uses_exact_oracle_bytes_and_atomic_cleanup(self, tmp_path) -> None:
        sidecar = _sidecar()
        path = tmp_path / "target.json"
        expected = (
            json.dumps(sidecar.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
            + b"\n"
        )
        sidecar.dump(path)
        assert path.read_bytes() == expected
        assert not list(tmp_path.glob(".target.json.*.tmp"))

    @pytest.mark.parametrize("failure", ("write", "fsync", "replace"))
    def test_dump_failure_preserves_target_and_cleans_temp(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, failure: str
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "target.json"
        old = b"old target canary"
        path.write_bytes(old)

        def fail(*_: object) -> None:
            raise OSError("canary")

        if failure == "write":
            monkeypatch.setattr(sidecar_module, "_write_all", fail)
        elif failure == "fsync":
            monkeypatch.setattr(sidecar_module.os, "fsync", fail)
        else:
            monkeypatch.setattr(sidecar_module.os, "replace", fail)
        with pytest.raises(ValueError) as exc_info:
            _sidecar().dump(path)
        assert str(exc_info.value) == "sidecar cannot be written"
        assert exc_info.value.__cause__ is None
        assert "canary" not in str(exc_info.value)
        assert path.read_bytes() == old
        assert not list(tmp_path.glob(".target.json.*.tmp"))

    def test_invalid_uuid_has_no_cause(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            SpanRecord(**cast(Any, {**_valid_span_values(), "span_id": "not-a-uuid"}))
        assert exc_info.value.__cause__ is None


class TestSidecarSchemaAwarePreflight:
    """Invalid schemas fail before ``json.loads`` allocates their containers."""

    @staticmethod
    def _forbid_json_loads(monkeypatch: pytest.MonkeyPatch) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(
            sidecar_module.json,
            "loads",
            lambda *_args, **_kwargs: pytest.fail("json.loads must not be called"),
        )

    def test_unknown_root_large_numeric_array_rejects_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "unknown-large.json"
        payload = b'{"unknown":[' + b"12345," * 1_000_000 + b"12345]}"
        assert len(payload) > 6_000_000
        path.write_bytes(payload)
        self._forbid_json_loads(monkeypatch)

        with pytest.raises(ValueError, match="unknown field"):
            SpanSidecar.load(path)

    def test_unknown_span_large_array_rejects_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "unknown-span-large.json"
        path.write_bytes(b'{"spans":[{"unknown":[' + b"12345," * 1_000_000 + b"0]}]}")
        self._forbid_json_loads(monkeypatch)

        with pytest.raises(ValueError, match="unknown field"):
            SpanSidecar.load(path)

    @pytest.mark.parametrize(
        ("payload", "expected_message"),
        (
            pytest.param(
                b'{"spans":[' + b",".join([b"{}"] * 100_000) + b'],"spans":[]}',
                "duplicate JSON key",
                id="root-first-large-container",
            ),
            pytest.param(
                b'{"spans":['
                + b"{}" * 0
                + b'],"spans":['
                + b"12345," * 1_000_000
                + b"0]}",
                "duplicate JSON key",
                id="root-second-large-container",
            ),
            pytest.param(
                b'{"spans":[{"heading_path":["'
                + b"x" * (1024 * 1024)
                + b'"],"heading_path":['
                + b"12345," * 1_000_000
                + b"0]}]}",
                "heading_path segment exceeds maximum size",
                id="span-first-oversized-heading",
            ),
        ),
    )
    def test_first_schema_violation_rejects_before_scanning_later_large_value(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        payload: bytes,
        expected_message: str,
    ) -> None:
        path = tmp_path / "duplicate-large.json"
        path.write_bytes(payload)
        self._forbid_json_loads(monkeypatch)

        with pytest.raises(ValueError, match=expected_message):
            SpanSidecar.load(path)

    @pytest.mark.parametrize(
        "field",
        (
            "doc_id",
            "version_id",
            "schema_version",
            "text",
            "span_id",
            "page_no",
            "offset",
        ),
    )
    @pytest.mark.parametrize("container", ("[]", "{}"))
    def test_scalar_schema_positions_reject_containers_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, field: str, container: str
    ) -> None:
        if field in {"text", "span_id", "page_no", "offset"}:
            payload = f'{{"spans":[{{"{field}":{container}}}]}}'
        else:
            payload = f'{{"{field}":{container}}}'
        path = tmp_path / "scalar-container.json"
        path.write_text(payload, encoding="utf-8")
        self._forbid_json_loads(monkeypatch)

        with pytest.raises(ValueError, match="schema"):
            SpanSidecar.load(path)

    @pytest.mark.parametrize(
        "payload",
        (
            '{"spans":{}}',
            '{"spans":1}',
            '{"spans":[[]]}',
            '{"spans":[1]}',
            '{"spans":[{"heading_path":{}}]}',
            '{"spans":[{"heading_path":1}]}',
            '{"spans":[{"heading_path":[[]]}]}',
            '{"spans":[{"heading_path":[{}]}]}',
            '{"spans":[{"heading_path":[1]}]}',
        ),
    )
    def test_schema_container_shapes_reject_before_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, payload: str
    ) -> None:
        path = tmp_path / "container-shape.json"
        path.write_text(payload, encoding="utf-8")
        self._forbid_json_loads(monkeypatch)

        with pytest.raises(ValueError, match="schema"):
            SpanSidecar.load(path)

    def test_escaped_keys_and_spans_first_preserve_valid_load_semantics(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "escaped-known.json"
        payload = (
            '{"\\u0073pans":[],"version_id":"%s","schema_version":1,"doc_id":"%s"}'
            % (uuid4(), uuid4())
        )
        path.write_text(payload, encoding="utf-8")
        calls = 0
        from llamaindex_runtime.okf import sidecar as sidecar_module

        real_loads = sidecar_module.json.loads

        def counting_loads(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            return real_loads(*args, **kwargs)

        monkeypatch.setattr(sidecar_module.json, "loads", counting_loads)
        assert SpanSidecar.load(path).spans == ()
        assert calls == 1

        path.write_text('{"\\u0075nknown":[]}', encoding="utf-8")
        calls = 0
        with pytest.raises(ValueError, match="unknown field"):
            SpanSidecar.load(path)
        assert calls == 0

    def test_normal_and_malformed_json_keep_json_loads_authority(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "normal.json"
        sidecar = _sidecar()
        path.write_text(json.dumps(sidecar.to_dict()), encoding="utf-8")
        from llamaindex_runtime.okf import sidecar as sidecar_module

        real_loads = sidecar_module.json.loads
        calls = 0

        def counting_loads(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            return real_loads(*args, **kwargs)

        monkeypatch.setattr(sidecar_module.json, "loads", counting_loads)
        assert SpanSidecar.load(path) == sidecar
        path.write_text('{"spans" [}', encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            SpanSidecar.load(path)
        assert calls == 2

    @pytest.mark.parametrize("mode", (stat.S_IFIFO, stat.S_IFLNK))
    def test_lstat_rejects_nonregular_path_before_open(
        self, monkeypatch: pytest.MonkeyPatch, mode: int
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        monkeypatch.setattr(
            sidecar_module.os,
            "lstat",
            lambda _: type("S", (), {"st_mode": mode})(),
        )
        monkeypatch.setattr(
            sidecar_module.os, "open", lambda *_: pytest.fail("must not open FIFO")
        )
        with pytest.raises(ValueError, match="cannot be read"):
            SpanSidecar.load(Path("fifo-sidecar"))

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo unavailable")
    def test_real_fifo_rejects_without_blocking(self, tmp_path) -> None:
        fifo = tmp_path / "sidecar.fifo"
        mkfifo = getattr(os, "mkfifo", None)
        assert mkfifo is not None
        mkfifo(fifo)
        with pytest.raises(ValueError, match="cannot be read"):
            SpanSidecar.load(fifo)
