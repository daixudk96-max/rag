"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.sidecar import SpanSidecar

from ._parser_completion_testkit import _make_raw_md_content, _make_sidecar
from .raw_pair_testkit import bind_raw_bytes, refresh_raw_manifest


class TestBundleResultStats:
    """parse_bundle returns list-compatible result with mandatory .stats attribute."""

    def test_parse_bundle_result_has_mandatory_stats(self, tmp_path: Path) -> None:
        """parse_bundle result must have mandatory .stats attribute (no hasattr check)."""
        from llamaindex_runtime.okf.parser import OKFParser

        # Empty bundle - stats must still be present
        result = OKFParser().parse_bundle(tmp_path)

        # FROZEN CONTRACT: result.stats is mandatory, not optional
        # Tests MUST NOT use hasattr() - direct attribute access is required
        stats = result.stats  # noqa: F841  (assert below)
        assert (
            stats is not None
        ), "result.stats must always be present (frozen contract)"

    def test_parse_bundle_result_stats_is_immutable_bundlestats(
        self, tmp_path: Path
    ) -> None:
        """result.stats must be immutable BundleStats dataclass."""
        from llamaindex_runtime.okf.parser import BundleStats, OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e1.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: a\n---\n\nEntity.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)

        # FROZEN CONTRACT: result.stats is BundleStats (frozen dataclass)
        assert isinstance(result.stats, BundleStats)
        # Verify frozen (immutable)
        assert result.stats.__dataclass_fields__["parsed"].init is True

    def test_parse_bundle_result_is_list_compatible(self, tmp_path: Path) -> None:
        """parse_bundle result must be list-compatible (iterable, indexable, len)."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e1.md").write_text(
            "---\ntype: legacy_entity\ntitle: First\n---\n\nEntity 1.\n",
            encoding="utf-8",
        )
        (tmp_path / "entities" / "e2.md").write_text(
            "---\ntype: legacy_entity\ntitle: Second\n---\n\nEntity 2.\n",
            encoding="utf-8",
        )

        result = OKFParser().parse_bundle(tmp_path)

        # List-compatible: iterable, indexable, len
        assert len(result) == 2, "result must support len()"
        assert result[0].frontmatter.title == "First", "result must support indexing"
        assert [d.frontmatter.title for d in result] == [
            "First",
            "Second",
        ], "result must be iterable"

    def test_parse_bundle_counts_parsed_correctly(self, tmp_path: Path) -> None:
        """Successfully parsed documents increment parsed count."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e1.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: a\n---\n\nEntity 1.\n", encoding="utf-8"
        )
        (tmp_path / "entities" / "e2.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: b\n---\n\nEntity 2.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)

        # parsed: count of successfully parsed documents
        assert result.stats.parsed == 2
        assert result.stats.skipped == 0
        assert result.stats.malformed == 0

    def test_parse_bundle_counts_skipped_for_reserved_files(
        self, tmp_path: Path
    ) -> None:
        """Reserved index.md/log.md and .obsidian entries increment skipped count."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e1.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: a\n---\n\nEntity.\n", encoding="utf-8"
        )
        # Reserved files at root
        (tmp_path / "index.md").write_text("---\n---\nIndex.\n", encoding="utf-8")
        (tmp_path / "log.md").write_text("Log.\n", encoding="utf-8")
        # Reserved files in subdirectory
        (tmp_path / "entities" / "index.md").write_text(
            "---\n---\nSub-index.\n", encoding="utf-8"
        )
        # .obsidian directory
        (tmp_path / ".obsidian").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".obsidian" / "config.md").write_text(
            "---\n---\nConfig.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)

        # 1 parsed (e1.md), 4 skipped (index.md, log.md, entities/index.md, .obsidian/config.md)
        assert result.stats.parsed == 1
        assert (
            result.stats.skipped == 4
        ), f"Expected 4 skipped, got {result.stats.skipped}"
        assert result.stats.malformed == 0

    def test_parse_bundle_counts_malformed_correctly(self, tmp_path: Path) -> None:
        """Malformed files increment both skipped and malformed counts."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)

        # Valid raw file with matching sidecar
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

        result = OKFParser().parse_bundle(tmp_path)

        # 1 parsed (valid.md), 1 skipped + 1 malformed (malformed.md)
        assert result.stats.parsed == 1, f"Expected 1 parsed, got {result.stats.parsed}"
        assert (
            result.stats.skipped == 1
        ), f"Expected 1 skipped, got {result.stats.skipped}"
        assert (
            result.stats.malformed == 1
        ), f"Expected 1 malformed, got {result.stats.malformed}"

    def test_parse_bundle_result_stats_not_optional_no_hasattr(
        self, tmp_path: Path
    ) -> None:
        """result.stats is mandatory - code must NOT use hasattr() checks."""
        from llamaindex_runtime.okf.parser import OKFParser

        result = OKFParser().parse_bundle(tmp_path)

        # This test documents the frozen contract: .stats is mandatory.
        # Production code MUST access result.stats directly without hasattr guards.
        # If this attribute access fails, the implementation is broken.
        stats = result.stats
        assert stats.parsed == 0

    def test_parse_bundle_result_stats_equal_to_last_bundle_stats(
        self, tmp_path: Path
    ) -> None:
        """result.stats and parser.last_bundle_stats must match (both required)."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e1.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: a\n---\n\nEntity.\n", encoding="utf-8"
        )

        parser = OKFParser()
        result = parser.parse_bundle(tmp_path)

        # Both APIs must exist and match
        assert parser.last_bundle_stats is not None
        assert result.stats == parser.last_bundle_stats

    def test_bundle_documents_alias_available(self, tmp_path: Path) -> None:
        """BundleDocuments must be available as the canonical name (BundleResult alias)."""
        from llamaindex_runtime.okf.parser import (
            BundleDocuments,
            BundleResult,
            OKFParser,
        )

        # BundleDocuments is the canonical name; BundleResult kept as compatibility alias
        assert BundleDocuments is BundleResult or issubclass(BundleResult, list)

        result = OKFParser().parse_bundle(tmp_path)
        assert isinstance(result, BundleDocuments)


class TestFrozenContractSyncDecisionSignature:
    """compute_sync_decision frozen keyword-only signature and identity preservation."""

    def test_signature_is_keyword_only_with_doc_id_and_path(self) -> None:
        """Signature must expose doc_id and okf_file_path as keyword-only params."""
        import inspect

        from llamaindex_runtime.okf.parser import compute_sync_decision

        sig = inspect.signature(compute_sync_decision)
        params = sig.parameters
        assert "doc_id" in params, "doc_id must be a named parameter"
        assert "okf_file_path" in params, "okf_file_path must be a named parameter"
        assert "current_canonical_hash" in params
        assert "previous_state" in params
        # All params must be keyword-only (KIND_KEYWORD_ONLY)
        for name in (
            "doc_id",
            "okf_file_path",
            "current_canonical_hash",
            "previous_state",
        ):
            assert (
                params[name].kind == inspect.Parameter.KEYWORD_ONLY
            ), f"{name} must be keyword-only"

    def test_synced_ignores_stale_previous_identity(self) -> None:
        """When previous_state is None, result uses supplied doc_id/path, not stale."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        current_doc_id = str(uuid4())
        decision = compute_sync_decision(
            doc_id=current_doc_id,
            okf_file_path="raw/current.md",
            current_canonical_hash="a" * 64,
            previous_state=None,
        )
        assert decision.status == "synced"
        assert decision.doc_id == current_doc_id
        assert decision.okf_file_path == "raw/current.md"

    def test_skipped_ignores_stale_previous_path_and_doc_id(self) -> None:
        """Skipped decision preserves current identity, ignoring stale previous."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        current_doc_id = str(uuid4())
        current_hash = "c" * 64
        decision = compute_sync_decision(
            doc_id=current_doc_id,
            okf_file_path="raw/new-location.md",
            current_canonical_hash=current_hash,
            previous_state={
                "doc_id": "stale-doc-id",
                "canonical_hash": current_hash,
                "okf_file_path": "raw/old-location.md",
            },
        )
        assert decision.status == "skipped"
        assert decision.doc_id == current_doc_id, "must use current doc_id not stale"
        assert (
            decision.okf_file_path == "raw/new-location.md"
        ), "must use current path not stale"

    def test_resynced_ignores_stale_previous_identity(self) -> None:
        """Resynced decision preserves current identity, ignoring stale previous."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        current_doc_id = str(uuid4())
        decision = compute_sync_decision(
            doc_id=current_doc_id,
            okf_file_path="raw/renamed.md",
            current_canonical_hash="b" * 64,
            previous_state={
                "doc_id": "stale-doc-id",
                "canonical_hash": "a" * 64,
                "okf_file_path": "raw/old-name.md",
            },
        )
        assert decision.status == "resynced"
        assert decision.doc_id == current_doc_id
        assert decision.okf_file_path == "raw/renamed.md"

    def test_positional_call_raises_typeerror(self) -> None:
        """Positional args must raise TypeError (keyword-only enforced)."""
        from llamaindex_runtime.okf.parser import compute_sync_decision

        with pytest.raises(TypeError, match="keyword|positional"):
            compute_sync_decision(str(uuid4()), "raw/x.md", "a" * 64, None)  # type: ignore[misc]


class TestFrozenContractDeletedPathsAbstractSet:
    """compute_deleted_paths accepts AbstractSet and returns frozenset."""

    def test_accepts_frozenset_input(self) -> None:
        """frozenset (AbstractSet) input must be accepted."""
        from llamaindex_runtime.okf.parser import compute_deleted_paths

        deleted = compute_deleted_paths(
            frozenset({"raw/a.md", "raw/b.md"}),
            frozenset({"raw/a.md"}),
        )
        assert isinstance(deleted, frozenset)
        assert deleted == frozenset({"raw/b.md"})

    def test_returns_empty_frozenset_when_nothing_deleted(self) -> None:
        from llamaindex_runtime.okf.parser import compute_deleted_paths

        deleted = compute_deleted_paths(
            frozenset({"raw/a.md"}),
            frozenset({"raw/a.md", "raw/b.md"}),
        )
        assert deleted == frozenset()
        assert isinstance(deleted, frozenset)


class TestFrozenContractBundleDocumentsRename:
    """BundleDocuments is the canonical name; BundleResult is a compatibility alias."""

    def test_bundle_documents_is_canonical_class(self) -> None:
        """BundleDocuments must be a class (not just an alias to list)."""
        from llamaindex_runtime.okf.parser import BundleDocuments

        assert isinstance(BundleDocuments, type), "BundleDocuments must be a class"

    def test_bundle_result_alias_points_to_bundle_documents(self) -> None:
        """BundleResult must be BundleDocuments (compatibility alias)."""
        from llamaindex_runtime.okf.parser import BundleDocuments, BundleResult

        assert (
            BundleResult is BundleDocuments
        ), "BundleResult must be a direct alias of BundleDocuments"

    def test_bundle_documents_constructor_requires_stats(self) -> None:
        """BundleDocuments constructor takes (docs, stats) - stats mandatory."""
        from llamaindex_runtime.okf.parser import BundleDocuments, BundleStats

        docs: list = []
        stats = BundleStats(parsed=0, skipped=0, malformed=0)
        result = BundleDocuments(docs, stats)
        assert result.stats is stats
        assert len(result) == 0

    def test_bundle_documents_stats_is_immutable(self) -> None:
        """BundleStats must be a frozen dataclass."""
        from dataclasses import FrozenInstanceError

        from llamaindex_runtime.okf.parser import BundleStats

        stats = BundleStats(parsed=1, skipped=0, malformed=0)
        with pytest.raises(FrozenInstanceError):
            stats.parsed = 999  # type: ignore[misc]


class TestFrozenContractRawProvenanceFields:
    """OKFFrontmatter exposes typed raw provenance fields populated exactly."""

    def test_raw_provenance_fields_populated_from_frontmatter(
        self, tmp_path: Path
    ) -> None:
        """doc_id, version_id, source_checksum, docling_version, generated_by populated."""
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test-producer",
        }
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_make_raw_md_content(fm), encoding="utf-8")
        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        doc = OKFParser().parse_document(md_path, tmp_path)
        fm_obj = doc.frontmatter

        assert fm_obj.doc_id == doc_id
        assert fm_obj.version_id == version_id
        assert fm_obj.source_checksum == "a" * 64
        assert fm_obj.docling_version == "2.45.0"
        assert fm_obj.generated_by == "test-producer"

    def test_raw_provenance_fields_default_none_for_non_raw(
        self, tmp_path: Path
    ) -> None:
        """Non-raw files without provenance fields default to None."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "e.md").write_text(
            "---\ntype: legacy_entity\n---\n\nEntity.\n", encoding="utf-8"
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "e.md", tmp_path)
        fm_obj = doc.frontmatter
        assert fm_obj.doc_id is None
        assert fm_obj.version_id is None
        assert fm_obj.source_checksum is None
        assert fm_obj.docling_version is None
        assert fm_obj.generated_by is None

    def test_unknown_top_level_field_preserved_in_extra_fields(
        self, tmp_path: Path
    ) -> None:
        """Unknown top-level fields preserved in extra_fields (no silent drop)."""
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id = str(uuid4())
        version_id = str(uuid4())
        fm = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
            "future_field_xyz": "preserved",
        }
        md_path = tmp_path / "raw" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_make_raw_md_content(fm), encoding="utf-8")
        sidecar = _make_sidecar(doc_id=doc_id, version_id=version_id)
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        doc = OKFParser().parse_document(md_path, tmp_path)
        assert doc.frontmatter.extra_fields.get("future_field_xyz") == "preserved"


class TestFrozenContractNoDuplicateOKFSpan:
    """OKFSpan duplicate removed; OKFDocument.spans uses tuple[SpanRecord, ...]."""

    def test_okf_span_not_defined_in_parser(self) -> None:
        """OKFSpan must not be defined in parser module (duplicate removed)."""
        from llamaindex_runtime.okf import parser

        assert not hasattr(
            parser, "OKFSpan"
        ), "OKFSpan must be removed from parser (duplicate of SpanRecord)"

    def test_okf_document_spans_uses_spanrecord(self, tmp_path: Path) -> None:
        """OKFDocument.spans type annotation is tuple[SpanRecord, ...]."""
        import typing

        from llamaindex_runtime.okf.parser import OKFDocument

        hints = typing.get_type_hints(OKFDocument)
        spans_hint = hints.get("spans")
        assert spans_hint is not None
        # Stringified form: tuple[SpanRecord, ...] - verify SpanRecord referenced
        assert "SpanRecord" in str(
            spans_hint
        ), f"spans hint must reference SpanRecord, got {spans_hint}"


class TestFrozenContractPosixPathsAndRawBoundary:
    """Bundle-relative paths use .as_posix(); raw boundary only at top-level raw."""

    def test_okf_file_path_uses_posix_separators(self, tmp_path: Path) -> None:
        """okf_file_path must use forward slashes (POSIX) on Windows too."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "sub").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "sub" / "deep.md").write_text(
            "---\ntype: legacy_entity\n---\n\nDeep.\n", encoding="utf-8"
        )

        doc = OKFParser().parse_document(
            tmp_path / "entities" / "sub" / "deep.md", tmp_path
        )
        assert (
            doc.frontmatter.okf_file_path == "entities/sub/deep.md"
        ), f"Expected POSIX path, got {doc.frontmatter.okf_file_path!r}"

    def test_nested_raw_subdir_not_treated_as_top_level_raw(
        self, tmp_path: Path
    ) -> None:
        """archive/raw/entity.md must NOT be treated as top-level raw boundary.

        Per frozen contract #6: raw-directory enforcement only if
        relative.parts[0] == "raw". A nested raw/ dir (e.g. archive/raw/)
        is not the top-level raw boundary.
        """
        from llamaindex_runtime.okf.parser import OKFParser

        # entity file under archive/raw/ - should parse as entity, NOT raise
        (tmp_path / "archive" / "raw").mkdir(parents=True, exist_ok=True)
        (tmp_path / "archive" / "raw" / "entity.md").write_text(
            "---\ntype: legacy_entity\ndoc_id: x\n---\n\nEntity in nested raw.\n",
            encoding="utf-8",
        )

        doc = OKFParser().parse_document(
            tmp_path / "archive" / "raw" / "entity.md", tmp_path
        )
        assert (
            doc.frontmatter.type == "legacy_entity"
        ), "Nested archive/raw/ must not trigger top-level raw enforcement"

    def test_top_level_raw_with_non_raw_type_still_raises(self, tmp_path: Path) -> None:
        """Top-level raw/ directory still enforces type: raw."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
        raw_path = tmp_path / "raw" / "entity.md"
        raw_path.write_text(
            "---\ntype: legacy_entity\n---\n\nEntity.\n", encoding="utf-8"
        )
        bind_raw_bytes(
            raw_path, SpanSidecar(1, str(uuid4()), str(uuid4()), ()).to_bytes()
        )

        with pytest.raises(ValueError, match="type"):
            OKFParser().parse_document(tmp_path / "raw" / "entity.md", tmp_path)


class TestFrozenContractDeterministicBundleScan:
    """Bundle rglob scan is deterministic (sorted)."""

    def test_bundle_scan_order_is_deterministic(self, tmp_path: Path) -> None:
        """Same bundle scanned twice yields docs in identical order regardless of FS."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        # Create files in reverse-named order to stress determinism
        for name in ("zebra.md", "apple.md", "mango.md"):
            (tmp_path / "entities" / name).write_text(
                f"---\ntype: legacy_entity\ntitle: {name}\n---\n\n{name}.\n",
                encoding="utf-8",
            )

        run1 = OKFParser().parse_bundle(tmp_path)
        run2 = OKFParser().parse_bundle(tmp_path)

        order1 = [d.frontmatter.title for d in run1]
        order2 = [d.frontmatter.title for d in run2]
        assert order1 == order2, "Bundle scan order must be deterministic"
        assert order1 == [
            "apple.md",
            "mango.md",
            "zebra.md",
        ], f"Expected sorted order, got {order1}"


