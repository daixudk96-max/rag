"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._parser_completion_testkit import _make_raw_md_content, _make_sidecar
from .raw_pair_testkit import bind_raw_bytes, refresh_raw_manifest


class TestParserIncrementalSync:
    """Parser sync: unchanged canonical_hash -> skip; changed -> resync."""

    def test_unchanged_hash_results_in_skip(self, tmp_path: Path) -> None:
        """Unchanged canonical hash must result in 'skipped' status."""
        from llamaindex_runtime.okf.parser import SyncDecision, compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "a" * 64

        previous_state = {
            "doc_id": doc_id,
            "canonical_hash": current_hash,
            "okf_file_path": "raw/test.md",
        }

        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/test.md",
            current_canonical_hash=current_hash,
            previous_state=previous_state,
        )

        assert isinstance(decision, SyncDecision)
        assert decision.status == "skipped"
        assert decision.doc_id == doc_id
        assert decision.canonical_hash == current_hash
        assert decision.okf_file_path == "raw/test.md"

    def test_changed_hash_results_in_resynced(self, tmp_path: Path) -> None:
        """Changed canonical hash must result in 'resynced' status."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "b" * 64

        previous_state = {
            "doc_id": doc_id,
            "canonical_hash": "a" * 64,
            "okf_file_path": "raw/test.md",
        }

        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/test.md",
            current_canonical_hash=current_hash,
            previous_state=previous_state,
        )

        assert decision.status == "resynced"
        assert decision.doc_id == doc_id

    def test_new_file_results_in_synced(self, tmp_path: Path) -> None:
        """File with no previous state must result in 'synced' status."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "a" * 64

        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/new.md",
            current_canonical_hash=current_hash,
            previous_state=None,
        )

        assert decision.status == "synced"
        # FROZEN CONTRACT: New files preserve supplied identity (not empty)
        assert decision.doc_id == doc_id
        assert decision.okf_file_path == "raw/new.md"


class TestSyncDecisionIdentityPreservation:
    """Sync decisions preserve current identity (doc_id, path) in all statuses."""

    def test_synced_preserves_supplied_identity(self, tmp_path: Path) -> None:
        """New file (previous_state=None) preserves supplied doc_id and path."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/newfile.md",
            current_canonical_hash="a" * 64,
            previous_state=None,
        )

        assert decision.status == "synced"
        assert decision.doc_id == doc_id, "synced must preserve supplied doc_id"
        assert (
            decision.okf_file_path == "raw/newfile.md"
        ), "synced must preserve supplied path"

    def test_skipped_preserves_supplied_identity(self, tmp_path: Path) -> None:
        """Unchanged file preserves supplied current identity."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "a" * 64

        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/same.md",
            current_canonical_hash=current_hash,
            previous_state={
                "doc_id": "old-doc-id",  # Previous state has different identity
                "canonical_hash": current_hash,
                "okf_file_path": "raw/old-path.md",
            },
        )

        assert decision.status == "skipped"
        # Current identity is preserved (previous state only used for hash comparison)
        assert decision.doc_id == doc_id, "skipped must preserve current doc_id"
        assert (
            decision.okf_file_path == "raw/same.md"
        ), "skipped must preserve current path"

    def test_resynced_preserves_supplied_identity(self, tmp_path: Path) -> None:
        """Changed file preserves supplied current identity."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "b" * 64

        decision = compute_sync_decision(
            doc_id=doc_id,
            okf_file_path="raw/changed.md",
            current_canonical_hash=current_hash,
            previous_state={
                "doc_id": "old-doc-id",
                "canonical_hash": "a" * 64,
                "okf_file_path": "raw/old-path.md",
            },
        )

        assert decision.status == "resynced"
        assert decision.doc_id == doc_id, "resynced must preserve current doc_id"
        assert (
            decision.okf_file_path == "raw/changed.md"
        ), "resynced must preserve current path"

    def test_keyword_only_signature_enforced(self, tmp_path: Path) -> None:
        """compute_sync_decision must require keyword-only arguments."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        doc_id = str(uuid4())
        current_hash = "a" * 64

        # Positional args must raise TypeError
        with pytest.raises(TypeError, match="keyword|positional"):
            compute_sync_decision(doc_id, "raw/test.md", current_hash, None)  # type: ignore[misc]


