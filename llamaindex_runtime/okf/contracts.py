"""Fail-fast contracts for machine-generated raw OKF Markdown files.

Adapted from ogham-mcp/ogham-mcp (MIT): frontmatter boundary validation
patterns. See the project upstream analysis.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

import yaml
from yaml.events import AliasEvent

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FRONTMATTER_DELIMITER = "---"
_FRONTMATTER_PATTERN = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
MAX_FRONTMATTER_BYTES = 1 * 1024 * 1024
DEFAULT_MAX_YAML_DEPTH = 64
DEFAULT_MAX_YAML_NODES = 10_000
DEFAULT_MAX_YAML_ALIASES = 32
_REQUIRED_FIELDS = (
    "type",
    "doc_id",
    "version_id",
    "source_checksum",
    "docling_version",
    "generated_by",
)


def load_bounded_safe_yaml(
    yaml_block: str,
    *,
    max_depth: int = DEFAULT_MAX_YAML_DEPTH,
    max_nodes: int = DEFAULT_MAX_YAML_NODES,
    max_aliases: int = DEFAULT_MAX_YAML_ALIASES,
) -> Any:
    """Load YAML with SafeLoader semantics and explicit compose-time budgets."""

    class BoundedSafeLoader(yaml.SafeLoader):
        def __init__(self, stream: str) -> None:
            super().__init__(stream)
            self._compose_depth = 0
            self._node_count = 0
            self._alias_count = 0

        def compose_node(self, parent: Any, index: Any) -> Any:
            is_alias = self.check_event(AliasEvent)
            if is_alias:
                self._alias_count += 1
                if self._alias_count > max_aliases:
                    raise ValueError("frontmatter YAML exceeds maximum aliases")
            else:
                self._compose_depth += 1
                if self._compose_depth > max_depth:
                    raise ValueError("frontmatter YAML exceeds maximum depth")
                self._node_count += 1
                if self._node_count > max_nodes:
                    raise ValueError("frontmatter YAML exceeds maximum nodes")
            try:
                return super().compose_node(parent, index)
            finally:
                if not is_alias:
                    self._compose_depth -= 1

    try:
        loader = BoundedSafeLoader(yaml_block)
        try:
            return loader.get_single_data()
        finally:
            loader.dispose()
    except ValueError:
        raise
    except yaml.YAMLError as exc:
        raise ValueError("frontmatter YAML is invalid") from exc


@dataclass(frozen=True)
class RawFrontmatterContract:
    """Validated document-level provenance for a raw OKF Markdown file."""

    type: str
    doc_id: str
    version_id: str
    source_checksum: str
    docling_version: str
    generated_by: str

    @classmethod
    def validate(cls, frontmatter: Mapping[str, Any]) -> RawFrontmatterContract:
        """Validate required raw-file fields with field-named errors."""
        for field in _REQUIRED_FIELDS:
            if field not in frontmatter:
                raise ValueError(f"{field} is required")
        if frontmatter["type"] != "raw":
            raise ValueError("type must be 'raw'")

        doc_id = _required_string(frontmatter, "doc_id")
        version_id = _required_string(frontmatter, "version_id")
        _validate_uuid(doc_id, "doc_id")
        _validate_uuid(version_id, "version_id")
        source_checksum = _required_string(frontmatter, "source_checksum")
        if not _SHA256_PATTERN.fullmatch(source_checksum):
            raise ValueError("source_checksum must be a lowercase SHA256 hex string")
        return cls(
            type="raw",
            doc_id=doc_id,
            version_id=version_id,
            source_checksum=source_checksum,
            docling_version=_required_string(frontmatter, "docling_version"),
            generated_by=_required_string(frontmatter, "generated_by"),
        )


def dump_raw_frontmatter(frontmatter: Mapping[str, Any], body: str) -> str:
    """Serialize ordered raw frontmatter and a body with one trailing newline.

    Adapted from ogham-mcp/ogham-mcp (MIT) `write_concept` semantics: preserve
    insertion order, retain Unicode, and prevent trailing-newline accumulation.
    """
    serialized_frontmatter = yaml.safe_dump(
        _normalize_frontmatter(frontmatter),
        sort_keys=False,
        allow_unicode=True,
    )
    normalized_body = body.rstrip("\r\n")
    return (
        f"{_FRONTMATTER_DELIMITER}\n"
        f"{serialized_frontmatter}"
        f"{_FRONTMATTER_DELIMITER}\n"
        f"{normalized_body}\n"
    )


def extract_bounded_frontmatter(document: str) -> tuple[str, str] | None:
    """Return frontmatter and body only after the shared UTF-8 byte budget passes."""
    match = _FRONTMATTER_PATTERN.match(document)
    if match is None:
        return None
    start, end = match.span(1)
    if _utf8_bytes_exceed_limit(document, start, end, MAX_FRONTMATTER_BYTES):
        raise ValueError("frontmatter exceeds maximum size")
    return document[start:end], document[match.end() :]


def _utf8_bytes_exceed_limit(value: str, start: int, end: int, maximum: int) -> bool:
    """Count a string range as UTF-8 without copying the untrusted range first."""
    byte_count = 0
    for index in range(start, end):
        code_point = ord(value[index])
        byte_count += (
            1
            if code_point <= 0x7F
            else 2 if code_point <= 0x7FF else 3 if code_point <= 0xFFFF else 4
        )
        if byte_count > maximum:
            return True
    return False


def load_raw_frontmatter(document: str) -> tuple[dict[str, Any], str]:
    """Parse raw frontmatter from LF or CRLF content without newline drift.

    Adapted from ogham-mcp/ogham-mcp (MIT) `read_concept` semantics. YAML input
    must be a mapping and the returned body has at most one writer-added newline
    removed so dump/load cycles are stable.
    """
    extracted = extract_bounded_frontmatter(document)
    if extracted is None:
        if not document.startswith(_FRONTMATTER_DELIMITER):
            raise ValueError("frontmatter must start with '---'")
        raise ValueError("frontmatter block must end with '---'")
    yaml_block, body = extracted
    try:
        parsed = load_bounded_safe_yaml(yaml_block) or {}
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    normalized_body = body.replace("\r\n", "\n")
    if normalized_body.endswith("\n"):
        normalized_body = normalized_body[:-1]
    return parsed, normalized_body


def _normalize_frontmatter(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat() if isinstance(value, (datetime, date)) else value
        for key, value in frontmatter.items()
    }


def _required_string(frontmatter: Mapping[str, Any], field: str) -> str:
    value = frontmatter[field]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_uuid(value: str, field: str) -> None:
    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a UUID") from exc


_KNOWN_TYPES = frozenset({"entity", "relation", "concept"})
_VALID_TIME_KEYS = frozenset({"start", "end", "expression"})


@dataclass(frozen=True)
class EntityFrontmatterContract:
    type: str
    title: str
    timestamp: str
    canonical_entity_id: str
    entity_type: str


@dataclass(frozen=True)
class RelationFrontmatterContract:
    type: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    timestamp: str


@dataclass(frozen=True)
class ConceptFrontmatterContract:
    type: str
    title: str
    timestamp: str


KnownFrontmatterContract = (
    EntityFrontmatterContract | RelationFrontmatterContract | ConceptFrontmatterContract
)


def validate_known_frontmatter(
    frontmatter: Mapping[str, Any],
) -> KnownFrontmatterContract | None:
    """Validate entity, relation, and concept frontmatter without rewriting it.

    Unknown document types retain the parser's legacy permissive behavior.
    """
    if "type" not in frontmatter:
        raise ValueError("type is required")
    document_type = frontmatter.get("type")
    if not isinstance(document_type, str) or not document_type.strip():
        raise ValueError("type must be a non-empty string")
    if document_type not in _KNOWN_TYPES:
        return None
    _validate_optional_string_list(frontmatter, "tags")
    _validate_optional_string_list(frontmatter, "aliases")
    _validate_optional_mapping_list(frontmatter, "relations")
    _validate_optional_mapping_list(frontmatter, "mentions")
    if document_type == "entity":
        return _validate_entity_frontmatter(frontmatter)
    if document_type == "relation":
        return _validate_relation_frontmatter(frontmatter)
    return _validate_concept_frontmatter(frontmatter)


def _validate_entity_frontmatter(
    frontmatter: Mapping[str, Any],
) -> EntityFrontmatterContract:
    _require_fields(
        frontmatter,
        ("type", "title", "timestamp", "canonical_entity_id", "entity_type"),
    )
    canonical_entity_id = _required_string(frontmatter, "canonical_entity_id")
    _validate_uuid(canonical_entity_id, "canonical_entity_id")
    return EntityFrontmatterContract(
        type="entity",
        title=_required_string(frontmatter, "title"),
        timestamp=_required_iso_timestamp(frontmatter, "timestamp"),
        canonical_entity_id=canonical_entity_id,
        entity_type=_required_string(frontmatter, "entity_type"),
    )


def _validate_relation_frontmatter(
    frontmatter: Mapping[str, Any],
) -> RelationFrontmatterContract:
    _require_fields(
        frontmatter,
        ("type", "subject_entity_id", "predicate", "object_entity_id", "timestamp"),
    )
    subject_entity_id = _required_string(frontmatter, "subject_entity_id")
    object_entity_id = _required_string(frontmatter, "object_entity_id")
    _validate_uuid(subject_entity_id, "subject_entity_id")
    _validate_uuid(object_entity_id, "object_entity_id")
    _validate_relation_qualifiers(frontmatter)
    return RelationFrontmatterContract(
        type="relation",
        subject_entity_id=subject_entity_id,
        predicate=_required_string(frontmatter, "predicate"),
        object_entity_id=object_entity_id,
        timestamp=_required_iso_timestamp(frontmatter, "timestamp"),
    )


def _validate_concept_frontmatter(
    frontmatter: Mapping[str, Any],
) -> ConceptFrontmatterContract:
    _require_fields(frontmatter, ("type", "title", "timestamp"))
    return ConceptFrontmatterContract(
        type="concept",
        title=_required_string(frontmatter, "title"),
        timestamp=_required_iso_timestamp(frontmatter, "timestamp"),
    )


def _require_fields(frontmatter: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field not in frontmatter:
            raise ValueError(f"{field} is required")


def _required_iso_timestamp(frontmatter: Mapping[str, Any], field: str) -> str:
    value = _required_string(frontmatter, field)
    try:
        datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 string") from exc
    return value


def _validate_optional_string_list(frontmatter: Mapping[str, Any], field: str) -> None:
    if field not in frontmatter:
        return
    value = frontmatter[field]
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{field} must be a list of non-empty strings")


def _validate_optional_mapping_list(frontmatter: Mapping[str, Any], field: str) -> None:
    if field not in frontmatter:
        return
    value = frontmatter[field]
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{field} must be a list of mappings")


def validate_relation_qualifiers(
    values: Mapping[str, Any],
    *,
    allow_none_negation: bool = False,
    allow_none_qualifiers: bool = False,
) -> None:
    """Validate shared relation qualifier semantics without rewriting values."""
    _validate_optional_bool(values, "negation", allow_none=allow_none_negation)
    _validate_optional_string_or_none(values, "condition")
    _validate_optional_string_or_none(values, "direction")
    _validate_optional_confidence(values)
    qualifiers = values.get("qualifiers", {})
    if qualifiers is None and allow_none_qualifiers:
        return
    if type(qualifiers) is not dict:
        raise ValueError("qualifiers must contain only JSON-compatible values")
    if "valid_time" in qualifiers:
        _validate_valid_time(qualifiers["valid_time"])
    _validate_json_compatible_qualifiers(qualifiers)


def _validate_json_compatible_qualifiers(value: Any) -> None:
    """Reject qualifier values that psycopg cannot encode as JSON."""
    _validate_json_value(value, depth=0, nodes=0, ancestors=frozenset())


def _validate_json_value(
    value: Any, *, depth: int, nodes: int, ancestors: frozenset[int]
) -> int:
    if depth > DEFAULT_MAX_YAML_DEPTH or nodes >= DEFAULT_MAX_YAML_NODES:
        raise ValueError("qualifiers must contain only JSON-compatible values")
    if value is None or isinstance(value, (bool, int)):
        return nodes + 1
    if isinstance(value, str):
        _validate_json_string(value)
        return nodes + 1
    if isinstance(value, float):
        if math.isfinite(value):
            return nodes + 1
        raise ValueError("qualifiers must contain only JSON-compatible values")
    if type(value) is not dict and type(value) is not list:
        raise ValueError("qualifiers must contain only JSON-compatible values")

    container_id = id(value)
    if container_id in ancestors:
        raise ValueError("qualifiers must contain only JSON-compatible values")
    next_ancestors = ancestors | frozenset((container_id,))
    next_nodes = nodes + 1
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("qualifiers must contain only JSON-compatible values")
            _validate_json_string(key)
            next_nodes = _validate_json_value(
                item,
                depth=depth + 1,
                nodes=next_nodes,
                ancestors=next_ancestors,
            )
        return next_nodes
    for item in value:
        next_nodes = _validate_json_value(
            item,
            depth=depth + 1,
            nodes=next_nodes,
            ancestors=next_ancestors,
        )
    return next_nodes


def _validate_json_string(value: str) -> None:
    """Ensure a JSON string contains only UTF-8 encodable Unicode scalars."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(
            "qualifiers must contain only JSON-compatible values"
        ) from error


