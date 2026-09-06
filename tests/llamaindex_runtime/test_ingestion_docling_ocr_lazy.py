"""OCR lazy-init contract for the query-time docling converter.

build_docling_bundle constructs its own DocumentConverter when none is
injected (tree recall path). Docling defaults do_ocr=True, which starts the
RapidOCR engine on every query even for text-only PDFs. Contract:

- OCR is enabled only when the source PDF actually contains raster images;
- text-only PDFs convert with do_ocr=False (no OCR engine startup);
- non-PDF sources keep plain default converter handling;
- any image-detection failure fails safe to do_ocr=True (prior behavior).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from llamaindex_runtime.ingestion.bundle import (
    _build_default_converter,
    _pdf_has_raster_images,
)


def _write_text_pdf(path: Path) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "Urban air quality is monitored by city stations.")
    c.save()


def _write_image_pdf(path: Path) -> None:
    from PIL import Image
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    png = path.with_suffix(".png")
    Image.new("RGB", (8, 8), (200, 0, 0)).save(png)
    c = canvas.Canvas(str(path))
    c.drawImage(str(png), 72, 720, width=1 * inch, height=1 * inch)
    c.save()
    png.unlink()


def test_text_only_pdf_has_no_raster_images(tmp_path: Path) -> None:
    pdf = tmp_path / "text.pdf"
    _write_text_pdf(pdf)
    assert _pdf_has_raster_images(pdf) is False


def test_pdf_with_embedded_image_has_raster_images(tmp_path: Path) -> None:
    pdf = tmp_path / "image.pdf"
    _write_image_pdf(pdf)
    assert _pdf_has_raster_images(pdf) is True


def _install_fake_docling(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    pdf_format_cls = type("PdfFormatOption", (), {})

    def pdf_format_init(self: object, pipeline_options: object = None) -> None:
        self.pipeline_options = pipeline_options

    pdf_format_cls.__init__ = pdf_format_init  # type: ignore[method-assign]
    conv_cls = type("DocumentConverter", (), {})

    def conv_init(self: object, format_options: object = None) -> None:
        captured["format_options"] = format_options

    conv_cls.__init__ = conv_init  # type: ignore[method-assign]
    pdf_opts_cls = type("PdfPipelineOptions", (), {})

    def opts_init(self: object, do_ocr: bool = True) -> None:
        self.do_ocr = do_ocr

    pdf_opts_cls.__init__ = opts_init  # type: ignore[method-assign]

    dc_mod = ModuleType("docling.document_converter")
    dc_mod.DocumentConverter = conv_cls  # type: ignore[attr-defined]
    dc_mod.PdfFormatOption = pdf_format_cls  # type: ignore[attr-defined]
    base_mod = ModuleType("docling.datamodel.base_models")
    base_mod.InputFormat = SimpleNamespace(PDF="pdf")  # type: ignore[attr-defined]
    pipe_mod = ModuleType("docling.datamodel.pipeline_options")
    pipe_mod.PdfPipelineOptions = pdf_opts_cls  # type: ignore[attr-defined]
    dm_mod = ModuleType("docling.datamodel")
    dl_mod = ModuleType("docling")
    monkeypatch.setitem(sys.modules, "docling", dl_mod)
    monkeypatch.setitem(sys.modules, "docling.document_converter", dc_mod)
    monkeypatch.setitem(sys.modules, "docling.datamodel", dm_mod)
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_mod)
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipe_mod)


def test_converter_for_text_pdf_disables_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)
    pdf = tmp_path / "text.pdf"
    _write_text_pdf(pdf)
    _build_default_converter(pdf)
    opts = captured["format_options"]["pdf"].pipeline_options
    assert opts.do_ocr is False


def test_converter_for_image_pdf_keeps_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)
    pdf = tmp_path / "image.pdf"
    _write_image_pdf(pdf)
    _build_default_converter(pdf)
    opts = captured["format_options"]["pdf"].pipeline_options
    assert opts.do_ocr is True


def test_converter_for_non_pdf_keeps_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)
    txt = tmp_path / "plain.txt"
    txt.write_text("hello", encoding="utf-8")
    _build_default_converter(txt)
    assert captured["format_options"] is None
