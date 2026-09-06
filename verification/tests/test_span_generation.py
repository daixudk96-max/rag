from __future__ import annotations

import uuid
from pathlib import Path

from parser.docling_wrapper import DoclingWrapper, NormalizationContract
from parser.span_generator import SpanGenerator
from registry import crud, queries

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "tests" / "fixtures" / "sample_minimal.pdf"


def _parsed_output():
    wrapper = DoclingWrapper(
        NormalizationContract(
            parser_name="Docling",
            parser_version="1.0",
            offset_basis="normalized_char_offset",
        )
    )
    return wrapper.parse(SAMPLE_PDF)


def test_generate_spans_from_docling_output() -> None:
    spans = SpanGenerator().generate_spans(_parsed_output())
    assert spans
    assert spans[0]["span_kind"] == "paragraph"


def test_span_has_page_and_heading() -> None:
    spans = SpanGenerator().generate_spans(_parsed_output())
    first = spans[0]
    assert first["page_no"] == 1
    assert first["heading_path"]


def test_spans_are_deterministic() -> None:
    generator = SpanGenerator()
    first = generator.generate_spans(_parsed_output())
    second = generator.generate_spans(_parsed_output())
    assert first == second


def test_spans_persist_to_db(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, title="Docling Sample", source_uri=SAMPLE_PDF.as_uri())
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="phase2-sample", normalization_contract_id=contract_id, version_no=1)
    spans = SpanGenerator().generate_spans(_parsed_output())
    ids = crud.write_spans(db_connection, version_id, spans)
    rows = queries.query_spans_by_version(db_connection, version_id)
    assert len(ids) == len(rows)
    assert rows[0]["page_no"] == 1