def _validate_relation_qualifiers(frontmatter: Mapping[str, Any]) -> None:
    validate_relation_qualifiers(frontmatter)


def _validate_optional_bool(
    frontmatter: Mapping[str, Any], field: str, *, allow_none: bool = False
) -> None:
    value = frontmatter.get(field)
    if field in frontmatter and not (
        isinstance(value, bool) or (allow_none and value is None)
    ):
        raise ValueError(f"{field} must be a boolean")


def _validate_optional_string_or_none(
    frontmatter: Mapping[str, Any], field: str
) -> None:
    if field in frontmatter and frontmatter[field] is not None:
        _required_string(frontmatter, field)


def _validate_optional_confidence(frontmatter: Mapping[str, Any]) -> None:
    if "confidence" not in frontmatter or frontmatter["confidence"] is None:
        return
    confidence = frontmatter["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("confidence must be a number between 0 and 1")


def _validate_valid_time(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("qualifiers.valid_time must be a mapping")
    unknown_keys = set(value) - _VALID_TIME_KEYS
    if unknown_keys:
        raise ValueError("qualifiers.valid_time contains unsupported keys")
    start = _validate_valid_time_timestamp(value.get("start"), "start")
    end = _validate_valid_time_timestamp(value.get("end"), "end")
    expression = value.get("expression")
    if expression is not None and (not isinstance(expression, str) or not expression):
        raise ValueError(
            "qualifiers.valid_time.expression must be a non-empty string or null"
        )
    if start is None and end is None and expression is None:
        raise ValueError("qualifiers.valid_time requires at least one non-null value")
    if start is not None and end is not None:
        try:
            if start > end:
                raise ValueError(
                    "qualifiers.valid_time start must be before or equal to end"
                )
        except TypeError as exc:
            raise ValueError(
                "qualifiers.valid_time start and end must be comparable"
            ) from exc


def _validate_valid_time_timestamp(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"qualifiers.valid_time.{field} must be an ISO-8601 string or null"
        )
    try:
        return datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise ValueError(
            f"qualifiers.valid_time.{field} must be an ISO-8601 string or null"
        ) from exc