class TestParserDeleteDetection:
    """Parser detects files removed from bundle."""

    def test_deleted_paths_returns_frozenset(self, tmp_path: Path) -> None:
        """compute_deleted_paths must return frozenset of deleted paths."""
        from llamaindex_runtime.okf.parser import compute_deleted_paths

        previous_paths = {"raw/doc1.md", "raw/doc2.md", "raw/doc3.md"}
        current_paths = {"raw/doc1.md", "raw/doc3.md"}

        deleted = compute_deleted_paths(previous_paths, current_paths)

        assert isinstance(deleted, frozenset)
        assert deleted == frozenset({"raw/doc2.md"})

    def test_all_files_present_returns_empty_frozenset(self, tmp_path: Path) -> None:
        """When all previous paths exist, return empty frozenset."""
        from llamaindex_runtime.okf.parser import compute_deleted_paths

        previous_paths = {"raw/doc1.md", "raw/doc2.md"}
        current_paths = {"raw/doc1.md", "raw/doc2.md", "raw/doc3.md"}

        deleted = compute_deleted_paths(previous_paths, current_paths)

        assert deleted == frozenset()

    def test_compute_deleted_paths_accepts_abstract_set(self, tmp_path: Path) -> None:
        """compute_deleted_paths must accept any AbstractSet (set, frozenset)."""
        from collections.abc import Set as AbstractSet

        from llamaindex_runtime.okf.parser import compute_deleted_paths

        previous: AbstractSet[str] = frozenset({"raw/a.md", "raw/b.md"})
        current: AbstractSet[str] = frozenset({"raw/a.md"})

        deleted = compute_deleted_paths(previous, current)

        assert deleted == frozenset({"raw/b.md"})


class TestMalformedYamlHandling:
    """Malformed YAML: bundle scan counts it; explicit parse_document fails fast."""

    def test_bundle_malformed_yaml_outside_raw_counted(self, tmp_path: Path) -> None:
        """Malformed YAML in entities/ (outside raw/) must be counted as malformed."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)

        # Valid entity file
        (tmp_path / "entities" / "valid.md").write_text(
            "---\ntype: legacy_entity\ntitle: Valid\n---\n\nEntity.\n", encoding="utf-8"
        )

        # Malformed YAML in entities/ (NOT in raw/)
        (tmp_path / "entities" / "bad.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nContent.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)

        # 1 parsed (valid.md), 1 skipped + 1 malformed (bad.md)
        assert result.stats.parsed == 1, f"Expected 1 parsed, got {result.stats.parsed}"
        assert (
            result.stats.malformed == 1
        ), f"Expected 1 malformed, got {result.stats.malformed}"
        assert (
            result.stats.skipped == 1
        ), f"Expected 1 skipped, got {result.stats.skipped}"
        assert len(result) == 1, "Only the valid doc should be in the result list"

    def test_explicit_parse_document_fails_fast_on_malformed_yaml_outside_raw(
        self, tmp_path: Path
    ) -> None:
        """Explicit parse_document must raise on malformed YAML even outside raw/."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "bad.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nContent.\n", encoding="utf-8"
        )

        parser = OKFParser()
        # Explicit parse_document is fail-fast - must raise, not silently return type=unknown
        with pytest.raises(ValueError, match="(?i)yaml|frontmatter|parse"):
            parser.parse_document(tmp_path / "entities" / "bad.md", tmp_path)

    def test_bundle_malformed_yaml_does_not_produce_unknown_type_doc(
        self, tmp_path: Path
    ) -> None:
        """Malformed YAML must NOT silently parse as a type=unknown document."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "bad.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nContent.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)

        # No document with type "unknown" should leak through from malformed YAML
        for doc in result:
            assert (
                doc.frontmatter.type != "unknown"
            ), "Malformed YAML must not silently produce a type=unknown document"


class TestDeterministicDocumentOrder:
    """parse_bundle must return documents in deterministic sorted order."""

    def test_bundle_returns_documents_in_sorted_path_order(
        self, tmp_path: Path
    ) -> None:
        """Documents must be returned in sorted path order for determinism."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)

        # Create files in non-sorted order (zebra first, alpha last)
        for name in ["zebra.md", "alpha.md", "mango.md"]:
            (tmp_path / "entities" / name).write_text(
                f"---\ntype: legacy_entity\ntitle: {name}\n---\n\nContent.\n",
                encoding="utf-8",
            )

        result = OKFParser().parse_bundle(tmp_path)

        titles = [doc.frontmatter.title for doc in result]
        assert titles == [
            "alpha.md",
            "mango.md",
            "zebra.md",
        ], f"Expected sorted order, got {titles}"


