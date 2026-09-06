"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanSidecar

from ._parser_completion_testkit import _make_raw_md_content, _make_sidecar
from .raw_pair_testkit import bind_raw_bytes, refresh_raw_manifest


class TestParserSidecarReading:
    """Parser reads sidecar; span identity is sidecar-sourced, not body-derived."""

    def test_raw_file_with_sidecar_exposes_spans_tuple(self, tmp_path: Path) -> None:
        """Raw file with sidecar must expose spans tuple on OKFDocument."""
        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm, body="Reflowed paragraph text.")
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        # Create sidecar with coordinates that differ from body
        sidecar = _make_sidecar(
            doc_id=doc_id,
            version_id=version_id,
            spans=[
                {
                    "span_id": str(uuid4()),
                    "page_no": 5,
                    "heading_path": ["Chapter", "Section"],
                    "offset": 999,
                    "text": "Original paragraph text.",
                }
            ],
        )
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        # Parse the document
        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        # FROZEN API: OKFDocument.spans is tuple[SpanRecord, ...]
        assert hasattr(doc, "spans"), "OKFDocument must have spans attribute"
        assert isinstance(doc.spans, tuple), "spans must be a tuple"
        assert len(doc.spans) == 1

        span = doc.spans[0]
        assert span.page_no == 5
        assert span.heading_path == ("Chapter", "Section")
        assert span.offset == 999
        assert span.text == "Original paragraph text."

    def test_markdown_reflow_preserves_canonical_hash_differs_from_source_hash(
        self, tmp_path: Path
    ) -> None:
        """Body reflow: canonical_hash unchanged, source_checksum changed (dual hash)."""
        from llamaindex_runtime.okf.canonical_hash import canonical_hash

        doc_id = str(uuid4())
        version_id = str(uuid4())

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)

        # Original raw file
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content1 = _make_raw_md_content(fm, body="Original text.")
        md_path1 = tmp_path / "v1" / "raw" / "test.md"
        md_path1.parent.mkdir(parents=True, exist_ok=True)
        md_path1.write_text(md_content1, encoding="utf-8")
        sidecar.dump(md_path1.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path1)

        # Reflowed raw file (same frontmatter, same sidecar, different body)
        md_content2 = _make_raw_md_content(
            fm, body="Reflowed text with different content."
        )
        md_path2 = tmp_path / "v2" / "raw" / "test.md"
        md_path2.parent.mkdir(parents=True, exist_ok=True)
        md_path2.write_text(md_content2, encoding="utf-8")
        sidecar.dump(md_path2.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path2)

        # Load both and verify canonical hash equality
        loaded1 = SpanSidecar.load(md_path1.with_suffix(".spans.json"))
        loaded2 = SpanSidecar.load(md_path2.with_suffix(".spans.json"))

        canonical1 = canonical_hash(fm, loaded1)
        canonical2 = canonical_hash(fm, loaded2)

        assert canonical1 == canonical2, "Canonical hash must not change on body reflow"

        # Source raw-byte hash MUST differ (different file contents)
        source_hash1 = md_path1.read_bytes()
        source_hash2 = md_path2.read_bytes()
        assert source_hash1 != source_hash2, "Source bytes must differ after reflow"


