"""Tests for the explicit normalization contract.

The normalization contract makes span normalization rules first-class,
testable, and configurable -- replacing the implicit rules previously
scattered across DoclingIngestor private static methods and
CanonicalSpan.__post_init__.
"""
from __future__ import annotations

from typing import Any

import pytest

from llamaindex_runtime.ingestion.normalization import (
    NormalizationContract,
    NormalizationRules,
    NormalizedNodeData,
)


# ---------------------------------------------------------------------------
# NormalizationRules dataclass
# ---------------------------------------------------------------------------

class TestNormalizationRules:
    def test_default_values(self) -> None:
        rules = NormalizationRules()
        assert rules.collapse_whitespace is True
        assert rules.strip_headings is True
        assert rules.filter_empty_headings is True
        assert rules.heading_separator_priority == (" > ", ">")
        assert rules.page_number_keys == ("page_no",)
        assert rules.offset_keys == ("offset", "start_offset", "doc_offset")

    def test_is_frozen(self) -> None:
        rules = NormalizationRules()
        with pytest.raises(AttributeError):
            rules.collapse_whitespace = False  # type: ignore[misc]

    def test_custom_values(self) -> None:
        rules = NormalizationRules(
            collapse_whitespace=False,
            heading_separator_priority=(" / ", "/"),
            page_number_keys=("page", "page_no"),
            offset_keys=("start",),
        )
        assert rules.collapse_whitespace is False
        assert rules.heading_separator_priority == (" / ", "/")
        assert rules.page_number_keys == ("page", "page_no")
        assert rules.offset_keys == ("start",)


# ---------------------------------------------------------------------------
# NormalizedNodeData dataclass
# ---------------------------------------------------------------------------