class TestCanonicalPosixPaths:
    """okf_file_path must use POSIX separators for OS-independent sync state."""

    def test_okf_file_path_uses_posix_separators(self, tmp_path: Path) -> None:
        """okf_file_path must use forward slashes regardless of OS."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "doc.md").write_text(
            "---\ntype: legacy_entity\ntitle: Doc\n---\n\nContent.\n", encoding="utf-8"
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "doc.md", tmp_path)

        # Must be POSIX (forward slash), never backslash
        assert "\\" not in (
            doc.frontmatter.okf_file_path or ""
        ), f"okf_file_path must be POSIX, got {doc.frontmatter.okf_file_path!r}"
        assert doc.frontmatter.okf_file_path == "entities/doc.md"


class TestRawDirectoryBoundary:
    """Only the bundle-root top-level raw/ directory enforces raw typing."""

    def test_nested_raw_directory_not_treated_as_raw(self, tmp_path: Path) -> None:
        """A file under entities/raw/ must NOT trigger raw-directory enforcement."""
        from llamaindex_runtime.okf.parser import OKFParser

        # entities/raw/ is NOT the bundle-root top-level raw/
        (tmp_path / "entities" / "raw").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "raw" / "doc.md").write_text(
            "---\ntype: legacy_entity\ntitle: Nested\n---\n\nContent.\n",
            encoding="utf-8",
        )

        parser = OKFParser()
        # This must NOT raise - the file is not in the bundle-root top-level raw/
        doc = parser.parse_document(tmp_path / "entities" / "raw" / "doc.md", tmp_path)
        assert doc.frontmatter.type == "legacy_entity"

    def test_top_level_raw_directory_enforced(self, tmp_path: Path) -> None:
        """A file directly under bundle-root raw/ must declare type: raw."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
        raw_path = tmp_path / "raw" / "doc.md"
        raw_path.write_text(
            "---\ntype: legacy_entity\ntitle: Bad\n---\n\nContent.\n", encoding="utf-8"
        )
        bind_raw_bytes(
            raw_path, SpanSidecar(1, str(uuid4()), str(uuid4()), ()).to_bytes()
        )

        parser = OKFParser()
        with pytest.raises(ValueError, match="type"):
            parser.parse_document(tmp_path / "raw" / "doc.md", tmp_path)


class TestOKFDocumentCanonicalHash:
    """OKFDocument must expose canonical_hash for sync decisions."""

    def test_raw_document_has_canonical_hash(self, tmp_path: Path) -> None:
        """Raw OKFDocument must have canonical_hash attribute."""

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
        md_content = _make_raw_md_content(fm, body="Test paragraph.")
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        # OKFDocument must expose canonical_hash
        assert hasattr(doc, "canonical_hash"), "OKFDocument must have canonical_hash"
        assert doc.canonical_hash is not None
        assert len(doc.canonical_hash) == 64  # SHA256 hex length


class TestBundleParsingReservedFiles:
    """Parser must skip reserved files (index.md, log.md) at all depths."""

    def test_bundle_skips_index_and_log_md(self, tmp_path: Path) -> None:
        """index.md and log.md must be skipped at all depths."""
        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)

        (tmp_path / "index.md").write_text(
            "---\nokf_version: '0.1'\n---\n\n# Index\n", encoding="utf-8"
        )
        (tmp_path / "log.md").write_text(
            "## 2026-07-14\n\nChanges.\n", encoding="utf-8"
        )

        doc_id = str(uuid4())
        (tmp_path / "entities" / "entity1.md").write_text(
            f"---\ntype: legacy_entity\ndoc_id: {doc_id}\n---\n\nEntity.\n",
            encoding="utf-8",
        )
        (tmp_path / "entities" / "index.md").write_text(
            "---\n---\nSubdir index.\n", encoding="utf-8"
        )

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        docs = parser.parse_bundle(tmp_path)

        assert len(docs) == 1
        assert docs[0].frontmatter.type == "legacy_entity"


