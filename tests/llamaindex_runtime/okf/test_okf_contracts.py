from __future__ import annotations

from collections import UserDict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from llamaindex_runtime.okf.contracts import (
    RawFrontmatterContract,
    dump_raw_frontmatter,
    load_raw_frontmatter,
    validate_known_frontmatter,
)

VALID_FRONTMATTER: dict[str, Any] = {
    "type": "raw",
    "doc_id": "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c",
    "version_id": "306dfedb-d8cf-4828-9e91-1d1855aa8b55",
    "source_checksum": "a" * 64,
    "docling_version": "2.45.0",
    "generated_by": "docling-to-okf/1.0",
}


def test_raw_frontmatter_accepts_valid_contract() -> None:
    contract = RawFrontmatterContract.validate(VALID_FRONTMATTER)

    assert contract.type == "raw"
    assert contract.doc_id == VALID_FRONTMATTER["doc_id"]
    assert contract.version_id == VALID_FRONTMATTER["version_id"]
    assert contract.source_checksum == "a" * 64
    assert contract.docling_version == "2.45.0"
    assert contract.generated_by == "docling-to-okf/1.0"


def test_raw_template_quotes_optional_timestamp_placeholder() -> None:
    template_path = Path(__file__).resolve().parents[3] / "okf_bundle/templates/raw.md"

    template = template_path.read_text(encoding="utf-8")
    frontmatter, _ = load_raw_frontmatter(template)

    assert 'timestamp: "<ISO-8601-timestamp>"' in template
    assert frontmatter["timestamp"] == "<ISO-8601-timestamp>"
    # Raw provenance validation intentionally does not require a timestamp.
    RawFrontmatterContract.validate(VALID_FRONTMATTER)


@pytest.mark.parametrize("document_type", ("entity", "relation", "concept"))
def test_known_template_quotes_timestamp_and_safeload_preserves_iso_string(
    document_type: str,
) -> None:
    template_path = (
        Path(__file__).resolve().parents[3] / f"okf_bundle/templates/{document_type}.md"
    )
    template = template_path.read_text(encoding="utf-8")
    timestamp = "2026-07-16T09:30:00Z"

    assert 'timestamp: "<ISO-8601-timestamp>"' in template

    frontmatter_source = template.replace("<ISO-8601-timestamp>", timestamp).split(
        "---", 2
    )[1]
    frontmatter = yaml.safe_load(frontmatter_source)

    assert frontmatter["timestamp"] == timestamp
    assert isinstance(frontmatter["timestamp"], str)


@pytest.mark.parametrize("field", tuple(VALID_FRONTMATTER))
def test_raw_frontmatter_names_each_missing_required_field(field: str) -> None:
    frontmatter = {
        key: value for key, value in VALID_FRONTMATTER.items() if key != field
    }

    with pytest.raises(ValueError, match=field):
        RawFrontmatterContract.validate(frontmatter)


def test_raw_frontmatter_rejects_non_raw_type() -> None:
    frontmatter = {**VALID_FRONTMATTER, "type": "entity"}

    with pytest.raises(ValueError, match="type"):
        RawFrontmatterContract.validate(frontmatter)


def test_raw_frontmatter_dump_load_preserves_order_unicode_and_datetime() -> None:
    frontmatter = {
        **VALID_FRONTMATTER,
        "title": "中文标题",
        "timestamp": datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    }

    dumped = dump_raw_frontmatter(frontmatter, "正文")
    loaded, body = load_raw_frontmatter(dumped)

    assert dumped.startswith("---\ntype: raw\ndoc_id:")
    assert "中文标题" in dumped
    assert loaded["timestamp"] == "2026-07-12T09:30:00+00:00"
    assert body == "正文"


def test_raw_frontmatter_io_writes_one_trailing_newline_without_accumulation() -> None:
    dumped = dump_raw_frontmatter(VALID_FRONTMATTER, "body\n\n")
    loaded, body = load_raw_frontmatter(dumped)
    redumped = dump_raw_frontmatter(loaded, body)

    assert dumped.endswith("body\n")
    assert not dumped.endswith("body\n\n")
    assert redumped == dumped


