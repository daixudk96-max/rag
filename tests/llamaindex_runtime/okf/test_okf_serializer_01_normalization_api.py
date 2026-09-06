"""Normalization-contract and public-API tests for the OKF serializer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ._serializer_testkit import (
    FakeDoclingNode,
    make_docling_metadata_with_nested_prov,
    make_normalize_spy,
)


class TestSerializerUsesNormalizationContract:
    """The serializer MUST import and call NormalizationContract.normalize."""

    def test_serialize_document_calls_normalization_contract_normalize(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """serialize_document must call NormalizationContract.normalize (spy proof)."""
        from llamaindex_runtime.okf import serializer

        normalize_calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "llamaindex_runtime.ingestion.normalization.NormalizationContract.normalize",
            make_normalize_spy(normalize_calls),
        )
        doc_id = uuid4()
        version_id = uuid4()
        node = FakeDoclingNode(
            text="Test paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        serializer.serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert (
            len(normalize_calls) >= 1
        ), "NormalizationContract.normalize must be called"

    def test_serializer_does_not_define_normalize_method(self) -> None:
        """Verify no normalize method is defined in serializer module (import-only)."""
        from llamaindex_runtime.okf import serializer

        assert not hasattr(serializer, "normalize") or not callable(
            getattr(serializer, "normalize", None)
        )


class TestSerializerUsesDoclingIngestorFlattenMetadata:
    """The serializer must use the same flattening logic as DoclingIngestor."""

    def test_serialize_document_flattens_nested_prov(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nested prov must be flattened (spy on flattening)."""
        from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
        from llamaindex_runtime.okf import serializer

        flatten_calls: list[dict[str, Any]] = []
        original_flatten = DoclingIngestor._flatten_docling_metadata

        def spy_flatten(metadata: dict[str, Any]) -> dict[str, Any]:
            flatten_calls.append(metadata)
            return original_flatten(metadata)

        monkeypatch.setattr(
            DoclingIngestor,
            "_flatten_docling_metadata",
            staticmethod(spy_flatten),
        )

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="Test paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=5, offset=100),
        )

        serializer.serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        # Observable proof: flattening was called with nested prov
        assert len(flatten_calls) >= 1


class TestSerializeDocumentApi:
    """Verify the serialize_document function signature and return type."""

    def test_serialize_document_exists_and_callable(self) -> None:
        """serialize_document must be a callable."""
        from llamaindex_runtime.okf.serializer import serialize_document

        assert callable(serialize_document)

    def test_serialize_document_returns_frozen_dataclass(self, tmp_path: Path) -> None:
        """serialize_document returns a frozen dataclass (SerializedRawFile)."""
        from llamaindex_runtime.okf.serializer import serialize_document

        doc_id = uuid4()
        version_id = uuid4()

        node = FakeDoclingNode(
            text="First paragraph.",
            metadata=make_docling_metadata_with_nested_prov(page_no=1, offset=0),
        )

        result = serialize_document(
            [node],
            doc_id=str(doc_id),
            version_id=str(version_id),
            source_checksum="a" * 64,
            docling_version="2.45.0",
            bundle_root=tmp_path,
            name="test-doc",
        )

        assert is_dataclass(result)
        with pytest.raises(FrozenInstanceError):
            result.span_count = 999  # type: ignore[misc, union-attr]

    def test_serialize_document_requires_doc_id_kwarg(self, tmp_path: Path) -> None:
        """doc_id is a required kwarg (UUID string)."""
        from llamaindex_runtime.okf.serializer import serialize_document

        node = FakeDoclingNode(text="Test", metadata={})

        with pytest.raises(TypeError, match="doc_id"):
            serialize_document(  # type: ignore[call-arg]
                [node],
                version_id=str(uuid4()),
                source_checksum="a" * 64,
                docling_version="2.45.0",
                bundle_root=tmp_path,
                name="test-doc",
            )

    def test_serialize_document_requires_version_id_kwarg(self, tmp_path: Path) -> None:
        """version_id is a required kwarg (UUID string)."""
        from llamaindex_runtime.okf.serializer import serialize_document

        node = FakeDoclingNode(text="Test", metadata={})

        with pytest.raises(TypeError, match="version_id"):
            serialize_document(  # type: ignore[call-arg]
                [node],
                doc_id=str(uuid4()),
                source_checksum="a" * 64,
                docling_version="2.45.0",
                bundle_root=tmp_path,
                name="test-doc",
            )