class TestBundleMalformedFileHandling:
    """Malformed files in bundle scan: skip + stats (not crash)."""

    def test_bundle_malformed_file_skipped_with_stats(self, tmp_path: Path) -> None:
        """Malformed files in bundle scan must be skipped with stats."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)

        # Valid raw file with matching sidecar
        doc_id = str(uuid4())
        version_id = str(uuid4())  # SAME version_id for both
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        (tmp_path / "raw" / "valid.md").write_text(
            _make_raw_md_content(fm), encoding="utf-8"
        )
        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(tmp_path / "raw" / "valid.spans.json")
        refresh_raw_manifest(tmp_path / "raw" / "valid.md")

        # Malformed file (invalid YAML)
        (tmp_path / "raw" / "malformed.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nContent.\n", encoding="utf-8"
        )

        parser = OKFParser()
        docs = parser.parse_bundle(tmp_path)

        # parse_bundle returns list[OKFDocument] by default
        # Stats available via parser.last_bundle_stats (additive API)
        assert len(docs) >= 1, "At least one valid document must parse"

        # Verify stats are available and correct
        assert hasattr(
            parser, "last_bundle_stats"
        ), "Parser must expose last_bundle_stats"
        stats = parser.last_bundle_stats
        assert (
            stats is not None
        ), "last_bundle_stats must be populated after parse_bundle"
        assert stats.parsed >= 1, f"parsed >= 1, got {stats.parsed}"
        assert stats.malformed >= 1, f"malformed >= 1, got {stats.malformed}"


class TestLegacyParagraphParsing:
    """Legacy split("\\n\\n") paragraph behavior preserved for non-raw files."""

    def test_non_raw_file_uses_legacy_paragraph_split(self, tmp_path: Path) -> None:
        """Non-raw files must use split("\\n\\n") paragraph parsing."""
        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)

        content = (
            "---\ntype: legacy_entity\n---\n\nPara one.\n\nPara two.\n\nPara three.\n"
        )
        (tmp_path / "entities" / "entity1.md").write_text(content, encoding="utf-8")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(tmp_path / "entities" / "entity1.md", tmp_path)

        assert len(doc.paragraphs) == 3
        assert "Para one" in doc.paragraphs[0].content

    def test_raw_file_bypasses_legacy_paragraph_split(self, tmp_path: Path) -> None:
        """Raw files must NOT use legacy paragraph splitting (spans are authoritative)."""
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
        md_content = _make_raw_md_content(
            fm, body="Para one.\n\nPara two.\n\nPara three."
        )
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        # Raw files: spans are authoritative from sidecar, not body-derived
        assert len(doc.spans) >= 1
        # Legacy paragraph splitting should NOT be applied to raw files
        assert doc.paragraphs == [], "Raw files must not use legacy paragraph splitting"

    def test_okf_paragraph_constructor_preserved(self, tmp_path: Path) -> None:
        """OKFParagraph(id, content, heading, okf_file_path) must work unchanged."""
        from llamaindex_runtime.okf.parser import OKFParagraph

        para = OKFParagraph(
            id="P1",
            content="Test",
            heading="Intro",
            okf_file_path="entities/test.md",
        )

        assert para.id == "P1"
        assert para.content == "Test"


class TestReservedSlugBoundary:
    """Files named index.md or log.md are reserved and skipped even in raw/."""

    def test_raw_file_named_index_md_skipped(self, tmp_path: Path) -> None:
        """index.md in raw/ must be skipped (reserved name)."""
        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)

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
        (tmp_path / "raw" / "index.md").write_text(
            _make_raw_md_content(fm), encoding="utf-8"
        )
        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(tmp_path / "raw" / "index.spans.json")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        docs = parser.parse_bundle(tmp_path)

        # index.md must be skipped
        assert len(docs) == 0

    def test_raw_file_named_log_md_skipped(self, tmp_path: Path) -> None:
        """log.md in raw/ must be skipped (reserved name)."""
        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)

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
        (tmp_path / "raw" / "log.md").write_text(
            _make_raw_md_content(fm), encoding="utf-8"
        )
        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(tmp_path / "raw" / "log.spans.json")

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        docs = parser.parse_bundle(tmp_path)

        # log.md must be skipped
        assert len(docs) == 0


class TestSpansUseSpanRecord:
    """OKFDocument.spans should use SpanRecord for raw files."""

    def test_spans_are_spanrecord_instances(self, tmp_path: Path) -> None:
        """Raw file spans must be SpanRecord instances."""

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
        md_content = _make_raw_md_content(fm, body="Test paragraph.")
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")

        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        from llamaindex_runtime.okf.parser import OKFParser

        parser = OKFParser()
        doc = parser.parse_document(md_path, tmp_path)

        assert len(doc.spans) >= 1
        # Spans should be SpanRecord instances (from sidecar)
        assert isinstance(
            doc.spans[0], SpanRecord
        ), f"Expected SpanRecord, got {type(doc.spans[0])}"