def test_raw_frontmatter_io_accepts_crlf_input() -> None:
    crlf_document = (
        "---\r\n"
        "type: raw\r\n"
        "doc_id: b2191a11-cd8b-4c6e-b34a-7b5552e3c03c\r\n"
        "version_id: 306dfedb-d8cf-4828-9e91-1d1855aa8b55\r\n"
        f"source_checksum: {'a' * 64}\r\n"
        "docling_version: 2.45.0\r\n"
        "generated_by: docling-to-okf/1.0\r\n"
        "---\r\n"
        "body\r\n"
    )

    loaded, body = load_raw_frontmatter(crlf_document)

    assert loaded == VALID_FRONTMATTER
    assert body == "body"


KNOWN_FRONTMATTER: dict[str, dict[str, Any]] = {
    "entity": {
        "type": "entity",
        "title": "Alice",
        "timestamp": "2026-07-15T09:30:00Z",
        "canonical_entity_id": "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c",
        "entity_type": "person",
    },
    "relation": {
        "type": "relation",
        "subject_entity_id": "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c",
        "predicate": "employed_by",
        "object_entity_id": "306dfedb-d8cf-4828-9e91-1d1855aa8b55",
        "timestamp": "2026-07-15T09:30:00Z",
        "negation": False,
        "condition": None,
        "direction": None,
        "confidence": None,
        "qualifiers": {},
    },
    "concept": {
        "type": "concept",
        "title": "Retrieval augmented generation",
        "timestamp": "2026-07-15T09:30:00Z",
    },
}


@pytest.mark.parametrize("document_type", tuple(KNOWN_FRONTMATTER))
def test_known_frontmatter_accepts_minimal_contract(document_type: str) -> None:
    from llamaindex_runtime.okf.contracts import validate_known_frontmatter

    result = validate_known_frontmatter(KNOWN_FRONTMATTER[document_type])

    assert result is not None


@pytest.mark.parametrize(
    ("document_type", "field"),
    [
        ("entity", "type"),
        ("entity", "title"),
        ("entity", "timestamp"),
        ("entity", "canonical_entity_id"),
        ("entity", "entity_type"),
        ("relation", "type"),
        ("relation", "subject_entity_id"),
        ("relation", "predicate"),
        ("relation", "object_entity_id"),
        ("relation", "timestamp"),
        ("concept", "type"),
        ("concept", "title"),
        ("concept", "timestamp"),
    ],
)
def test_known_frontmatter_names_each_missing_required_field(
    document_type: str, field: str
) -> None:
    from llamaindex_runtime.okf.contracts import validate_known_frontmatter

    frontmatter = {
        k: v for k, v in KNOWN_FRONTMATTER[document_type].items() if k != field
    }

    with pytest.raises(ValueError, match=field):
        validate_known_frontmatter(frontmatter)


@pytest.mark.parametrize(
    ("document_type", "field", "value"),
    [
        ("entity", "canonical_entity_id", "not-a-uuid"),
        ("entity", "timestamp", "not-an-iso-timestamp"),
        ("relation", "subject_entity_id", "not-a-uuid"),
        ("relation", "object_entity_id", 7),
        ("relation", "timestamp", 7),
        ("relation", "negation", "false"),
        ("relation", "confidence", True),
        ("relation", "confidence", -0.1),
        ("relation", "confidence", 1.1),
        ("relation", "condition", False),
        ("relation", "direction", 3),
    ],
)
def test_known_frontmatter_rejects_invalid_field_types(
    document_type: str, field: str, value: object
) -> None:
    from llamaindex_runtime.okf.contracts import validate_known_frontmatter

    frontmatter = {**KNOWN_FRONTMATTER[document_type], field: value}

    with pytest.raises(ValueError, match=field):
        validate_known_frontmatter(frontmatter)


@pytest.mark.parametrize("document_type", tuple(KNOWN_FRONTMATTER))
@pytest.mark.parametrize("timestamp", [datetime(2026, 7, 15, 9, 30), date(2026, 7, 15)])
def test_known_frontmatter_rejects_datetime_values_without_echoing_them(
    document_type: str, timestamp: datetime | date
) -> None:
    frontmatter = {**KNOWN_FRONTMATTER[document_type], "timestamp": timestamp}

    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(frontmatter)

    assert str(exc_info.value) == "timestamp must be a non-empty string"
    assert str(timestamp) not in str(exc_info.value)