class TestNormalizedNodeData:
    def test_fields(self) -> None:
        data = NormalizedNodeData(
            text="hello world",
            headings=("Intro",),
            page_no=3,
            offset=12,
        )
        assert data.text == "hello world"
        assert data.headings == ("Intro",)
        assert data.page_no == 3
        assert data.offset == 12

    def test_page_no_defaults_to_none(self) -> None:
        data = NormalizedNodeData(text="x", headings=(), page_no=None, offset=0)
        assert data.page_no is None

    def test_is_frozen(self) -> None:
        data = NormalizedNodeData(text="x", headings=(), page_no=None, offset=0)
        with pytest.raises(AttributeError):
            data.text = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NormalizationContract -- normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_collapses_whitespace_by_default(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_text("  hello   world  ") == "hello world"

    def test_collapses_tabs_and_newlines(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_text("hello\t\nworld") == "hello world"

    def test_preserves_text_when_rule_disabled(self) -> None:
        contract = NormalizationContract(NormalizationRules(collapse_whitespace=False))
        assert contract.normalize_text("  hello   world  ") == "  hello   world  "

    def test_empty_string_stays_empty(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_text("") == ""

    def test_single_word(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_text("  hello  ") == "hello"

    def test_unicode_whitespace(self) -> None:
        contract = NormalizationContract()
        # 　 is ideographic space
        result = contract.normalize_text("hello　world")
        assert result == "hello world"

    def test_only_whitespace_becomes_empty(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_text("   \t\n  ") == ""


# ---------------------------------------------------------------------------
# NormalizationContract -- normalize_headings
# ---------------------------------------------------------------------------

class TestNormalizeHeadings:
    def test_none_returns_empty_tuple(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings(None) == ()

    def test_string_with_arrow_separator(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings("Intro > Section") == ("Intro", "Section")

    def test_string_with_spaced_arrow_separator(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings("Intro > Section > Details") == ("Intro", "Section", "Details")

    def test_string_with_no_separator(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings("SingleHeading") == ("SingleHeading",)

    def test_list_of_strings(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings(["Intro", "Section"]) == ("Intro", "Section")

    def test_strips_whitespace_from_parts(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings([" Intro ", " Section "]) == ("Intro", "Section")

    def test_filters_empty_parts(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings(["Intro", " ", "", "Section"]) == ("Intro", "Section")

    def test_empty_list_returns_empty_tuple(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings([]) == ()

    def test_all_whitespace_parts_returns_empty_tuple(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings(["  ", "\t"]) == ()

    def test_custom_separator(self) -> None:
        rules = NormalizationRules(heading_separator_priority=(" / ", "/"))
        contract = NormalizationContract(rules)
        assert contract.normalize_headings("Intro / Section") == ("Intro", "Section")

    def test_strip_disabled(self) -> None:
        rules = NormalizationRules(strip_headings=False, filter_empty_headings=False)
        contract = NormalizationContract(rules)
        # With stripping disabled, parts retain their whitespace
        result = contract.normalize_headings([" Intro ", " Section "])
        assert result == (" Intro ", " Section ")

    def test_filter_empty_disabled(self) -> None:
        rules = NormalizationRules(filter_empty_headings=False)
        contract = NormalizationContract(rules)
        # Empty strings are kept when filtering is disabled
        result = contract.normalize_headings(["Intro", "", "Section"])
        assert result == ("Intro", "", "Section")

    def test_heading_path_with_spaced_arrow_takes_priority(self) -> None:
        """When both ' > ' and '>' exist, ' > ' should be used as separator."""
        contract = NormalizationContract()
        # "A > B" contains both " > " and ">", so " > " should win
        result = contract.normalize_headings("A > B > C")
        assert result == ("A", "B", "C")

    def test_unicode_in_headings(self) -> None:
        contract = NormalizationContract()
        assert contract.normalize_headings(["Intro", "中文标题"]) == ("Intro", "中文标题")


# ---------------------------------------------------------------------------
# NormalizationContract -- extract_page_no
# ---------------------------------------------------------------------------

class TestExtractPageNo:
    def test_integer_page_number(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": 3}) == 3

    def test_string_page_number(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": "5"}) == 5

    def test_missing_key_returns_none(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({}) is None

    def test_negative_integer_returns_none(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": -1}) is None

    def test_non_numeric_string_returns_none(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": "iii"}) is None

    def test_float_returns_none(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": 2.5}) is None

    def test_zero_is_valid(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_page_no({"page_no": 0}) == 0

    def test_custom_key(self) -> None:
        rules = NormalizationRules(page_number_keys=("page",))
        contract = NormalizationContract(rules)
        assert contract.extract_page_no({"page": 7}) == 7
        assert contract.extract_page_no({"page_no": 7}) is None

    def test_first_matching_key_wins(self) -> None:
        rules = NormalizationRules(page_number_keys=("page", "page_no"))
        contract = NormalizationContract(rules)
        assert contract.extract_page_no({"page": 1, "page_no": 2}) == 1


# ---------------------------------------------------------------------------
# NormalizationContract -- extract_offset
# ---------------------------------------------------------------------------

class TestExtractOffset:
    def test_offset_key(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": 100}, ordinal=0) == 100

    def test_start_offset_key(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"start_offset": 48}, ordinal=0) == 48

    def test_doc_offset_key(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"doc_offset": 200}, ordinal=0) == 200

    def test_falls_back_to_ordinal(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({}, ordinal=5) == 5

    def test_string_offset_value(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": "42"}, ordinal=0) == 42

    def test_negative_offset_falls_back_to_ordinal(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": -1}, ordinal=3) == 3

    def test_non_numeric_string_falls_back(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": "abc"}, ordinal=2) == 2

    def test_first_matching_key_wins(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": 10, "start_offset": 20}, ordinal=0) == 10

    def test_custom_keys(self) -> None:
        rules = NormalizationRules(offset_keys=("char_start",))
        contract = NormalizationContract(rules)
        assert contract.extract_offset({"char_start": 99}, ordinal=0) == 99
        assert contract.extract_offset({"offset": 50}, ordinal=0) == 0

    def test_zero_is_valid(self) -> None:
        contract = NormalizationContract()
        assert contract.extract_offset({"offset": 0}, ordinal=5) == 0


# ---------------------------------------------------------------------------
# NormalizationContract -- normalize (composite method)
# ---------------------------------------------------------------------------

class TestNormalizeComposite:
    def test_produces_normalized_node_data(self) -> None:
        contract = NormalizationContract()
        result = contract.normalize(
            raw_text="  hello   world  ",
            metadata={"page_no": 1, "headings": ["Intro", "Section"], "offset": 12},
            ordinal=0,
        )
        assert isinstance(result, NormalizedNodeData)
        assert result.text == "hello world"
        assert result.headings == ("Intro", "Section")
        assert result.page_no == 1
        assert result.offset == 12

    def test_heading_path_key(self) -> None:
        contract = NormalizationContract()
        result = contract.normalize(
            raw_text="text",
            metadata={"heading_path": "Appendix > A"},
            ordinal=0,
        )
        assert result.headings == ("Appendix", "A")

    def test_headings_key_takes_priority_over_heading_path(self) -> None:
        contract = NormalizationContract()
        result = contract.normalize(
            raw_text="text",
            metadata={"headings": ["A"], "heading_path": "B > C"},
            ordinal=0,
        )
        assert result.headings == ("A",)

    def test_empty_metadata(self) -> None:
        contract = NormalizationContract()
        result = contract.normalize(
            raw_text="some text",
            metadata={},
            ordinal=7,
        )
        assert result.text == "some text"
        assert result.headings == ()
        assert result.page_no is None
        assert result.offset == 7

    def test_string_page_no_in_metadata(self) -> None:
        contract = NormalizationContract()
        result = contract.normalize(
            raw_text="text",
            metadata={"page_no": "3"},
            ordinal=0,
        )
        assert result.page_no == 3

    def test_custom_rules_applied(self) -> None:
        rules = NormalizationRules(
            collapse_whitespace=False,
            page_number_keys=("pg",),
            offset_keys=("start",),
        )
        contract = NormalizationContract(rules)
        result = contract.normalize(
            raw_text="  hello  ",
            metadata={"pg": 2, "start": 50},
            ordinal=0,
        )
        assert result.text == "  hello  "
        assert result.page_no == 2
        assert result.offset == 50


# ---------------------------------------------------------------------------
# NormalizationContract -- rules property
# ---------------------------------------------------------------------------

class TestContractRulesProperty:
    def test_default_rules(self) -> None:
        contract = NormalizationContract()
        assert contract.rules == NormalizationRules()

    def test_custom_rules_exposed(self) -> None:
        rules = NormalizationRules(collapse_whitespace=False)
        contract = NormalizationContract(rules)
        assert contract.rules is rules


# ---------------------------------------------------------------------------
# Integration: DoclingIngestor uses NormalizationContract
# ---------------------------------------------------------------------------

class TestDoclingIngestorUsesNormalizationContract:
    """Verify DoclingIngestor delegates to NormalizationContract for
    normalization, keeping span generation behavior stable."""

    def test_ingestor_exposes_contract(self) -> None:
        from llamaindex_runtime.ingestion import DoclingIngestor

        ingestor = DoclingIngestor(
            reader=_FakeReader(),
            node_parser=_FakeNodeParser([]),
        )
        assert isinstance(ingestor.normalization_contract, NormalizationContract)

    def test_ingestor_accepts_custom_contract(self, tmp_path: Any) -> None:
        from uuid import uuid4

        from llamaindex_runtime.ingestion import DoclingIngestor

        source_path = tmp_path / "sample.txt"
        source_path.write_text("demo", encoding="utf-8")

        rules = NormalizationRules(collapse_whitespace=False)
        contract = NormalizationContract(rules)

        ingestor = DoclingIngestor(
            reader=_FakeReader(),
            node_parser=_FakeNodeParser(
                [_FakeNode("  hello  ", {"page_no": 1, "offset": 0})]
            ),
            normalization_contract=contract,
        )
        result = ingestor.ingest(source_path, doc_id=uuid4(), version_id=uuid4())

        assert len(result.spans) == 1
        assert result.spans[0].text == "  hello  "

    def test_existing_behavior_preserved(self, tmp_path: Any) -> None:
        """Regression: span generation behavior must not change."""
        from pathlib import Path
        from uuid import uuid4

        from llamaindex_runtime.ingestion import DoclingIngestor

        source_path = tmp_path / "sample.txt"
        source_path.write_text("demo", encoding="utf-8")
        doc_id = uuid4()
        version_id = uuid4()

        ingestor = DoclingIngestor(
            reader=_FakeReader(),
            node_parser=_FakeNodeParser(
                [
                    _FakeNode(
                        "  First span  ",
                        {"page_no": 1, "headings": ["Intro", "Section"], "offset": 12},
                    ),
                    _FakeNode(
                        "Second span",
                        {"page_no": "2", "heading_path": "Appendix > A", "start_offset": 48},
                    ),
                ]
            ),
        )
        result = ingestor.ingest(source_path, doc_id=doc_id, version_id=version_id)

        assert len(result.spans) == 2
        assert result.spans[0].text == "First span"
        assert result.spans[0].heading_path == "Intro > Section"
        assert result.spans[0].page_no == 1
        assert result.spans[0].offset == 12
        assert result.spans[1].heading_path == "Appendix > A"
        assert result.spans[1].page_no == 2
        assert result.spans[1].offset == 48

    def test_ingestor_preserves_disabled_heading_rules(self, tmp_path: Any) -> None:
        from uuid import uuid4

        from llamaindex_runtime.ingestion import DoclingIngestor

        source_path = tmp_path / "sample.txt"
        source_path.write_text("demo", encoding="utf-8")
        contract = NormalizationContract(
            NormalizationRules(strip_headings=False, filter_empty_headings=False)
        )

        ingestor = DoclingIngestor(
            reader=_FakeReader(),
            node_parser=_FakeNodeParser(
                [_FakeNode("text", {"headings": [" Intro ", "", " Section "]})]
            ),
            normalization_contract=contract,
        )
        result = ingestor.ingest(source_path, doc_id=uuid4(), version_id=uuid4())

        assert result.spans[0].headings == (" Intro ", "", " Section ")


# ---------------------------------------------------------------------------
# Fakes for integration tests (local to this file to avoid import coupling)
# ---------------------------------------------------------------------------

class _FakeDocument:
    def __init__(self, source: str) -> None:
        self.source = source


class _FakeNode:
    def __init__(self, text: str, metadata: dict[str, object]) -> None:
        self._text = text
        self.metadata = metadata

    def get_content(self) -> str:
        return self._text


class _FakeReader:
    def load_data(self, *, file_path: str) -> list[_FakeDocument]:
        return [_FakeDocument(file_path)]


class _FakeNodeParser:
    def __init__(self, nodes: list[_FakeNode]) -> None:
        self._nodes = nodes

    def get_nodes_from_documents(self, documents: object) -> list[_FakeNode]:
        return self._nodes
