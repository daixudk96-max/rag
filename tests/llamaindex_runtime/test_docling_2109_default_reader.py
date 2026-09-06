"""Production-path tests for Docling 2.109 HeadingHierarchyModel integration.

These tests are the strict RED->GREEN gate for Phase 14 Task #32 gap #1.

CRITICAL: these tests do NOT duplicate the reader/pipeline configuration. They
import and directly call the PRODUCTION entry points:

    - ``llamaindex_runtime.ingestion.docling_ingestor._build_default_reader``
    - ``llamaindex_runtime.ingestion.docling_ingestor.DoclingIngestor``

Span_id computation uses the EXACT production chain
(``DoclingIngestor._flatten_docling_metadata`` + ``NormalizationContract.normalize``
+ ``uuid5``), never a simplified ordinal-offset reimplementation.

Isolated environment requirement
---------------------------------
These tests exercise the real Docling PDF pipeline and therefore require
``docling==2.109.0``. Run them with the isolated venv::

    C:/Users/daixu/AppData/Local/Temp/docling-hierarchy-verify-2109/venv/Scripts/python.exe \\
      -m pytest tests/llamaindex_runtime/test_docling_2109_default_reader.py -q
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

# Ensure the worktree root is importable when this file is run directly from
# the isolated venv (which does not see the repo conftest.py path injection).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from llamaindex_runtime.ingestion.docling_ingestor import (  # noqa: E402
    DoclingIngestor,
    _build_default_reader,
)
from llamaindex_runtime.ingestion.normalization import (  # noqa: E402
    NormalizationContract,
)

# Fixed deterministic UUIDs shared with the fixture generator.
DOC_ID = UUID("00000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000003")


# ---------------------------------------------------------------------------
# PDF fixture authoring: BaseDocTemplate + afterFlowable so each heading
# bookmark/destination attaches when that heading actually flows. Bookmarks
# are NOT created in onFirstPage.
# ---------------------------------------------------------------------------


def _build_sectioned_doc_template(buffer: BytesIO) -> Any:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

    class SectionedDocTemplate(BaseDocTemplate):
        """BaseDocTemplate that bookmarks each heading as it flows."""

        def __init__(self, buffer: BytesIO) -> None:
            super().__init__(buffer, pagesize=letter)
            frame = Frame(
                self.leftMargin, self.bottomMargin, self.width, self.height, id="normal"
            )
            self.addPageTemplates([PageTemplate(id="main", frames=[frame])])
            self._outline_level: dict[str, int] = {
                "h1": 0,
                "h2": 1,
                "h3": 2,
            }
            self._bookmark_counter = 0

        def afterFlowable(self, flowable: object) -> None:
            """Attach bookmark + outline entry when a heading flowable is laid out."""
            style_name = getattr(getattr(flowable, "style", None), "name", "")
            if style_name not in self._outline_level:
                return
            text = getattr(flowable, "getPlainText", lambda: "")()
            if not text:
                return
            self._bookmark_counter += 1
            key = f"heading-{self._bookmark_counter}"
            # bookmarkPage attaches the named destination at the CURRENT flow
            # position (where this heading actually landed), not on page 1.
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=self._outline_level[style_name])

    return SectionedDocTemplate(buffer)


def _sectioned_pdf_story() -> list[object]:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10)
    return [
        Paragraph("Introduction to Machine Learning", h1),
        Paragraph("Overview of ML fundamentals.", body),
        Paragraph("Chapter 1: Foundations", h2),
        Paragraph("Machine learning is a subset of AI.", body),
        Paragraph("1.1 Supervised Learning", h3),
        Paragraph("Uses labeled training data.", body),
        Paragraph("1.2 Unsupervised Learning", h3),
        Paragraph("Discovers patterns in data.", body),
    ]


def _make_sectioned_pdf_bytes() -> bytes:
    """Author a multi-level sectioned PDF with afterFlowable bookmarks.

    Uses a BaseDocTemplate subclass whose ``afterFlowable`` hook attaches a
    named destination + outline entry at the current flow position whenever a
    heading paragraph is laid out. This is the user-approved authoring pattern
    (gap #2): bookmarks attach when each heading actually flows, not all at
    once in ``onFirstPage``.
    """
    buffer = BytesIO()
    doc = _build_sectioned_doc_template(buffer)
    doc.build(_sectioned_pdf_story())
    return buffer.getvalue()


@pytest.fixture
def sectioned_pdf(tmp_path: Path) -> Path:
    pdf_bytes = _make_sectioned_pdf_bytes()
    pdf_path = tmp_path / "sectioned.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


# ---------------------------------------------------------------------------
# Helpers that reuse the EXACT production span computation.
# ---------------------------------------------------------------------------


def _production_span_records(
    nodes: list[object], doc_id: UUID, version_id: UUID
) -> list[dict]:
    """Recompute span records using the EXACT DoclingIngestor chain.

    This mirrors ``DoclingIngestor._build_span`` / ``DoclingIngestor.ingest``
    exactly: ``_flatten_docling_metadata`` + ``NormalizationContract.normalize``
    + ``uuid5``. It is NOT a simplified ordinal-offset approximation.
    """
    contract = NormalizationContract()
    records: list[dict] = []
    for ordinal, node in enumerate(nodes):
        raw_text = DoclingIngestor._extract_text(node)
        if not raw_text.strip():
            continue
        metadata = dict(getattr(node, "metadata", {}) or {})
        flat_metadata = DoclingIngestor._flatten_docling_metadata(metadata)
        normalized = contract.normalize(
            raw_text=raw_text, metadata=flat_metadata, ordinal=ordinal
        )
        span_id = uuid5(
            NAMESPACE_URL,
            f"{doc_id}|{version_id}|{normalized.page_no}|"
            f"{'/'.join(normalized.headings)}|{normalized.offset}|{normalized.text}",
        )
        records.append(
            {
                "span_id": str(span_id),
                "page_no": normalized.page_no,
                "headings": list(normalized.headings),
                "offset": normalized.offset,
                "text": normalized.text,
            }
        )
    return records


def _legacy_flat_reader() -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        HeadingHierarchyOptions,
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from llama_index.readers.docling import DoclingReader

    flat_hho = HeadingHierarchyOptions(enabled=False)
    flat_pipeline = PdfPipelineOptions(heading_hierarchy_options=flat_hho)
    flat_format = PdfFormatOption(pipeline_options=flat_pipeline)
    flat_converter = DocumentConverter(format_options={InputFormat.PDF: flat_format})
    return DoclingReader(export_type="json", doc_converter=flat_converter)


def _reader_nodes(reader: Any, node_parser: Any, sectioned_pdf: Path) -> list[object]:
    documents = reader.load_data(file_path=str(sectioned_pdf))
    return list(node_parser.get_nodes_from_documents(documents))


def _assert_distinct_span_id_sets(
    flat_records: list[dict], prod_records: list[dict]
) -> None:
    # The span_id sets MUST differ: enabling HeadingHierarchyModel changes
    # heading_path, which changes span_id. This is the intentional
    # migration boundary.
    flat_ids = {r["span_id"] for r in flat_records}
    prod_ids = {r["span_id"] for r in prod_records}
    assert flat_ids != prod_ids, (
        "Flat (legacy) and hierarchy (production default) readers MUST "
        "produce different span_id sets: heading_path differs, which is "
        "the intentional migration boundary."
    )


def _aligned_records(
    flat_records: list[dict], prod_records: list[dict]
) -> list[tuple[dict, dict]]:
    flat_by_coord = {(r["page_no"], r["offset"], r["text"]): r for r in flat_records}
    return [
        (flat_by_coord[(r["page_no"], r["offset"], r["text"])], r)
        for r in prod_records
        if (r["page_no"], r["offset"], r["text"]) in flat_by_coord
    ]


def _assert_aligned_records(aligned: list[tuple[dict, dict]]) -> None:
    assert aligned, (
        "Expected at least one span that aligns on non-heading coordinates "
        "(page_no, offset, text) between flat and hierarchy readers, so the "
        "heading-only drift can be demonstrated."
    )
    # Every aligned pair proves that page_no/offset/text remain stable.
    # The root heading may be identical in both readers; only the nested
    # section spans must demonstrate heading-only/span-ID drift.
    for flat_rec, prod_rec in aligned:
        assert flat_rec["page_no"] == prod_rec["page_no"]
        assert flat_rec["offset"] == prod_rec["offset"]
        assert flat_rec["text"] == prod_rec["text"]


def _assert_heading_drift(aligned: list[tuple[dict, dict]]) -> None:
    drifted = [
        (flat_rec, prod_rec)
        for flat_rec, prod_rec in aligned
        if flat_rec["headings"] != prod_rec["headings"]
    ]
    assert drifted, (
        "Expected at least one aligned nested span whose heading_path "
        "changes between the legacy flat reader and production hierarchy "
        "reader."
    )
    for flat_rec, prod_rec in drifted:
        assert flat_rec["span_id"] != prod_rec["span_id"], (
            "An aligned span whose heading_path changes must drift on "
            "span_id. This is the intentional migration boundary."
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDoclingVersion:
    def test_docling_version_is_2109(self) -> None:
        """Docling version must be 2.109.x for HeadingHierarchyOptions."""
        import importlib.metadata

        version = importlib.metadata.version("docling")
        assert version.startswith("2.109"), (
            f"Docling version must be 2.109.x for HeadingHierarchyOptions, "
            f"got {version}"
        )


class TestProductionDefaultReader:
    """Verify the PRODUCTION ``_build_default_reader`` configuration directly."""

    def test_reader_export_type_is_json(self) -> None:
        """The production reader must be configured with export_type JSON."""
        reader = _build_default_reader()
        export_type = getattr(reader, "export_type", None)
        # ExportType.JSON is an enum; accept either the enum or its value.
        export_value = getattr(export_type, "value", export_type)
        assert (
            str(export_value).lower() == "json"
        ), f"Production reader export_type must be JSON, got {export_type!r}"

    def test_pdf_pipeline_has_heading_hierarchy_fields(self) -> None:
        """The production PDF pipeline must carry the exact hierarchy config.

        Asserts against the ACTUAL converter returned by the production
        ``_build_default_reader`` (not a reconstructed duplicate): enabled /
        use_bookmarks / use_numbering / use_style are True, max_level is 6,
        bookmark_match_threshold is 0.8, and generate_parsed_pages is True.
        """
        from docling.datamodel.base_models import InputFormat

        reader = _build_default_reader()
        converter = reader.doc_converter
        pdf_option = converter.format_to_options[InputFormat.PDF]
        pipeline_options = pdf_option.pipeline_options
        hho = pipeline_options.heading_hierarchy_options

        assert hho.enabled is True
        assert hho.use_bookmarks is True
        assert hho.use_numbering is True
        assert hho.use_style is True
        assert hho.max_level == 6
        assert hho.bookmark_match_threshold == 0.8
        assert pipeline_options.generate_parsed_pages is True


class TestRealSectionedPdfThroughProductionIngestor:
    """Run a real sectioned PDF through the production ``DoclingIngestor()``."""

    def test_sectioned_pdf_has_heading_depth_at_least_two(
        self, sectioned_pdf: Path
    ) -> None:
        """Production ``DoclingIngestor()`` must yield heading depth >= 2.

        This exercises the real default reader (with HeadingHierarchyModel
        enabled) end-to-end through ``DoclingIngestor().ingest``.
        """
        result = DoclingIngestor().ingest(
            sectioned_pdf, doc_id=DOC_ID, version_id=VERSION_ID
        )
        assert len(result.spans) > 0, "Ingestor produced no spans"
        max_depth = max(len(span.headings) for span in result.spans)
        assert max_depth >= 2, (
            f"Production DoclingIngestor on a sectioned PDF must yield "
            f"heading depth >= 2, got max_depth={max_depth}. "
            f"headings sample: {[list(s.headings) for s in result.spans[:5]]}"
        )

    def test_production_ingest_span_ids_match_exact_chain(
        self, sectioned_pdf: Path
    ) -> None:
        """Span_ids from ``DoclingIngestor().ingest`` must equal the exact chain.

        Recomputes span_ids via the exact ``_flatten_docling_metadata`` +
        ``NormalizationContract.normalize`` + ``uuid5`` chain over the same
        nodes and asserts per-span identity (including offset, which is the
        charspan-sourced offset, not an ordinal approximation).
        """
        ingestor = DoclingIngestor()
        result = ingestor.ingest(sectioned_pdf, doc_id=DOC_ID, version_id=VERSION_ID)

        # Re-run the reader/node_parser to get the raw nodes, then recompute
        # via the exact production chain. Docling conversion is deterministic
        # for this fixture, so nodes are structurally identical.
        documents = ingestor._reader.load_data(file_path=str(sectioned_pdf))
        nodes = list(ingestor._node_parser.get_nodes_from_documents(documents))
        recomputed = _production_span_records(nodes, DOC_ID, VERSION_ID)

        ingest_records = [
            {
                "span_id": str(span.span_id),
                "page_no": span.page_no,
                "headings": list(span.headings),
                "offset": span.offset,
                "text": span.text,
            }
            for span in result.spans
        ]
        assert ingest_records == recomputed, (
            "DoclingIngestor().ingest output must equal the exact production "
            "chain recomputation (span_id/page_no/headings/offset/text, in order)."
        )


class TestSpanIdMigrationDrift:
    """Demonstrate the INTENTIONAL span_id drift between hierarchy and flat readers.

    Both readers are run through the EXACT production span computation (no
    simplified ordinal offsets). Where the two readers' spans align on
    non-heading coordinates (page_no, offset, text), the heading_path differs
    and therefore span_id drifts. This is the documented migration boundary.
    """

    def test_default_reader_drifts_from_legacy_flat_reader(
        self, sectioned_pdf: Path
    ) -> None:
        from llama_index.node_parser.docling import DoclingNodeParser

        # --- Legacy flat reader (heading_hierarchy disabled) ---
        flat_reader = _legacy_flat_reader()
        # --- Production default reader (heading_hierarchy enabled) ---
        prod_reader = _build_default_reader()
        node_parser = DoclingNodeParser()

        flat_nodes = _reader_nodes(flat_reader, node_parser, sectioned_pdf)
        prod_nodes = _reader_nodes(prod_reader, node_parser, sectioned_pdf)
        flat_records = _production_span_records(flat_nodes, DOC_ID, VERSION_ID)
        prod_records = _production_span_records(prod_nodes, DOC_ID, VERSION_ID)

        _assert_distinct_span_id_sets(flat_records, prod_records)
        # Where the two readers align on non-heading coordinates (page_no,
        # offset, text), the span_id MUST still differ because heading_path
        # differs. Find aligned spans by (page_no, offset, text) and assert
        # drift on the heading dimension only.
        aligned = _aligned_records(flat_records, prod_records)
        _assert_aligned_records(aligned)
        _assert_heading_drift(aligned)


class TestCustomReaderInjectionRollback:
    """The ``DoclingIngestor(reader=...)`` injection path is the rollback lever.

    A caller can inject a flat/legacy reader and recover the legacy span_ids,
    proving the migration is reversible without touching production code.
    """

    def test_injected_flat_reader_restores_legacy_spans(
        self, sectioned_pdf: Path
    ) -> None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            HeadingHierarchyOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from llama_index.readers.docling import DoclingReader

        flat_hho = HeadingHierarchyOptions(enabled=False)
        flat_pipeline = PdfPipelineOptions(heading_hierarchy_options=flat_hho)
        flat_format = PdfFormatOption(pipeline_options=flat_pipeline)
        flat_converter = DocumentConverter(
            format_options={InputFormat.PDF: flat_format}
        )
        flat_reader = DoclingReader(export_type="json", doc_converter=flat_converter)

        # Baseline: legacy spans from the flat reader alone.
        legacy_result = DoclingIngestor(reader=flat_reader).ingest(
            sectioned_pdf, doc_id=DOC_ID, version_id=VERSION_ID
        )
        legacy_ids = [str(s.span_id) for s in legacy_result.spans]

        # Production default: hierarchy spans.
        prod_result = DoclingIngestor().ingest(
            sectioned_pdf, doc_id=DOC_ID, version_id=VERSION_ID
        )
        prod_ids = [str(s.span_id) for s in prod_result.spans]

        # Rollback: inject the flat reader into the ingestor and confirm we
        # recover the SAME span_ids as the legacy baseline (deterministic).
        rollback_result = DoclingIngestor(reader=flat_reader).ingest(
            sectioned_pdf, doc_id=DOC_ID, version_id=VERSION_ID
        )
        rollback_ids = [str(s.span_id) for s in rollback_result.spans]

        assert rollback_ids == legacy_ids, (
            "Injecting a flat reader must restore the exact legacy span_id "
            "sequence (rollback path is deterministic)."
        )
        assert rollback_ids != prod_ids, (
            "Rollback span_ids must differ from the production hierarchy "
            "span_ids, confirming injection actually changes behavior."
        )


class TestDocxPassesThroughProductionDefaultPath:
    """DOCX must process through the production default reader (no PDF-only crash)."""

    def test_docx_ingests_via_production_default(self, tmp_path: Path) -> None:
        from docx import Document

        docx_doc = Document()
        docx_doc.add_heading("Test Document", level=1)
        docx_doc.add_heading("Section 1", level=2)
        docx_doc.add_paragraph("Content for section 1.")
        docx_doc.add_heading("Section 2", level=2)
        docx_doc.add_paragraph("Content for section 2.")
        docx_path = tmp_path / "test.docx"
        docx_doc.save(str(docx_path))

        # Production default ingestor: PDF format has heading_hierarchy options,
        # DOCX falls through to default handling. Must not raise.
        result = DoclingIngestor().ingest(
            docx_path, doc_id=DOC_ID, version_id=VERSION_ID
        )
        assert (
            len(result.spans) > 0
        ), "DOCX must produce spans via production default path"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