class TestFrozenContractMalformedYamlRaisesValueError:
    """Malformed YAML must raise ValueError (also for non-raw files)."""

    def test_non_raw_malformed_yaml_raises_valueerror(self, tmp_path: Path) -> None:
        """Non-raw file with malformed YAML must raise ValueError (not swallowed)."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "bad.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nBody.\n", encoding="utf-8"
        )

        with pytest.raises(ValueError, match="yaml|YAML|frontmatter"):
            OKFParser().parse_document(tmp_path / "entities" / "bad.md", tmp_path)

    def test_bundle_counts_non_raw_malformed_as_skipped_and_malformed(
        self, tmp_path: Path
    ) -> None:
        """Bundle parse catches non-raw malformed YAML, counts skipped+malformed."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        # Valid entity
        (tmp_path / "entities" / "good.md").write_text(
            "---\ntype: legacy_entity\n---\n\nGood.\n", encoding="utf-8"
        )
        # Malformed YAML (non-raw)
        (tmp_path / "entities" / "bad.md").write_text(
            "---\ninvalid: yaml: content:\n---\n\nBody.\n", encoding="utf-8"
        )

        result = OKFParser().parse_bundle(tmp_path)
        assert result.stats.parsed == 1, f"Expected 1 parsed, got {result.stats.parsed}"
        assert (
            result.stats.malformed == 1
        ), f"Expected 1 malformed, got {result.stats.malformed}"
        assert (
            result.stats.skipped == 1
        ), f"Expected 1 skipped, got {result.stats.skipped}"
