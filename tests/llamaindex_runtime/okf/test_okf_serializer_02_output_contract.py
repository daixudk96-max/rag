"""Serialized file, frontmatter, span, and determinism tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from llamaindex_runtime.okf.contracts import load_raw_frontmatter
from llamaindex_runtime.okf.sidecar import SpanSidecar

from ._serializer_testkit import (
    FakeDoclingNode,
    make_docling_metadata_with_nested_prov,
)


class TestSerializerOutputFiles:
    """Verify output files land at correct locations."""

    def test_raw_md_written_to_raw_subdirectory(self, tmp_path: Path) -> None:
        """raw/<slug>.md must be written to bundle_root/raw/."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        md_path = tmp_path / "raw" / "test-doc.md"
        assert md_path.exists()
        assert md_path.read_text(encoding="utf-8")

    def test_spans_json_written_adjacent_to_md(self, tmp_path: Path) -> None:
        """<slug>.spans.json must be written adjacent to the .md file."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        sidecar_path = tmp_path / "raw" / "test-doc.spans.json"
        assert sidecar_path.exists()

        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1


class TestSerializerFrontmatter:
    """Verify frontmatter passes RawFrontmatterContract."""

    def test_frontmatter_has_required_raw_fields(self, tmp_path: Path) -> None:
        """Frontmatter must have all RawFrontmatterContract required fields."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        md_path = tmp_path / "raw" / "test-doc.md"
        content = md_path.read_text(encoding="utf-8")
        frontmatter, body = load_raw_frontmatter(content)

        assert frontmatter["type"] == "raw"
        assert frontmatter["doc_id"] == str(doc_id)
        assert frontmatter["version_id"] == str(version_id)
        assert frontmatter["source_checksum"] == "a" * 64
        assert frontmatter["docling_version"] == "2.45.0"
        assert frontmatter["generated_by"] == "docling-to-okf/1.0"

    def test_frontmatter_rejects_invalid_doc_id(self, tmp_path: Path) -> None:
        """Invalid doc_id must raise ValueError with clear message."""
        from llamaindex_runtime.okf.serializer import serialize_document

        node = FakeDoclingNode(text="Test", metadata={})

        with pytest.raises(ValueError, match="doc_id"):
            serialize_document(
                [node],
                doc_id="not-a-uuid",
                version_id=str(uuid4()),
                source_checksum="a" * 64,
                docling_version="2.45.0",
                bundle_root=tmp_path,
                name="test-doc",
            )


class TestSerializerSidecarSpans:
    """Verify sidecar spans equal NormalizationContract output element-for-element."""

    def test_sidecar_spans_match_normalization_output(self, tmp_path: Path) -> None:
        """Sidecar spans must match NormalizationContract.normalize output."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(
                page_no=1, offset=0, heading_path=("Intro",)
            ),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        sidecar_path = tmp_path / "raw" / "test-doc.spans.json"
        sidecar = SpanSidecar.load(sidecar_path)

        assert sidecar.doc_id == str(doc_id)
        assert sidecar.version_id == str(version_id)
        assert len(sidecar.spans) == 1

        span0 = sidecar.spans[0]
        assert span0.page_no == 1
        assert span0.heading_path == ("Intro",)
        assert span0.offset == 0
        assert "First paragraph" in span0.text

    def test_span_id_uses_uuid5_formula(self, tmp_path: Path) -> None:
        """span_id must use uuid5 over the six-element formula."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(
                page_no=1, offset=0, heading_path=("Intro",)
            ),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        sidecar_path = tmp_path / "raw" / "test-doc.spans.json"
        sidecar = SpanSidecar.load(sidecar_path)

        normalized_text = "First paragraph."
        expected_span_id = uuid5(
            NAMESPACE_URL,
            f"{doc_id}|{version_id}|{1}|{'/'.join(('Intro',))}|{0}|{normalized_text}",
        )

        assert sidecar.spans[0].span_id == str(expected_span_id)


class TestSerializerDeterminism:
    """Verify same input yields byte-identical output (determinism)."""

    def test_same_input_twice_byte_identical(self, tmp_path: Path) -> None:
        """Serializing same input twice must yield byte-identical outputs."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )
        (tmp_path / "run1").mkdir()
        (tmp_path / "run2").mkdir()

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path / "run1",
            name="test-doc",
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path / "run2",
            name="test-doc",
        )

        md1 = (tmp_path / "run1" / "raw" / "test-doc.md").read_bytes()
        md2 = (tmp_path / "run2" / "raw" / "test-doc.md").read_bytes()
        assert md1 == md2, "Markdown files must be byte-identical"

        sidecar1 = (tmp_path / "run1" / "raw" / "test-doc.spans.json").read_bytes()
        sidecar2 = (tmp_path / "run2" / "raw" / "test-doc.spans.json").read_bytes()
        assert sidecar1 == sidecar2, "Sidecar files must be byte-identical"
        pair1 = (tmp_path / "run1" / "raw" / "test-doc.pair.json").read_bytes()
        pair2 = (tmp_path / "run2" / "raw" / "test-doc.pair.json").read_bytes()
        assert pair1 == pair2, "Pair manifests must be byte-identical"


class TestSerializerSlugValidation:
    """Verify slug validation and path containment."""

    def test_slug_must_be_kebab_case(self, tmp_path: Path) -> None:
        """Slug must be kebab-case (lowercase letters, numbers, hyphens)."""
        from llamaindex_runtime.okf.serializer import serialize_document

        node = FakeDoclingNode(text="Test", metadata={})

        with pytest.raises(ValueError, match="slug|name"):
            serialize_document(
                [node],
                doc_id=str(uuid4()),
                version_id=str(uuid4()),
                source_checksum="a" * 64,
                docling_version="2.45.0",
                bundle_root=tmp_path,
                name="../escape",
            )

    def test_rejects_empty_node_sequence(self, tmp_path: Path) -> None:
        """Empty node sequence must raise ValueError."""
        from llamaindex_runtime.okf.serializer import serialize_document

        with pytest.raises(ValueError, match="empty|invalid"):
            serialize_document(
                [],
                doc_id=str(uuid4()),
                version_id=str(uuid4()),
                source_checksum="a" * 64,
                docling_version="2.45.0",
                bundle_root=tmp_path,
                name="test-doc",
            )


class TestSerializerMarkdownBody:
    """Verify Markdown body is human-readable."""

    def test_body_contains_text_content(self, tmp_path: Path) -> None:
        """Body must contain span text in readable form."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        md_path = tmp_path / "raw" / "test-doc.md"
        content = md_path.read_text(encoding="utf-8")
        _, body = load_raw_frontmatter(content)

        assert "First paragraph" in body
