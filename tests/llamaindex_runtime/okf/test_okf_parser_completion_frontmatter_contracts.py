"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest


class TestFrozenContractTimestampRobustness:
    """Timestamp parsing handles datetime, date, strings (with Z), and invalid."""

    def test_timestamp_datetime_object_preserved(self, tmp_path: Path) -> None:
        """YAML-produced datetime object is accepted directly (no AttributeError)."""
        from datetime import datetime

        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        # YAML auto-parses ISO datetime into datetime object
        (tmp_path / "entities" / "t.md").write_text(
            "---\ntype: legacy_entity\ntimestamp: 2026-07-14T10:30:00\n---\n\nBody.\n",
            encoding="utf-8",
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "t.md", tmp_path)
        assert isinstance(doc.frontmatter.timestamp, datetime)
        assert doc.frontmatter.timestamp.year == 2026
        assert doc.frontmatter.timestamp.hour == 10

    def test_timestamp_date_object_converted_to_midnight_datetime(
        self, tmp_path: Path
    ) -> None:
        """YAML-produced date object is converted to midnight datetime."""
        from datetime import datetime

        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        # YAML auto-parses ISO date into date object
        (tmp_path / "entities" / "t.md").write_text(
            "---\ntype: legacy_entity\ntimestamp: 2026-07-14\n---\n\nBody.\n",
            encoding="utf-8",
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "t.md", tmp_path)
        assert isinstance(
            doc.frontmatter.timestamp, datetime
        ), "date must be converted to datetime (midnight)"
        assert doc.frontmatter.timestamp.year == 2026
        assert doc.frontmatter.timestamp.month == 7
        assert doc.frontmatter.timestamp.day == 14
        assert doc.frontmatter.timestamp.hour == 0
        assert doc.frontmatter.timestamp.minute == 0

    def test_timestamp_z_suffix_string_parsed(self, tmp_path: Path) -> None:
        """String timestamp with Z suffix is parsed without error."""
        from datetime import datetime

        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "t.md").write_text(
            "---\ntype: legacy_entity\ntimestamp: '2026-07-14T10:30:00Z'\n---\n\nBody.\n",
            encoding="utf-8",
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "t.md", tmp_path)
        assert isinstance(doc.frontmatter.timestamp, datetime)
        assert doc.frontmatter.timestamp.year == 2026

    def test_timestamp_invalid_string_does_not_raise_attribute_error(
        self, tmp_path: Path
    ) -> None:
        """Invalid timestamp string must not raise AttributeError (None or warning OK)."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "t.md").write_text(
            "---\ntype: legacy_entity\ntimestamp: 'not-a-date'\n---\n\nBody.\n",
            encoding="utf-8",
        )

        # Must not raise AttributeError; None is acceptable
        doc = OKFParser().parse_document(tmp_path / "entities" / "t.md", tmp_path)
        assert doc.frontmatter.timestamp is None or hasattr(
            doc.frontmatter.timestamp, "year"
        )

    def test_timestamp_non_string_non_datetime_handled_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Non-string, non-datetime timestamp (e.g. int) handled without crash."""
        from llamaindex_runtime.okf.parser import OKFParser

        (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "t.md").write_text(
            "---\ntype: legacy_entity\ntimestamp: 12345\n---\n\nBody.\n",
            encoding="utf-8",
        )

        doc = OKFParser().parse_document(tmp_path / "entities" / "t.md", tmp_path)
        # Must not crash; None or datetime both acceptable
        assert doc.frontmatter.timestamp is None or hasattr(
            doc.frontmatter.timestamp, "year"
        )


