"""Docling-node shapes, metadata boundaries, and rejection-path tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanSidecar

from ._serializer_testkit import (
    FakeDoclingNode,
    FakeDoclingNodeWithTextAttr,
    assert_span_identity_matches_direct_chain,
    build_direct_chain_expectation,
    make_docling_metadata_with_nested_prov,
)


class TestSerializerMetadataPriority:
    """Verify top-level metadata takes priority over nested prov."""

    def test_top_level_page_no_priority_over_nested_prov(self, tmp_path: Path) -> None:
        """Top-level page_no must take priority over nested prov value."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        # Top-level page_no=99, nested prov has page_no=1
        metadata = make_docling_metadata_with_nested_prov(page_no=1, offset=0)
        metadata["page_no"] = 99

        node = FakeDoclingNode(text="Test paragraph.", metadata=metadata)

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

        assert sidecar.spans[0].page_no == 99

    def test_nested_prov_fallback_when_no_top_level(self, tmp_path: Path) -> None:
        """Nested prov must be used when no top-level page_no."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="Test paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=5, offset=100),
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

        assert sidecar.spans[0].page_no == 5
        assert sidecar.spans[0].offset == 100


class TestSerializerDroppedNodes:
    """Verify whitespace-only nodes are dropped with observable count."""

    def test_whitespace_only_nodes_dropped(self, tmp_path: Path) -> None:
        """Whitespace-only nodes must be dropped (not written to sidecar)."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        nodes = [
            FakeDoclingNode(
                text="Valid paragraph.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
            ),
            FakeDoclingNode(
                text="   \n\t  ",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=100),
            ),
            FakeDoclingNode(
                text="Another valid.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=200),
            ),
        ]

        result = serialize_document(
            nodes,
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert result.span_count == 2

        sidecar_path = tmp_path / "raw" / "test-doc.spans.json"
        sidecar = SpanSidecar.load(sidecar_path)

        assert len(sidecar.spans) == 2

    def test_empty_string_nodes_dropped(self, tmp_path: Path) -> None:
        """Empty string nodes must be dropped."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        nodes = [
            FakeDoclingNode(
                text="Valid paragraph.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
            ),
            FakeDoclingNode(
                text="",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=100),
            ),
        ]

        result = serialize_document(
            nodes,
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert result.span_count == 1

    def test_dropped_node_count_exposed_on_result(self, tmp_path: Path) -> None:
        """SerializedRawFile must expose dropped_node_count for observability."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        nodes = [
            FakeDoclingNode(
                text="Valid paragraph.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
            ),
            FakeDoclingNode(
                text="   \n\t  ",  # Whitespace-only (dropped)
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=100),
            ),
            FakeDoclingNode(
                text="Another valid.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=200),
            ),
        ]

        result = serialize_document(
            nodes,
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        # FROZEN CONTRACT: dropped_node_count is mandatory, not optional
        assert hasattr(
            result, "dropped_node_count"
        ), "SerializedRawFile must have dropped_node_count"
        assert (
            result.dropped_node_count == 1
        ), f"Expected 1 dropped, got {result.dropped_node_count}"
        assert result.span_count == 2

    def test_dropped_node_count_multiple_whitespace(self, tmp_path: Path) -> None:
        """Multiple whitespace nodes must all be counted."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        nodes = [
            FakeDoclingNode(
                text="Valid.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
            ),
            FakeDoclingNode(
                text="   ",  # Whitespace
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=100),
            ),
            FakeDoclingNode(
                text="\n\n",  # Newlines
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=200),
            ),
            FakeDoclingNode(
                text="",  # Empty
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=300),
            ),
        ]

        result = serialize_document(
            nodes,
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert (
            result.dropped_node_count == 3
        ), f"Expected 3 dropped, got {result.dropped_node_count}"
        assert result.span_count == 1

    def test_dropped_node_count_zero_when_all_valid(self, tmp_path: Path) -> None:
        """No dropped nodes means dropped_node_count is zero."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        nodes = [
            FakeDoclingNode(
                text="First valid.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
            ),
            FakeDoclingNode(
                text="Second valid.",
                metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=100),
            ),
        ]

        result = serialize_document(
            nodes,
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert result.dropped_node_count == 0
        assert result.span_count == 2


class TestSerializerObjectNodeShape:
    """Verify serializer handles both get_content() and .text fallback."""

    def test_node_with_get_content_method(self, tmp_path: Path) -> None:
        """Node with get_content() method must use that method."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="Should be extracted via get_content",
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
        sidecar = SpanSidecar.load(sidecar_path)

        assert "Should be extracted via get_content" in sidecar.spans[0].text

    def test_node_with_only_text_attribute(self, tmp_path: Path) -> None:
        """Node with only .text attribute (no get_content) must use .text."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNodeWithTextAttr(
            text="Extracted via text attribute",
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
        sidecar = SpanSidecar.load(sidecar_path)

        assert "Extracted via text attribute" in sidecar.spans[0].text


class TestSerializerPageNoNone:
    """Verify valid page_no=None handling."""

    def test_page_no_none_preserved_in_sidecar(self, tmp_path: Path) -> None:
        """page_no=None must be preserved in sidecar."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        metadata = make_docling_metadata_with_nested_prov(page_no=None, offset=0)

        node = FakeDoclingNode(text="Test paragraph.", metadata=metadata)

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

        assert sidecar.spans[0].page_no is None


class TestSerializerDoclingOutputAnnotation:
    """serialize_document docling_output must be typed as Sequence[object]."""

    def test_docling_output_parameter_annotated_as_sequence(self) -> None:
        """docling_output parameter annotation must be Sequence-compatible."""
        import inspect
        import typing

        from llamaindex_runtime.okf.serializer import serialize_document

        sig = inspect.signature(serialize_document)
        param = sig.parameters["docling_output"]
        annotation = param.annotation
        # Resolve stringified annotations if needed
        if isinstance(annotation, str):
            # Annotation may be stringified as "Sequence[object]" or similar
            assert "Sequence" in annotation or "Sequence" in str(
                annotation
            ), f"docling_output must be Sequence-typed, got {annotation}"
        else:
            origin = typing.get_origin(annotation)
            assert origin is not None or "Sequence" in str(
                annotation
            ), f"docling_output must be Sequence-typed, got {annotation}"

    def test_docling_output_first_param_is_keyword_only_or_positional(self) -> None:
        """docling_output is the first parameter (positional-or-keyword allowed)."""
        import inspect

        from llamaindex_runtime.okf.serializer import serialize_document

        sig = inspect.signature(serialize_document)
        params = list(sig.parameters.keys())
        assert (
            params[0] == "docling_output"
        ), f"docling_output must be first param, got {params[0]}"


class TestSerializerNoRootHeadingEnrichment:
    """HIGH-1 regression: object-node root headings/heading_path must not be injected."""

    def test_object_node_root_headings_not_injected_into_sidecar(
        self, tmp_path: Path
    ) -> None:
        """Object root headings must not enter the metadata-only direct chain."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()
        raw_text = "Body paragraph with no heading context in metadata."
        node = FakeDoclingNode(text=raw_text, metadata={})
        node.headings = ["Root Only Heading"]  # type: ignore[attr-defined]
        node.heading_path = ("Root Only", "Path")  # type: ignore[attr-defined]
        expected = build_direct_chain_expectation(
            metadata=node.metadata,
            raw_text=raw_text,
            doc_id=doc_id,
            version_id=version_id,
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

        span0 = SpanSidecar.load(tmp_path / "raw" / "test-doc.spans.json").spans[0]
        assert span0.heading_path == expected.normalized.headings == ()
        assert span0.offset == expected.normalized.offset
        assert span0.page_no == expected.normalized.page_no
        assert_span_identity_matches_direct_chain(span0, expected)

    def test_mapping_node_root_headings_not_injected_into_sidecar(
        self, tmp_path: Path
    ) -> None:
        """Mapping root headings must not enter the metadata-only direct chain."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()
        raw_text = "Mapping body with root headings but empty metadata."
        node: dict[str, Any] = {
            "text": raw_text,
            "metadata": {},
            "headings": ["Root Only Heading"],
            "heading_path": ("Root Only", "Path"),
        }
        expected = build_direct_chain_expectation(
            metadata=node["metadata"],
            raw_text=raw_text,
            doc_id=doc_id,
            version_id=version_id,
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

        span0 = SpanSidecar.load(tmp_path / "raw" / "test-doc.spans.json").spans[0]
        assert span0.heading_path == expected.normalized.headings == ()
        assert span0.offset == expected.normalized.offset
        assert span0.page_no == expected.normalized.page_no
        assert_span_identity_matches_direct_chain(span0, expected)


class TestSerializerNoRootDocItemsLift:
    """HIGH-2 regression: Mapping-node root ``doc_items`` must not be lifted into metadata."""

    def test_mapping_node_root_doc_items_not_lifted_into_sidecar(
        self, tmp_path: Path
    ) -> None:
        """Mapping root doc_items must not enter the metadata-only direct chain."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()
        raw_text = "Mapping body with root doc_items but empty metadata."
        node: dict[str, Any] = {
            "text": raw_text,
            "metadata": {},
            "doc_items": [
                {"prov": [{"page_no": 7, "charspan": [42, 142]}], "label": "text"}
            ],
        }
        expected = build_direct_chain_expectation(
            metadata=node["metadata"],
            raw_text=raw_text,
            doc_id=doc_id,
            version_id=version_id,
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

        span0 = SpanSidecar.load(tmp_path / "raw" / "test-doc.spans.json").spans[0]
        assert expected.normalized.page_no is None
        assert expected.normalized.offset == 0
        assert span0.page_no == expected.normalized.page_no is None
        assert span0.offset == expected.normalized.offset == 0
        assert_span_identity_matches_direct_chain(span0, expected)

    def test_mapping_node_metadata_doc_items_still_flattened(
        self, tmp_path: Path
    ) -> None:
        """doc_items in mapping metadata must remain on the flattening path."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()
        raw_text = "Mapping body with doc_items inside metadata."
        metadata = {
            "doc_items": [
                {"prov": [{"page_no": 3, "charspan": [10, 110]}], "label": "text"}
            ],
        }
        node: dict[str, Any] = {"text": raw_text, "metadata": metadata}
        expected = build_direct_chain_expectation(
            metadata=metadata, raw_text=raw_text, doc_id=doc_id, version_id=version_id
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

        span0 = SpanSidecar.load(tmp_path / "raw" / "test-doc.spans.json").spans[0]
        assert span0.page_no == expected.normalized.page_no == 3
        assert span0.offset == expected.normalized.offset == 10
        assert_span_identity_matches_direct_chain(span0, expected)


def test_serialize_document_fails_closed_before_publish_for_duplicate_span_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serializer admission must reject deterministic UUID collisions before I/O."""
    import llamaindex_runtime.okf.serializer as serializer

    raw = tmp_path / "raw"
    raw.mkdir()
    old_markdown = raw / "collision.md"
    old_sidecar = raw / "collision.spans.json"
    old_manifest = raw / "collision.pair.json"
    old_markdown.write_bytes(b"old-markdown")
    old_sidecar.write_bytes(b"old-sidecar")
    old_manifest.write_bytes(b"old-manifest")
    published = False

    def publish_should_not_run(**_: object) -> None:
        nonlocal published
        published = True

    monkeypatch.setattr(serializer, "publish_raw_pair", publish_should_not_run)
    duplicate_metadata = make_docling_metadata_with_nested_prov(page_no=2, offset=7)

    with pytest.raises(
        ValueError, match="^sidecar contains duplicate persisted span identity$"
    ):
        serializer.serialize_document(
            [
                FakeDoclingNode("same normalized text", duplicate_metadata),
                FakeDoclingNode("same normalized text", duplicate_metadata),
            ],
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="collision",
        )

    assert not published
    assert old_markdown.read_bytes() == b"old-markdown"
    assert old_sidecar.read_bytes() == b"old-sidecar"
    assert old_manifest.read_bytes() == b"old-manifest"
