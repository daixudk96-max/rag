from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from llama_index.core import Document as LlamaDocument


@dataclass(frozen=True)
class DoclingBundle:
    source_path: Path
    json_documents: tuple[LlamaDocument, ...]
    markdown_documents: tuple[LlamaDocument, ...]


class DoclingConverterProtocol(Protocol):
    def convert(self, source: str) -> object: ...


def _pdf_has_raster_images(path: Path) -> bool:
    """Return True when the PDF embeds at least one raster image XObject.

    Best-effort pre-scan via pypdf; any import or parse failure fails safe
    to True so OCR behavior degrades to the prior always-on contract.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return True
    try:
        reader = PdfReader(str(path), strict=False)
        for page in reader.pages:
            resources = page.get("/Resources")
            if resources is None:
                continue
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            if not resources:
                continue
            xobjects = resources.get("/XObject")
            if not xobjects:
                continue
            if hasattr(xobjects, "get_object"):
                xobjects = xobjects.get_object()
            for value in xobjects.values():
                xobj = value.get_object()
                if xobj.get("/Subtype") == "/Image":
                    return True
    except Exception:
        return True
    return False


def _build_default_converter(path: Path) -> DoclingConverterProtocol:
    """Build the query-time converter with OCR gated on actual image content.

    Docling defaults ``do_ocr=True``, which starts the OCR engine for every
    conversion. The tree recall path converts the source document on each
    query, so text-only PDFs paid a full OCR startup for nothing. OCR is
    now enabled only when the PDF really embeds raster images; non-PDF
    sources keep plain default handling.
    """
    from docling.document_converter import DocumentConverter

    if path.suffix.lower() != ".pdf":
        return DocumentConverter()

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    pipeline_options = PdfPipelineOptions(do_ocr=_pdf_has_raster_images(path))
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def build_docling_bundle(
    source_path: str | Path,
    *,
    converter: DoclingConverterProtocol | None = None,
) -> DoclingBundle:
    resolved_path = Path(source_path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Source file not found: {resolved_path}")

    doc_converter: DoclingConverterProtocol
    if converter is None:
        doc_converter = _build_default_converter(resolved_path)
    else:
        doc_converter = converter
    from llama_index.core import Document as LlamaDocument

    conversion_result: Any = doc_converter.convert(str(resolved_path))
    docling_document = conversion_result.document
    json_document = LlamaDocument(
        doc_id=str(uuid.uuid4()),
        text=json.dumps(docling_document.export_to_dict()),
    )
    markdown_document = LlamaDocument(
        doc_id=str(uuid.uuid4()),
        text=docling_document.export_to_markdown(image_placeholder=""),
    )
    return DoclingBundle(
        source_path=resolved_path,
        json_documents=(json_document,),
        markdown_documents=(markdown_document,),
    )
