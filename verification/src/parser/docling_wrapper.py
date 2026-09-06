from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docling
from docling.document_converter import DocumentConverter

from .normalization import clean_text, normalize_heading


@dataclass(frozen=True)
class NormalizationContract:
    parser_name: str
    parser_version: str
    offset_basis: str


class DoclingWrapper:
    def __init__(self, contract: NormalizationContract, converter: DocumentConverter | None = None) -> None:
        if contract.parser_name != "Docling":
            raise ValueError("parser_name must be Docling")
        self.contract = contract
        self.converter = converter or DocumentConverter()

    def parse(self, pdf_path: str | Path) -> dict[str, Any]:
        result = self.converter.convert(str(pdf_path))
        exported = result.document.export_to_dict()
        texts = exported.get("texts", [])

        heading_stack: dict[int, str] = {}
        items: list[dict[str, Any]] = []
        current_offset = 0

        for text_item in texts:
            raw_text = clean_text(text_item.get("text") or text_item.get("orig") or "")
            if not raw_text:
                continue

            label = str(text_item.get("label", "body"))
            level = int(text_item.get("level", 1) or 1)
            prov = text_item.get("prov") or []
            page_no = prov[0].get("page_no") if prov else None

            if "header" in label:
                heading_stack[level] = normalize_heading(raw_text)
                for key in list(heading_stack.keys()):
                    if key > level:
                        del heading_stack[key]

            heading_path = " > ".join(heading_stack[k] for k in sorted(heading_stack)) if heading_stack else "(root)"
            start_offset = current_offset
            end_offset = start_offset + len(raw_text)
            current_offset = end_offset + 1

            items.append(
                {
                    "page_no": page_no,
                    "heading_path": heading_path,
                    "text": raw_text,
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                    "label": label,
                    "level": level,
                }
            )

        return {
            "parser_name": self.contract.parser_name,
            "parser_version": self.contract.parser_version or getattr(docling, "__version__", "unknown"),
            "offset_basis": self.contract.offset_basis,
            "items": items,
        }
