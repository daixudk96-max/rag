from __future__ import annotations

from pathlib import Path

import pytest

from parser.docling_wrapper import DoclingWrapper, NormalizationContract

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "tests" / "fixtures" / "sample_minimal.pdf"


def test_reject_invalid_contract() -> None:
    with pytest.raises(ValueError):
        DoclingWrapper(
            NormalizationContract(
                parser_name="OtherParser",
                parser_version="1.0",
                offset_basis="normalized_char_offset",
            )
        )


def test_capture_parser_metadata() -> None:
    wrapper = DoclingWrapper(
        NormalizationContract(
            parser_name="Docling",
            parser_version="1.0",
            offset_basis="normalized_char_offset",
        )
    )
    result = wrapper.parse(SAMPLE_PDF)
    assert result["parser_name"] == "Docling"
    assert result["parser_version"] == "1.0"
    assert result["offset_basis"] == "normalized_char_offset"


def test_deterministic_output() -> None:
    wrapper = DoclingWrapper(
        NormalizationContract(
            parser_name="Docling",
            parser_version="1.0",
            offset_basis="normalized_char_offset",
        )
    )
    first = wrapper.parse(SAMPLE_PDF)
    second = wrapper.parse(SAMPLE_PDF)
    assert first == second


def test_output_structure() -> None:
    wrapper = DoclingWrapper(
        NormalizationContract(
            parser_name="Docling",
            parser_version="1.0",
            offset_basis="normalized_char_offset",
        )
    )
    result = wrapper.parse(SAMPLE_PDF)
    assert result["items"]
    first = result["items"][0]
    assert {"page_no", "heading_path", "text", "start_offset", "end_offset"}.issubset(first.keys())
    assert first["end_offset"] > first["start_offset"]