class TestParserFrontmatterValidation:
    """Parser validates raw frontmatter fail-fast via RawFrontmatterContract."""

    def test_raw_file_missing_doc_id_raises_named_error(self, tmp_path: Path) -> None:
        """Missing doc_id must raise ValueError naming the field."""
        fm = {
            "type": "raw",
            # doc_id missing
            "version_id": str(uuid4()),
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        bind_raw_bytes(
            md_path,
            SpanSidecar(1, str(uuid4()), fm["version_id"], ()).to_bytes(),
        )

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        with pytest.raises(ValueError, match="doc_id"):
            parser.parse_document(md_path, tmp_path)

    def test_raw_file_missing_adjacent_sidecar_raises_named_error(
        self, tmp_path: Path
    ) -> None:
        """Raw file without adjacent sidecar must raise ValueError naming sidecar."""
        doc_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": str(uuid4()),
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        bind_raw_bytes(md_path, b"placeholder", write_sidecar=False)
        # NO sidecar created

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        with pytest.raises(ValueError, match="sidecar"):
            parser.parse_document(md_path, tmp_path)

    def test_raw_file_invalid_sidecar_json_raises_named_error(
        self, tmp_path: Path
    ) -> None:
        """Raw file with malformed sidecar JSON must raise ValueError naming sidecar."""
        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        # Write invalid JSON sidecar
        sidecar_path = md_path.with_suffix(".spans.json")
        bind_raw_bytes(md_path, b"{invalid json")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        with pytest.raises(ValueError) as exc_info:
            parser.parse_document(md_path, tmp_path)

        assert str(exc_info.value) == "sidecar contains invalid JSON"
        assert str(sidecar_path) not in str(exc_info.value)

    def test_raw_file_sidecar_doc_id_mismatch_raises_named_error(
        self, tmp_path: Path
    ) -> None:
        """Sidecar doc_id mismatch with frontmatter must raise ValueError."""
        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        # Create sidecar with DIFFERENT doc_id
        sidecar = _make_sidecar(doc_id=str(uuid4()), version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        with pytest.raises(ValueError, match="doc_id"):
            parser.parse_document(md_path, tmp_path)

    def test_raw_file_sidecar_version_id_mismatch_raises_named_error(
        self, tmp_path: Path
    ) -> None:
        """Sidecar version_id mismatch with frontmatter must raise ValueError."""
        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        # Create sidecar with DIFFERENT version_id
        sidecar = _make_sidecar(doc_id=doc_id, version_id=str(uuid4()))
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        with pytest.raises(ValueError, match="version_id"):
            parser.parse_document(md_path, tmp_path)

    def test_non_raw_file_in_entities_parses_without_raw_validation(
        self, tmp_path: Path
    ) -> None:
        """Non-raw file in entities/ parses without RawFrontmatterContract validation."""
        fm = {
            "type": "legacy_entity",  # Not raw
            "doc_id": str(uuid4()),
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "entities" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)
        assert doc.frontmatter.type == "legacy_entity"

    def test_raw_file_type_entity_in_raw_directory_fails(self, tmp_path: Path) -> None:
        """File in raw/ directory with type: legacy_entity must fail (type must be raw)."""
        doc_id = str(uuid4())
        version_id = str(uuid4())

        # Create file with type: legacy_entity in raw/ directory - MUST FAIL
        fm = {
            "type": "entity",  # Wrong type for raw/ directory
            "doc_id": doc_id,
            "version_id": version_id,
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "entity-in-raw.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        bind_raw_bytes(md_path, SpanSidecar(1, doc_id, version_id, ()).to_bytes())

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        # MUST raise ValueError - files in raw/ must have type: raw
        with pytest.raises(ValueError, match="type"):
            parser.parse_document(md_path, tmp_path)


class TestParserUnknownFieldFidelity:
    """Parser must preserve unknown frontmatter fields without silent drops."""

    def test_unknown_top_level_frontmatter_field_preserved(
        self, tmp_path: Path
    ) -> None:
        """Unknown top-level frontmatter field must be preserved."""
        doc_id = str(uuid4())
        version_id = str(uuid4())

        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
            "custom_future_field": "preserved-value",  # Unknown top-level field
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        # Unknown field preserved in extra_fields (additive API)
        assert hasattr(doc.frontmatter, "extra_fields")
        assert (
            doc.frontmatter.extra_fields.get("custom_future_field") == "preserved-value"
        )

    def test_relation_unknown_qualifier_preserved(self, tmp_path: Path) -> None:
        """Unknown relation qualifier field must be preserved."""
        doc_id = str(uuid4())
        version_id = str(uuid4())

        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
            "relations": [
                {
                    "target": "entity-123",
                    "relation_type": "mentions",
                    "negation": False,
                    "time_range": "2024-01-01..2024-12-31",  # Unknown qualifier
                }
            ],
        }
        md_content = _make_raw_md_content(fm)
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        relations = doc.frontmatter.relations
        assert len(relations) == 1
        assert relations[0]["time_range"] == "2024-01-01..2024-12-31"

    def test_entity_file_unknown_relation_qualifier_preserved(
        self, tmp_path: Path
    ) -> None:
        """Entity-type file with unknown relation qualifier must preserve it.

        This test uses type: legacy_entity (not raw) to independently verify that
        relation qualifier passthrough works for non-raw entity frontmatter
        per 14-03 PLAN:139 (entity-type frontmatter with relations).
        No sidecar required for entity files.
        """
        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)

        # Entity file with known and unknown relation qualifiers
        fm = {
            "type": "legacy_entity",
            "doc_id": str(uuid4()),
            "relations": [
                {
                    "target": "person-alice",
                    "relation_type": "mentions",
                    "negation": True,  # Known qualifier
                    "confidence": 0.95,  # Known qualifier
                    "temporal_range": "2024-01-01..2024-06-30",  # Unknown qualifier
                    "source_sentence": "Alice was mentioned.",  # Unknown qualifier
                }
            ],
        }
        md_content = _make_raw_md_content(fm, body="Entity content.")
        md_path = tmp_path / "entities" / "person.md"
        md_path.write_text(md_content, encoding="utf-8")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        # Verify entity file parsed correctly
        assert doc.frontmatter.type == "legacy_entity"

        # Verify all relation qualifiers preserved (no silent drops)
        relations = doc.frontmatter.relations
        assert len(relations) == 1
        rel = relations[0]
        assert rel["target"] == "person-alice"
        assert rel["relation_type"] == "mentions"
        assert rel["negation"] is True  # Known qualifier preserved
        assert rel["confidence"] == 0.95  # Known qualifier preserved
        assert rel["temporal_range"] == "2024-01-01..2024-06-30"  # Unknown preserved
        assert rel["source_sentence"] == "Alice was mentioned."  # Unknown preserved
