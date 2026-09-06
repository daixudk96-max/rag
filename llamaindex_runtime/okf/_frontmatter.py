"""Private OKF frontmatter construction helpers."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

_KNOWN_FRONTMATTER_FIELDS = frozenset(
    {
        "type",
        "title",
        "description",
        "resource",
        "tags",
        "timestamp",
        "aliases",
        "canonical_entity_id",
        "entity_type",
        "relations",
        "mentions",
        "source",
        "subject_entity_id",
        "predicate",
        "object_entity_id",
        "negation",
        "condition",
        "direction",
        "confidence",
        "qualifiers",
        "doc_id",
        "version_id",
        "source_checksum",
        "docling_version",
        "generated_by",
    }
)


def build_frontmatter_values(
    frontmatter: dict[str, Any], parse_timestamp: Callable[[Any], Any]
) -> dict[str, Any]:
    """Copy producer data into constructor-compatible immutable snapshots."""
    declared_type = frontmatter.get("type")
    timestamp = _timestamp_value(frontmatter, declared_type, parse_timestamp)
    values = _known_values(frontmatter, timestamp)
    return {**values, "extra_fields": _extra_fields(frontmatter)}


def _timestamp_value(
    frontmatter: dict[str, Any],
    declared_type: object,
    parse_timestamp: Callable[[Any], Any],
) -> Any:
    if declared_type in {"entity", "relation", "concept"}:
        return frontmatter.get("timestamp")
    return parse_timestamp(frontmatter.get("timestamp"))


def _extra_fields(frontmatter: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in frontmatter.items()
        if key not in _KNOWN_FRONTMATTER_FIELDS
    }


def _known_values(frontmatter: dict[str, Any], timestamp: Any) -> dict[str, Any]:
    copied = ("tags", "aliases", "relations", "mentions", "qualifiers")
    values = {key: frontmatter.get(key) for key in _KNOWN_FRONTMATTER_FIELDS}
    values["type"] = frontmatter.get("type", "unknown")
    values["timestamp"] = timestamp
    for key in copied:
        values[key] = deepcopy(frontmatter.get(key, [] if key != "qualifiers" else {}))
    return values
