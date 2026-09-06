"""Evaluation fixtures and helpers for regression baselines.

This module provides:
- Minimal PDF fixture generator for formal runtime evaluation
- Representative queries derived from validation patterns
- Mock registry for hybrid baseline testing
- Helper utilities for baseline tests

Does NOT modify core retrieval logic - only provides test fixtures.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence
from unittest.mock import MagicMock
from uuid import uuid4

from PIL import Image, ImageDraw


def build_evaluation_pdf(
    pdf_path: Path,
    *,
    heading: str = "Evaluation Baseline Document",
    paragraphs: Sequence[str] = (
        "This is the first paragraph for evaluation baseline testing.",
        "This is the second paragraph representing searchable content.",
        "The third paragraph contains representative query terms like test query.",
        "Additional content for sample minimal document retrieval validation.",
    ),
) -> None:
    """Build a minimal PDF for evaluation baseline testing.

    Creates a PDF with:
    - One heading
    - Multiple paragraphs for retrieval testing

    This is the minimal fixture needed to establish retrieval stability baselines.
    """
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)

    # Draw heading
    draw.text((80, 80), heading, fill="black")

    # Draw paragraphs
    y_offset = 180
    for paragraph in paragraphs:
        draw.text((80, y_offset), paragraph, fill="black")
        y_offset += 80

    image.save(pdf_path, "PDF")


# Representative queries derived from validation report patterns
REPRESENTATIVE_QUERIES = [
    "test query",  # Generic evaluation query
    "sample",  # Document characteristic match
    "evaluation",  # Heading match
    "paragraph",  # Content structure match
]


def make_evaluation_registry() -> MagicMock:
    """Create a mock registry for hybrid baseline testing.

    Returns a MagicMock that implements the RegistryWriter protocol
    with ``query_spans_by_keyword`` returning sample keyword rows.

    This enables the hybrid mode to exercise the keyword retrieval
    path alongside vector and tree paths, providing baseline coverage
    for the full hybrid composition surface.
    """
    registry = MagicMock()
    uid = uuid4()
    registry.query_spans_by_keyword.return_value = [
        {
            "span_id": uid,
            "doc_id": uid,
            "version_id": uid,
            "raw_text": "Evaluation Baseline Document",
            "page_no": 1,
            "heading_path": "Evaluation Baseline Document",
            "match_score": 1.0,
        },
    ]
    return registry