@pytest.mark.parametrize(
    "valid_time",
    [
        {"start": "2026-01-01T00:00:00Z", "end": None, "expression": None},
        {"start": None, "end": None, "expression": "during the 2026 fiscal year"},
        {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-12-31T23:59:59Z",
            "expression": None,
        },
    ],
)
def test_relation_valid_time_accepts_standard_forms(
    valid_time: dict[str, str | None],
) -> None:
    from llamaindex_runtime.okf.contracts import validate_known_frontmatter

    validate_known_frontmatter(
        {**KNOWN_FRONTMATTER["relation"], "qualifiers": {"valid_time": valid_time}}
    )


@pytest.mark.parametrize(
    "valid_time",
    [
        {},
        {"start": None, "end": None, "expression": None},
        {"start": None, "end": None, "expression": ""},
        {"start": "not-an-iso", "end": None, "expression": None},
        {
            "start": "2026-12-31T00:00:00Z",
            "end": "2026-01-01T00:00:00Z",
            "expression": None,
        },
        {
            "start": "2026-01-01T00:00:00Z",
            "end": None,
            "expression": None,
            "future": "no",
        },
    ],
)
def test_relation_valid_time_rejects_invalid_or_lossy_forms(
    valid_time: dict[str, object],
) -> None:
    from llamaindex_runtime.okf.contracts import validate_known_frontmatter

    with pytest.raises(ValueError, match="valid_time"):
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "qualifiers": {"valid_time": valid_time}}
        )


@pytest.mark.parametrize(
    "invalid_extension",
    [
        {"decimal": Decimal("1.25")},
        {"set": {"unsupported"}},
        {"object": object()},
        {1: "non-string key"},
        {"number": float("nan")},
        {"number": float("inf")},
        {"number": float("-inf")},
        {"nested": {"unsupported": Decimal("1.25")}},
        {"array": ("tuples are not JSON arrays",)},
    ],
)
def test_relation_rejects_non_json_qualifier_extensions_with_safe_error(
    invalid_extension: object,
) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {
                **KNOWN_FRONTMATTER["relation"],
                "qualifiers": {"extension": invalid_extension},
            }
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"


@pytest.mark.parametrize(
    "qualifiers, canary",
    [
        ({"value": "before\ud800after"}, "before\ud800after"),
        ({"value": "before\udc00after"}, "before\udc00after"),
        ({"key-\ud800": "safe"}, "key-\ud800"),
        ({"key-\udc00": "safe"}, "key-\udc00"),
        ({"outer": {"inner": ["before\ud800after"]}}, "before\ud800after"),
    ],
)
def test_relation_rejects_surrogate_qualifiers_with_safe_error(
    qualifiers: dict[str, object], canary: str
) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "qualifiers": qualifiers}
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert canary not in str(exc_info.value)


def test_relation_preserves_valid_unicode_qualifiers() -> None:
    frontmatter = {
        **KNOWN_FRONTMATTER["relation"],
        "qualifiers": {"语言😀": {"message": "中文、emoji 😀、café"}},
    }

    result = validate_known_frontmatter(frontmatter)

    assert result is not None
    assert frontmatter["qualifiers"] == {"语言😀": {"message": "中文、emoji 😀、café"}}


def test_relation_rejects_cyclic_qualifier_extensions_with_safe_error() -> None:
    cycle: dict[str, object] = {}
    cycle["self"] = cycle

    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "qualifiers": {"extension": cycle}}
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"


def test_relation_rejects_oversized_qualifier_extension_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llamaindex_runtime.okf import contracts

    monkeypatch.setattr(contracts, "DEFAULT_MAX_YAML_NODES", 2)

    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {
                **KNOWN_FRONTMATTER["relation"],
                "qualifiers": {"extension": {"value": "one too many"}},
            }
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"


def test_relation_rejects_deep_qualifier_extension_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llamaindex_runtime.okf import contracts

    monkeypatch.setattr(contracts, "DEFAULT_MAX_YAML_DEPTH", 1)

    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {
                **KNOWN_FRONTMATTER["relation"],
                "qualifiers": {"extension": {"nested": "too deep"}},
            }
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"


