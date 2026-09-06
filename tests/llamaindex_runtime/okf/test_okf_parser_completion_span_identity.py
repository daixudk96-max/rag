"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._parser_completion_testkit import _make_raw_md_content
from .raw_pair_testkit import refresh_raw_manifest

DuplicateRecordFactory = Callable[[str, str], tuple[SpanRecord, SpanRecord]]


def _slash_joined_heading_collision(_: str, __: str) -> tuple[SpanRecord, SpanRecord]:
    """Build distinct paths that collide under slash-delimited identity input."""
    return (
        SpanRecord(str(uuid4()), 1, ("A/B",), 0, "safe text"),
        SpanRecord(str(uuid4()), 1, ("A", "B"), 0, "safe text"),
    )


def _pipe_cross_field_collision(_: str, __: str) -> tuple[SpanRecord, SpanRecord]:
    """Build distinct coordinates that collide at the field delimiter boundary."""
    return (
        SpanRecord(str(uuid4()), 1, ("h|2",), 3, "x"),
        SpanRecord(str(uuid4()), 1, ("h",), 2, "3|x"),
    )


DUPLICATE_RECOMPUTED_RECORD_FACTORIES: tuple[DuplicateRecordFactory, ...] = (
    _slash_joined_heading_collision,
    _pipe_cross_field_collision,
)