class TestKnownNonRawFrontmatterContracts:
    """Known entity, relation, and concept documents validate before construction."""

    @staticmethod
    def _known_document_frontmatter(document_type: str, timestamp: str) -> str:
        identifiers = (str(uuid4()), str(uuid4()))
        common = f"type: {document_type}\ntimestamp: {timestamp}\n"
        if document_type == "entity":
            return (
                common
                + f"title: Alice\ncanonical_entity_id: {identifiers[0]}\n"
                + "entity_type: person\n"
            )
        if document_type == "relation":
            return (
                common
                + f"subject_entity_id: {identifiers[0]}\npredicate: employed_by\n"
                + f"object_entity_id: {identifiers[1]}\n"
            )
        return common + "title: Retrieval augmented generation\n"

    @pytest.mark.parametrize("document_type", ("entity", "relation", "concept"))
    @pytest.mark.parametrize("timestamp", ("2026-07-15T09:30:00Z", "2026-07-15"))
    def test_known_documents_reject_safeloader_datetime_and_date_timestamps(
        self, tmp_path: Path, document_type: str, timestamp: str
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        md_path = tmp_path / f"{document_type}.md"
        md_path.write_text(
            f"---\n{self._known_document_frontmatter(document_type, timestamp)}---\nBody.\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(md_path, tmp_path)

        assert str(exc_info.value) == "timestamp must be a non-empty string"
        assert timestamp not in str(exc_info.value)

    @pytest.mark.parametrize("document_type", ("entity", "relation", "concept"))
    def test_known_documents_preserve_quoted_timestamp_strings(
        self, tmp_path: Path, document_type: str
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        timestamp = "2026-07-15T09:30:00Z"
        md_path = tmp_path / f"{document_type}.md"
        md_path.write_text(
            f"---\n{self._known_document_frontmatter(document_type, repr(timestamp))}---\nBody.\n",
            encoding="utf-8",
        )

        document = OKFParser().parse_document(md_path, tmp_path)

        assert document.frontmatter.timestamp == timestamp
        assert isinstance(document.frontmatter.timestamp, str)

    def test_main_e001_known_entity_is_contract_compliant(self) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        # Legacy sample/test fixture; this is not the operational default bundle root.
        bundle_root = Path(__file__).resolve().parents[3] / "okf-bundles/main"
        entity_path = bundle_root / "entities/e001-内蒙古自治区卫健委.md"
        expected_id = str(uuid5(NAMESPACE_URL, "E001"))

        document = OKFParser().parse_document(entity_path, bundle_root)

        assert expected_id == "31c6abd8-ee07-5706-8e64-838909674dfc"
        assert document.frontmatter.type == "entity"
        assert isinstance(document.frontmatter.timestamp, str)
        assert document.frontmatter.canonical_entity_id == expected_id
        assert [
            mention["resolved_to"] for mention in document.frontmatter.mentions
        ] == [
            expected_id,
            expected_id,
        ]

    def test_e001_legacy_identifier_uuid5_mapping_is_stable(self) -> None:
        assert str(uuid5(NAMESPACE_URL, "E001")) == (
            "31c6abd8-ee07-5706-8e64-838909674dfc"
        )

    def test_known_entity_dispatches_to_contract_validator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import parser as parser_module

        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            parser_module,
            "validate_known_frontmatter",
            lambda frontmatter: calls.append(dict(frontmatter)),
        )
        md_path = tmp_path / "entities" / "alice.md"
        md_path.parent.mkdir()
        md_path.write_text(
            "---\ntype: entity\ntitle: Alice\ntimestamp: '2026-07-15T09:30:00Z'\n"
            f"canonical_entity_id: {uuid4()}\nentity_type: person\n---\nAlice.\n",
            encoding="utf-8",
        )

        document = parser_module.OKFParser().parse_document(md_path, tmp_path)

        assert document.frontmatter.type == "entity"
        assert calls == [
            {
                "type": "entity",
                "title": "Alice",
                "timestamp": "2026-07-15T09:30:00Z",
                "canonical_entity_id": calls[0]["canonical_entity_id"],
                "entity_type": "person",
            }
        ]

    def test_known_relation_preserves_extensions_and_original_timestamp(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        md_path = tmp_path / "relations" / "employment.md"
        md_path.parent.mkdir()
        md_path.write_text(
            "---\ntype: relation\n"
            f"subject_entity_id: {uuid4()}\npredicate: employed_by\nobject_entity_id: {uuid4()}\n"
            "timestamp: '2026-07-15T09:30:00Z'\nqualifiers:\n"
            "  valid_time:\n    start: '2026-01-01T00:00:00Z'\n    end: null\n    expression: null\n"
            "  future_qualifier: retained\nfuture_top_level: retained\n---\nEmployment.\n",
            encoding="utf-8",
        )

        document = OKFParser().parse_document(md_path, tmp_path)

        assert document.frontmatter.timestamp == "2026-07-15T09:30:00Z"
        assert document.frontmatter.qualifiers["future_qualifier"] == "retained"
        assert document.frontmatter.extra_fields["future_top_level"] == "retained"

    def test_unknown_type_retains_legacy_permissive_behavior(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        md_path = tmp_path / "legacy.md"
        md_path.write_text(
            "---\ntype: legacy_extension\ntimestamp: 12345\n---\nLegacy.\n",
            encoding="utf-8",
        )

        document = OKFParser().parse_document(md_path, tmp_path)

        assert document.frontmatter.type == "legacy_extension"
        assert document.frontmatter.timestamp is None
