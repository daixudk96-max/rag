from __future__ import annotations

from pathlib import Path
from typing import Sequence
from uuid import UUID, uuid4

import pytest

from llamaindex_runtime.ingestion import DoclingIngestor, IngestionPipeline
from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.registry import RegisteredDocument


class FakeDocument:
    def __init__(self, source: str) -> None:
        self.source = source


class FakeNode:
    def __init__(self, text: str, metadata: dict[str, object]) -> None:
        self._text = text
        self.metadata = metadata

    def get_content(self) -> str:
        return self._text


class FakeReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load_data(self, *, file_path: str) -> list[FakeDocument]:
        self.calls.append(file_path)
        return [FakeDocument(file_path)]


class FakeNodeParser:
    def __init__(self, nodes: list[FakeNode]) -> None:
        self._nodes = nodes
        self.calls: list[list[FakeDocument]] = []

    def get_nodes_from_documents(self, documents: Sequence[object]) -> list[FakeNode]:
        typed_documents = [
            document for document in documents if isinstance(document, FakeDocument)
        ]
        self.calls.append(typed_documents)
        return self._nodes


class RecordingRegistry:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str | None]] = []
        self.writes: list[tuple[UUID, tuple[CanonicalSpan, ...]]] = []
        self.registered_document = RegisteredDocument(
            doc_id=uuid4(),
            version_id=uuid4(),
            source_uri="file:///placeholder",
        )

    def register_document(
        self,
        *,
        source_path: Path,
        source_uri: str,
        title: str | None = None,
    ) -> RegisteredDocument:
        self.registered.append((source_uri, title))
        assert source_path.exists()
        return self.registered_document

    def write_spans(self, *, version_id: UUID, spans: Sequence[CanonicalSpan]) -> None:
        self.writes.append((version_id, tuple(spans)))

    def query_spans_by_version(self, version_id: UUID) -> list[dict]:
        return []

    def get_version(self, version_id: UUID):
        raise NotImplementedError

    def list_versions(self, doc_id: UUID):
        raise NotImplementedError

    def get_active_version(self, doc_id: UUID):
        raise NotImplementedError

    def healthcheck(self) -> bool:
        return True


def test_docling_ingestor_builds_deterministic_canonical_spans(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.txt"
    source_path.write_text("demo", encoding="utf-8")
    doc_id = uuid4()
    version_id = uuid4()
    reader = FakeReader()
    parser = FakeNodeParser(
        [
            FakeNode(
                "  First span  ",
                {"page_no": 1, "headings": ["Intro", "Section"], "offset": 12},
            ),
            FakeNode(
                "Second span",
                {"page_no": "2", "heading_path": "Appendix > A", "start_offset": 48},
            ),
        ]
    )
    ingestor = DoclingIngestor(reader=reader, node_parser=parser)

    first = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)
    second = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)

    assert reader.calls == [str(source_path.resolve()), str(source_path.resolve())]
    assert parser.calls[0][0].source == str(source_path.resolve())
    assert parser.calls[1][0].source == str(source_path.resolve())
    assert len(first.spans) == 2
    assert first.spans == second.spans
    assert first.dropped_nodes == 0
    assert first.spans[0].text == "First span"
    assert first.spans[0].heading_path == "Intro > Section"
    assert first.spans[0].page_no == 1
    assert first.spans[0].offset == 12
    assert first.spans[1].heading_path == "Appendix > A"
    assert first.spans[1].page_no == 2
    assert first.spans[1].offset == 48


