from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from llamaindex_runtime.ingestion.bundle import build_docling_bundle


class FakeDoclingDocument:
    def export_to_dict(self) -> dict[str, object]:
        return {"texts": [{"text": "Body text"}]}

    def export_to_markdown(self, **_: object) -> str:
        return "# Heading\n\nBody text"


class RecordingConverter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def convert(self, source: str) -> object:
        self.calls.append(source)
        return SimpleNamespace(document=FakeDoclingDocument())


def test_build_docling_bundle_parses_source_once(tmp_path: Path) -> None:
    source_path = tmp_path / "bundle-source.pdf"
    source_path.write_bytes(b"pdf")
    converter = RecordingConverter()

    bundle = build_docling_bundle(source_path, converter=converter)

    assert converter.calls == [str(source_path.resolve())]
    assert len(bundle.json_documents) == 1
    assert len(bundle.markdown_documents) == 1
    assert bundle.json_documents[0].doc_id != bundle.markdown_documents[0].doc_id
    assert '"texts"' in bundle.json_documents[0].get_content()
    assert "Body text" in bundle.markdown_documents[0].get_content()