class TestParserSpanIdentityAdmission:
    """Raw sidecars must carry unique, coordinate-derived identities."""

    @staticmethod
    def _frontmatter(doc_id: str, version_id: str) -> dict[str, str]:
        return {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }

    def _write_raw(
        self,
        root: Path,
        name: str,
        records: tuple[SpanRecord, ...],
        *,
        doc_id: str | None = None,
        version_id: str | None = None,
    ) -> tuple[Path, str, str]:
        resolved_doc_id = doc_id or str(uuid4())
        resolved_version_id = version_id or str(uuid4())
        path = root / "raw" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _make_raw_md_content(
                self._frontmatter(resolved_doc_id, resolved_version_id)
            ),
            encoding="utf-8",
        )
        SpanSidecar(
            schema_version=1,
            doc_id=resolved_doc_id,
            version_id=resolved_version_id,
            spans=records,
        ).dump(path.with_suffix(".spans.json"))
        refresh_raw_manifest(path)
        return path, resolved_doc_id, resolved_version_id

    @staticmethod
    def _canonical_record(
        *,
        doc_id: str,
        version_id: str,
        page_no: int = 1,
        heading_path: tuple[str, ...] = (),
        offset: int = 0,
        text: str = "safe text",
    ) -> SpanRecord:
        provisional = SpanRecord(
            span_id="00000000-0000-0000-0000-000000000000",
            page_no=page_no,
            heading_path=heading_path,
            offset=offset,
            text=text,
        )
        return SpanRecord(
            span_id=recompute_span_id(
                provisional, doc_id=doc_id, version_id=version_id
            ),
            page_no=page_no,
            heading_path=heading_path,
            offset=offset,
            text=text,
        )

    def test_valid_sidecar_parses_with_original_order_and_ids(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        records = (
            self._canonical_record(doc_id=doc_id, version_id=version_id, text="first"),
            self._canonical_record(
                doc_id=doc_id, version_id=version_id, offset=5, text="second"
            ),
        )
        path, _, _ = self._write_raw(
            tmp_path, "valid", records, doc_id=doc_id, version_id=version_id
        )

        parsed = OKFParser().parse_document(path, tmp_path)

        assert parsed.spans == records
        assert [span.span_id for span in parsed.spans] == [
            span.span_id for span in records
        ]

    def test_parse_rejects_persisted_id_mismatch_without_sensitive_details(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        canonical = self._canonical_record(
            doc_id=doc_id,
            version_id=version_id,
            heading_path=("canary heading",),
            text="canary text",
        )
        wrong_id = "00000000-0000-0000-0000-000000000099"
        path, _, _ = self._write_raw(
            tmp_path,
            "canary-path",
            (
                SpanRecord(
                    wrong_id,
                    canonical.page_no,
                    canonical.heading_path,
                    canonical.offset,
                    canonical.text,
                ),
            ),
            doc_id=doc_id,
            version_id=version_id,
        )

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(path, tmp_path)

        assert (
            str(exc_info.value)
            == "sidecar span identity does not match canonical coordinates"
        )
        for secret in (
            "canary text",
            "canary heading",
            wrong_id,
            canonical.span_id,
            str(path),
            str(tmp_path),
        ):
            assert secret not in str(exc_info.value)

    def test_parse_rejects_duplicate_persisted_identity(self, tmp_path: Path) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        first = self._canonical_record(
            doc_id=doc_id, version_id=version_id, text="first"
        )
        second = self._canonical_record(
            doc_id=doc_id, version_id=version_id, offset=1, text="second"
        )
        path, _, _ = self._write_raw(
            tmp_path,
            "duplicate-persisted",
            (
                first,
                SpanRecord(
                    first.span_id,
                    second.page_no,
                    second.heading_path,
                    second.offset,
                    second.text,
                ),
            ),
            doc_id=doc_id,
            version_id=version_id,
        )

        with pytest.raises(
            ValueError, match="^sidecar contains duplicate persisted span identity$"
        ):
            OKFParser().parse_document(path, tmp_path)

    @pytest.mark.parametrize(
        "records_factory",
        DUPLICATE_RECOMPUTED_RECORD_FACTORIES,
        ids=("slash-joined-heading", "pipe-cross-field"),
    )
    def test_parse_rejects_distinct_coordinates_with_duplicate_recomputed_identity(
        self, tmp_path: Path, records_factory: DuplicateRecordFactory
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        records = records_factory(doc_id, version_id)
        assert records[0].to_dict() != records[1].to_dict()
        assert recompute_span_id(
            records[0], doc_id=doc_id, version_id=version_id
        ) == recompute_span_id(records[1], doc_id=doc_id, version_id=version_id)
        path, _, _ = self._write_raw(
            tmp_path,
            "duplicate-recomputed",
            records,
            doc_id=doc_id,
            version_id=version_id,
        )

        with pytest.raises(
            ValueError, match="^sidecar contains duplicate recomputed span identity$"
        ):
            OKFParser().parse_document(path, tmp_path)

    def test_parse_rejects_identical_record_duplicate_without_deduping(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        record = self._canonical_record(doc_id=doc_id, version_id=version_id)
        path, _, _ = self._write_raw(
            tmp_path,
            "identical-duplicate",
            (record, record),
            doc_id=doc_id,
            version_id=version_id,
        )

        with pytest.raises(
            ValueError, match="^sidecar contains duplicate persisted span identity$"
        ):
            OKFParser().parse_document(path, tmp_path)

    @pytest.mark.parametrize(
        "records_factory, expected",
        [
            (
                lambda self, doc_id, version_id: (
                    self._canonical_record(doc_id=doc_id, version_id=version_id),
                    SpanRecord(
                        "00000000-0000-0000-0000-000000000099", 2, (), 1, "other"
                    ),
                    SpanRecord(
                        "00000000-0000-0000-0000-000000000099", 3, (), 2, "third"
                    ),
                ),
                "sidecar contains duplicate persisted span identity",
            ),
            (
                lambda self, doc_id, version_id: (
                    SpanRecord(
                        "00000000-0000-0000-0000-000000000098",
                        1,
                        ("A/B",),
                        0,
                        "safe text",
                    ),
                    self._canonical_record(
                        doc_id=doc_id, version_id=version_id, heading_path=("A", "B")
                    ),
                ),
                "sidecar contains duplicate recomputed span identity",
            ),
        ],
        ids=("persisted-before-recomputed-and-mismatch", "recomputed-before-mismatch"),
    )
    def test_admission_error_priority_is_deterministic(
        self, tmp_path: Path, records_factory: Any, expected: str
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        records = records_factory(self, doc_id, version_id)
        path, _, _ = self._write_raw(
            tmp_path, "priority", records, doc_id=doc_id, version_id=version_id
        )

        with pytest.raises(ValueError, match=f"^{expected}$"):
            OKFParser().parse_document(path, tmp_path)

    def test_bundle_skips_invalid_raw_identity_and_keeps_valid_documents(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id, version_id = str(uuid4()), str(uuid4())
        valid = self._canonical_record(doc_id=doc_id, version_id=version_id)
        self._write_raw(
            tmp_path, "valid", (valid,), doc_id=doc_id, version_id=version_id
        )
        bad_doc_id, bad_version_id = str(uuid4()), str(uuid4())
        bad = self._canonical_record(doc_id=bad_doc_id, version_id=bad_version_id)
        self._write_raw(
            tmp_path,
            "bad",
            (
                SpanRecord(
                    "00000000-0000-0000-0000-000000000097",
                    bad.page_no,
                    bad.heading_path,
                    bad.offset,
                    bad.text,
                ),
            ),
            doc_id=bad_doc_id,
            version_id=bad_version_id,
        )

        result = OKFParser().parse_bundle(tmp_path)

        assert [document.file_path.name for document in result] == ["valid.md"]
        assert (result.stats.parsed, result.stats.skipped, result.stats.malformed) == (
            1,
            1,
            1,
        )
