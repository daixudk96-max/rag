from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._sidecar_testkit import _sidecar


def _record_short_read(read_sizes: list[int], size: int, chunks: Any) -> bytes:
    read_sizes.append(size)
    return next(chunks)


class TestSidecarReviewBlockerRegressions:
    def test_dumped_60_mib_text_payload_loads_within_file_contract(
        self, tmp_path
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        text = "x" * sidecar_module.MAX_SPAN_TEXT_BYTES
        sidecar = SpanSidecar(
            schema_version=1,
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            spans=tuple(
                SpanRecord(str(uuid4()), None, (), index, text) for index in range(60)
            ),
        )
        path = tmp_path / "60-mib.json"

        sidecar.dump(path)

        assert path.stat().st_size == 62_924_061
        assert path.stat().st_size < sidecar_module.MAX_SIDECAR_BYTES
        assert SpanSidecar.load(path) == sidecar

    def test_bounded_read_collects_short_reads_until_eof(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        metadata = type(
            "S", (), {"st_mode": stat.S_IFREG, "st_size": 7, "st_dev": 1, "st_ino": 2}
        )()
        chunks = iter((b"{", b"}", b""))
        read_sizes: list[int] = []
        monkeypatch.setattr(sidecar_module.os, "lstat", lambda _: metadata)
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(sidecar_module.os, "fstat", lambda _: metadata)
        monkeypatch.setattr(
            sidecar_module.os,
            "read",
            lambda _, size: _record_short_read(read_sizes, size, chunks),
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)

        assert sidecar_module._read_sidecar_bytes_bounded(Path("sidecar.json")) == b"{}"
        assert len(read_sizes) == 3
        assert all(size <= sidecar_module.MAX_SIDECAR_BYTES + 1 for size in read_sizes)

    def test_replaced_path_after_lstat_is_rejected_before_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        initial = type(
            "S", (), {"st_mode": stat.S_IFREG, "st_size": 2, "st_dev": 1, "st_ino": 2}
        )()
        replacement = type(
            "S", (), {"st_mode": stat.S_IFREG, "st_size": 2, "st_dev": 1, "st_ino": 3}
        )()
        monkeypatch.setattr(sidecar_module.os, "lstat", lambda _: initial)
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(sidecar_module.os, "fstat", lambda _: replacement)
        monkeypatch.setattr(
            sidecar_module.os,
            "read",
            lambda *_: pytest.fail("must not read replacement"),
        )
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)

        with pytest.raises(ValueError, match="sidecar cannot be read") as exc_info:
            SpanSidecar.load(Path("sidecar.json"))
        assert exc_info.value.__cause__ is None

    def test_same_lstat_and_fd_identity_continues_to_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        metadata = type(
            "S", (), {"st_mode": stat.S_IFREG, "st_size": 2, "st_dev": 1, "st_ino": 2}
        )()
        monkeypatch.setattr(sidecar_module.os, "lstat", lambda _: metadata)
        monkeypatch.setattr(sidecar_module.os, "open", lambda *_: 7)
        monkeypatch.setattr(sidecar_module.os, "fstat", lambda _: metadata)
        chunks = iter((b"{}", b""))
        monkeypatch.setattr(sidecar_module.os, "read", lambda *_: next(chunks))
        monkeypatch.setattr(sidecar_module.os, "close", lambda _: None)

        with pytest.raises(ValueError, match="spans is required"):
            SpanSidecar.load(Path("sidecar.json"))

    def test_escaped_key_decoding_does_not_use_full_payload_json_loads(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "escaped-key.json"
        path.write_text(
            '{"\\u0073chema_version":1,"doc_id":"%s","version_id":"%s","spans":[]}'
            % (uuid4(), uuid4()),
            encoding="utf-8",
        )
        real_loads = sidecar_module.json.loads
        received: list[str] = []

        def guarded_loads(value: str, **kwargs: Any) -> Any:
            received.append(value)
            assert value == path.read_text(encoding="utf-8")
            return real_loads(value, **kwargs)

        monkeypatch.setattr(sidecar_module.json, "loads", guarded_loads)

        assert SpanSidecar.load(path).spans == ()
        assert received == [path.read_text(encoding="utf-8")]


class TestSidecarReviewMediumRegressions:
    @pytest.mark.parametrize(
        ("field_payload", "expected_message"),
        (
            (
                lambda: '"text":"' + "x" * (1024 * 1024 + 1) + '"',
                "span text exceeds maximum size",
            ),
            (
                lambda: '"heading_path":["' + "x" * (64 * 1024 + 1) + '"]',
                "heading_path segment exceeds maximum size",
            ),
        ),
    )
    def test_oversized_decoded_string_rejects_before_full_json_loads(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        field_payload,
        expected_message: str,
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "oversized-string.json"
        path.write_text(
            '{"spans":[{"span_id":"%s","page_no":0,%s,"offset":0%s}]}'
            % (
                uuid4(),
                field_payload(),
                (
                    ',"text":"x"'
                    if "heading_path" in field_payload()
                    else ',"heading_path":[]'
                ),
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            sidecar_module.json,
            "loads",
            lambda *_args, **_kwargs: pytest.fail("json.loads must not be called"),
        )

        with pytest.raises(ValueError) as exc_info:
            SpanSidecar.load(path)

        assert str(exc_info.value) == expected_message
        assert exc_info.value.__cause__ is None

    def test_escaped_text_at_decoded_utf8_limit_loads(self, tmp_path) -> None:
        path = tmp_path / "escaped-limit.json"
        path.write_text(
            '{"schema_version":1,"doc_id":"%s","version_id":"%s","spans":['
            '{"span_id":"%s","page_no":0,"heading_path":[],"offset":0,'
            '"text":"%s"}]}' % (uuid4(), uuid4(), uuid4(), "\\u0061" * (1024 * 1024)),
            encoding="utf-8",
        )

        loaded = SpanSidecar.load(path)

        assert loaded.spans[0].text == "a" * (1024 * 1024)

    def test_fdopen_failure_closes_owned_descriptor_and_cleans_temp(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import sidecar as sidecar_module

        path = tmp_path / "target.json"
        old = b"old target canary"
        path.write_bytes(old)
        created: list[tuple[int, str]] = []
        real_mkstemp = sidecar_module.tempfile.mkstemp

        def tracking_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
            result = real_mkstemp(*args, **kwargs)
            created.append(result)
            return result

        def fail_fdopen(*_: Any, **__: Any) -> None:
            raise OSError("canary")

        monkeypatch.setattr(sidecar_module.tempfile, "mkstemp", tracking_mkstemp)
        monkeypatch.setattr(sidecar_module.os, "fdopen", fail_fdopen)

        with pytest.raises(ValueError) as exc_info:
            _sidecar().dump(path)

        descriptor, temporary_name = created.pop()
        assert str(exc_info.value) == "sidecar cannot be written"
        assert exc_info.value.__cause__ is None
        assert path.read_bytes() == old
        assert not Path(temporary_name).exists()
        with pytest.raises(OSError) as descriptor_error:
            os.fstat(descriptor)
        assert descriptor_error.value.errno == getattr(os, "EBADF", 9)