def test_docling_ingestor_counts_dropped_empty_nodes(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.txt"
    source_path.write_text("demo", encoding="utf-8")
    ingestor = DoclingIngestor(
        reader=FakeReader(),
        node_parser=FakeNodeParser([FakeNode("   ", {"page_no": 1, "offset": 0})]),
    )

    result = ingestor.ingest(source_path, doc_id=uuid4(), version_id=uuid4())

    assert result.spans == ()
    assert result.dropped_nodes == 1


def test_docling_ingestor_rejects_missing_source_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.txt"
    ingestor = DoclingIngestor(reader=FakeReader(), node_parser=FakeNodeParser([]))

    with pytest.raises(FileNotFoundError):
        ingestor.ingest(missing_path, doc_id=uuid4(), version_id=uuid4())


def test_ingestion_pipeline_does_not_register_missing_source_path(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.txt"
    registry = RecordingRegistry()
    pipeline = IngestionPipeline(
        registry=registry,
        ingestor=DoclingIngestor(reader=FakeReader(), node_parser=FakeNodeParser([])),
    )

    with pytest.raises(FileNotFoundError):
        pipeline.ingest(missing_path)

    assert registry.registered == []
    assert registry.writes == []


def test_docling_ingestor_registers_document_and_persists_spans(tmp_path: Path) -> None:
    # DoclingIngestor.ingest() directly, bypassing E2a-only IngestionPipeline.ingest()
    source_path = tmp_path / "formal.pdf"
    source_path.write_text("demo", encoding="utf-8")
    registry = RecordingRegistry()
    ingestor = DoclingIngestor(
        reader=FakeReader(),
        node_parser=FakeNodeParser(
            [FakeNode("Only span", {"page_no": 1, "headings": ["Root"], "offset": 0})]
        ),
    )

    registered_doc = registry.register_document(
        source_path=source_path,
        source_uri=source_path.resolve().as_uri(),
        title="Formal runtime test",
    )
    result = ingestor.ingest(
        source_path, doc_id=registered_doc.doc_id, version_id=registered_doc.version_id
    )
    registry.write_spans(version_id=registered_doc.version_id, spans=result.spans)

    assert registry.registered == [
        (source_path.resolve().as_uri(), "Formal runtime test")
    ]
    assert registry.writes[0][0] == registry.registered_document.version_id
    assert registry.writes[0][1] == result.spans
    assert result.doc_id == registry.registered_document.doc_id
    assert result.version_id == registry.registered_document.version_id


# ---------------------------------------------------------------------------
# Unit: DoclingIngestor._flatten_docling_metadata
# ---------------------------------------------------------------------------


class TestFlattenDoclingMetadata:
    """Tests for the metadata flattening that extracts Docling's nested
    provenance fields (page_no, charspan, label) to top-level keys
    that NormalizationContract can consume."""

    def test_extracts_page_no_from_prov(self) -> None:
        metadata = {
            "doc_items": [
                {
                    "prov": [
                        {"page_no": 3, "bbox": {}, "charspan": [0, 10]},
                    ],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["page_no"] == 3

    def test_extracts_start_offset_from_charspan(self) -> None:
        metadata = {
            "doc_items": [
                {
                    "prov": [
                        {"page_no": 1, "bbox": {}, "charspan": [42, 60]},
                    ],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["start_offset"] == 42

    def test_extracts_label_from_doc_items(self) -> None:
        metadata = {
            "doc_items": [
                {
                    "label": "section_header",
                    "prov": [{"page_no": 1, "bbox": {}, "charspan": [0, 5]}],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["label"] == "section_header"

    def test_top_level_keys_take_priority(self) -> None:
        """Top-level page_no must not be overwritten by nested value."""
        metadata = {
            "page_no": 7,
            "doc_items": [
                {
                    "prov": [
                        {"page_no": 3, "bbox": {}, "charspan": [0, 10]},
                    ],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["page_no"] == 7

    def test_top_level_offset_keys_take_priority(self) -> None:
        """Top-level offset keys must not be overwritten by nested charspan."""
        metadata = {
            "offset": 100,
            "doc_items": [
                {
                    "prov": [
                        {"page_no": 1, "bbox": {}, "charspan": [42, 60]},
                    ],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["offset"] == 100
        assert "start_offset" not in flat

    def test_top_level_start_offset_takes_priority(self) -> None:
        metadata = {
            "start_offset": 200,
            "doc_items": [
                {
                    "prov": [
                        {"page_no": 1, "bbox": {}, "charspan": [42, 60]},
                    ],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["start_offset"] == 200

    def test_empty_doc_items(self) -> None:
        metadata = {"doc_items": []}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat
        assert "start_offset" not in flat

    def test_no_doc_items_key(self) -> None:
        metadata = {"schema_name": "test"}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat

    def test_empty_metadata(self) -> None:
        flat = DoclingIngestor._flatten_docling_metadata({})
        assert "page_no" not in flat

    def test_doc_items_not_a_list(self) -> None:
        metadata = {"doc_items": "not a list"}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat

    def test_first_item_not_a_dict(self) -> None:
        metadata = {"doc_items": ["not a dict"]}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat

    def test_prov_not_a_list(self) -> None:
        metadata = {"doc_items": [{"prov": "not a list"}]}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat

    def test_prov_empty(self) -> None:
        metadata = {"doc_items": [{"prov": []}]}
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "page_no" not in flat

    def test_charspan_not_a_list(self) -> None:
        metadata = {
            "doc_items": [
                {
                    "prov": [{"page_no": 1, "bbox": {}, "charspan": "bad"}],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert "start_offset" not in flat

    def test_preserves_existing_metadata_keys(self) -> None:
        metadata = {
            "schema_name": "docling_core.transforms.chunker.DocMeta",
            "version": "1.0.0",
            "doc_items": [
                {
                    "prov": [{"page_no": 2, "bbox": {}, "charspan": [10, 20]}],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["schema_name"] == "docling_core.transforms.chunker.DocMeta"
        assert flat["version"] == "1.0.0"
        assert flat["page_no"] == 2
        assert flat["start_offset"] == 10

    def test_doc_offset_takes_priority_over_charspan(self) -> None:
        metadata = {
            "doc_offset": 300,
            "doc_items": [
                {
                    "prov": [{"page_no": 1, "bbox": {}, "charspan": [42, 60]}],
                },
            ],
        }
        flat = DoclingIngestor._flatten_docling_metadata(metadata)
        assert flat["doc_offset"] == 300
        assert "start_offset" not in flat


class TestFlattenDoclingMetadataIntegration:
    """Integration: verify DoclingIngestor.ingest uses _flatten_docling_metadata
    to produce correct provenance on CanonicalSpan objects."""

    def test_ingestor_extracts_page_no_from_nested_docling_metadata(
        self, tmp_path: Path
    ) -> None:
        source_path = tmp_path / "nested.pdf"
        source_path.write_text("demo", encoding="utf-8")
        doc_id = uuid4()
        version_id = uuid4()

        reader = FakeReader()
        parser = FakeNodeParser(
            [
                FakeNode(
                    "Text with page",
                    {
                        "doc_items": [
                            {
                                "label": "text",
                                "prov": [
                                    {"page_no": 5, "bbox": {}, "charspan": [100, 120]}
                                ],
                            },
                        ],
                    },
                )
            ],
        )
        ingestor = DoclingIngestor(reader=reader, node_parser=parser)

        result = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)
        assert len(result.spans) == 1
        assert result.spans[0].page_no == 5

    def test_ingestor_extracts_offset_from_nested_charspan(
        self, tmp_path: Path
    ) -> None:
        source_path = tmp_path / "offset.pdf"
        source_path.write_text("demo", encoding="utf-8")
        doc_id = uuid4()
        version_id = uuid4()

        reader = FakeReader()
        parser = FakeNodeParser(
            [
                FakeNode(
                    "Text with offset",
                    {
                        "doc_items": [
                            {
                                "label": "text",
                                "prov": [
                                    {"page_no": 1, "bbox": {}, "charspan": [42, 60]}
                                ],
                            },
                        ],
                    },
                )
            ],
        )
        ingestor = DoclingIngestor(reader=reader, node_parser=parser)

        result = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)
        assert len(result.spans) == 1
        assert result.spans[0].offset == 42

    def test_ingestor_top_level_page_no_takes_priority(self, tmp_path: Path) -> None:
        source_path = tmp_path / "priority.pdf"
        source_path.write_text("demo", encoding="utf-8")
        doc_id = uuid4()
        version_id = uuid4()

        reader = FakeReader()
        parser = FakeNodeParser(
            [
                FakeNode(
                    "Text",
                    {
                        "page_no": 7,
                        "doc_items": [
                            {
                                "prov": [
                                    {"page_no": 3, "bbox": {}, "charspan": [0, 10]}
                                ],
                            },
                        ],
                    },
                )
            ],
        )
        ingestor = DoclingIngestor(reader=reader, node_parser=parser)

        result = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)
        assert result.spans[0].page_no == 7
