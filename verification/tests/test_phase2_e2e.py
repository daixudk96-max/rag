from __future__ import annotations

from pathlib import Path

from parser.docling_wrapper import DoclingWrapper, NormalizationContract
from parser.span_generator import SpanGenerator
from registry import crud, queries

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "tests" / "fixtures" / "sample_minimal.pdf"


def test_pdf_to_spans_to_postgres(db_connection, applied_schema) -> None:
    contract = NormalizationContract(
        parser_name="Docling",
        parser_version="1.0",
        offset_basis="normalized_char_offset",
    )
    wrapper = DoclingWrapper(contract)
    parsed = wrapper.parse(SAMPLE_PDF)
    spans = SpanGenerator().generate_spans(parsed)

    doc_id = crud.create_document(db_connection, title="Phase2 E2E", source_uri=SAMPLE_PDF.as_uri())
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="phase2-e2e", normalization_contract_id=contract_id, version_no=1)
    crud.write_spans(db_connection, version_id, spans)

    rows = queries.query_spans_by_version(db_connection, version_id)
    assert rows
    assert rows[0]["heading_path"]
    assert rows[0]["page_no"] == 1
    assert rows[0]["raw_text"]