def test_relation_preserves_unknown_top_level_and_qualifier_extensions() -> None:
    frontmatter = {
        **KNOWN_FRONTMATTER["relation"],
        "future_top_level": "保留",
        "qualifiers": {"future_qualifier": {"emoji": "知识"}},
    }

    result = validate_known_frontmatter(frontmatter)

    assert result is not None


@pytest.mark.parametrize(
    "valid_time",
    [
        {"start": "2026-01-01T00:00:00Z"},
        {"end": "2026-12-31T23:59:59Z"},
        {"expression": "during 2026"},
        {"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"},
        {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-12-31T23:59:59Z",
            "expression": "during 2026",
        },
    ],
)
def test_relation_valid_time_accepts_non_empty_key_subsets(
    valid_time: dict[str, str],
) -> None:
    validate_known_frontmatter(
        {**KNOWN_FRONTMATTER["relation"], "qualifiers": {"valid_time": valid_time}}
    )


def test_relation_valid_time_rejects_aware_naive_bounds_without_typeerror() -> None:
    frontmatter = {
        **KNOWN_FRONTMATTER["relation"],
        "qualifiers": {
            "valid_time": {
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-12-31T23:59:59",
            }
        },
    }

    with pytest.raises(ValueError, match="valid_time.*comparable"):
        validate_known_frontmatter(frontmatter)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_relation_confidence_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "confidence": value}
        )


@pytest.mark.parametrize("value", [[], {}, None, True, 1, "", "   "])
def test_known_frontmatter_type_rejects_non_empty_string_boundary(
    value: object,
) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter({"type": value})

    assert str(exc_info.value) == "type must be a non-empty string"


def test_unknown_non_empty_string_type_remains_permissive() -> None:
    assert validate_known_frontmatter({"type": "future_extension"}) is None


@pytest.mark.parametrize("field", ("tags", "aliases"))
@pytest.mark.parametrize(
    "value", ["scalar", b"bytes", {"bad": "mapping"}, [""], ["  "], [1]]
)
def test_known_frontmatter_rejects_invalid_string_list_extensions(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        validate_known_frontmatter({**KNOWN_FRONTMATTER["entity"], field: value})


@pytest.mark.parametrize("field", ("relations", "mentions"))
@pytest.mark.parametrize("value", ["scalar", {"target": "x"}, ["not-a-mapping"], [1]])
def test_known_frontmatter_rejects_invalid_mapping_list_extensions(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        validate_known_frontmatter({**KNOWN_FRONTMATTER["entity"], field: value})


@pytest.mark.parametrize(
    "qualifiers, canary",
    [
        (UserDict({"extension": "root-mapping-subclass"}), "root-mapping-subclass"),
        (
            {"extension": UserDict({"value": "nested-mapping-subclass"})},
            "nested-mapping-subclass",
        ),
    ],
)
def test_relation_qualifiers_require_plain_dict_objects(
    qualifiers: object, canary: str
) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "qualifiers": qualifiers}
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert canary not in str(exc_info.value)


@pytest.mark.parametrize("value", ["scalar", [], ["not", "a", "mapping"]])
def test_relation_qualifiers_requires_mapping_when_present(value: object) -> None:
    with pytest.raises(ValueError, match="qualifiers"):
        validate_known_frontmatter(
            {**KNOWN_FRONTMATTER["relation"], "qualifiers": value}
        )


class TestRawFrontmatterResourceBudget:
    """The public raw-frontmatter loader shares the parser's byte budget."""

    def test_load_raw_frontmatter_rejects_oversized_frontmatter_before_copying(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import contracts

        monkeypatch.setattr(contracts, "MAX_FRONTMATTER_BYTES", 8)
        document = "---\nsecret: 123456789\n---\nbody"

        with pytest.raises(ValueError) as exc_info:
            load_raw_frontmatter(document)

        assert str(exc_info.value) == "frontmatter exceeds maximum size"
        assert "secret" not in str(exc_info.value)

    def test_load_raw_frontmatter_does_not_charge_large_body_to_frontmatter_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import contracts

        monkeypatch.setattr(contracts, "MAX_FRONTMATTER_BYTES", 16)
        document = "---\ntype: raw\n---\n" + ("body" * 100_000)

        frontmatter, body = load_raw_frontmatter(document)

        assert frontmatter == {"type": "raw"}
        assert len(body) == 400_000
