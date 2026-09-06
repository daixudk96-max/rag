"""E2a-only strict frontmatter parsing without changing shared parser semantics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node, ScalarNode

from .contracts import MAX_FRONTMATTER_BYTES, extract_bounded_frontmatter

MAX_E2A_YAML_DEPTH = 64
MAX_E2A_YAML_NODES = 10_000
MAX_E2A_FRONTMATTER_BYTES = MAX_FRONTMATTER_BYTES
MAX_E2A_DELIMITER_HWS = 64
_E2A_DELIMITER_LOOKAHEAD_BYTES = 3 + MAX_E2A_DELIMITER_HWS + 2
_E2A_INVALID = "e2a_frontmatter_invalid"
_E2A_RESOURCE_LIMIT = "e2a_frontmatter_resource_limit"


class _E2aYamlResourceLimit(ValueError):
    pass


class _E2aSafeLoader(yaml.SafeLoader):
    """Single-pass E2a loader with composition and mapping safety gates."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0
        self._nodes = 0

    def compose_node(self, parent: Any, index: Any) -> Node:
        if self.check_event(AliasEvent):
            raise ValueError(_E2A_INVALID)
        self._depth += 1
        self._nodes += 1
        try:
            if self._depth > MAX_E2A_YAML_DEPTH or self._nodes > MAX_E2A_YAML_NODES:
                raise _E2aYamlResourceLimit
            return cast(Node, super().compose_node(parent, index))
        finally:
            self._depth -= 1

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        seen: set[str] = set()
        for key_node, _ in node.value:
            if (
                not isinstance(key_node, ScalarNode)
                or key_node.tag != "tag:yaml.org,2002:str"
                or key_node.value == "<<"
            ):
                raise ValueError(_E2A_INVALID)
            _require_unicode_scalar(key_node.value)
            if key_node.value in seen:
                raise ValueError(_E2A_INVALID)
            seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)


def load_strict_e2a_frontmatter(document: str) -> tuple[dict[str, Any], str]:
    """Parse one bounded E2a frontmatter document with stable redacted errors."""
    yaml_block, body = _extract_e2a_frontmatter(document)
    parsed = _load_e2a_yaml(yaml_block)
    if type(parsed) is not dict:
        raise ValueError(_E2A_INVALID)
    _validate_unicode_scalars(parsed)
    return parsed, body.replace("\r\n", "\n").removesuffix("\n")


def validate_no_duplicate_yaml_keys(document: str) -> None:
    """Run the E2a single-pass safety loader for an already-read raw snapshot."""
    yaml_block, _ = _extract_e2a_frontmatter(document)
    _validate_unicode_scalars(_load_e2a_yaml(yaml_block))


def validate_strict_e2a_raw_frontmatter_bytes(document: bytes) -> None:
    """Validate bounded raw frontmatter without decoding or retaining its body."""
    yaml_block = _extract_e2a_raw_frontmatter_bytes(document)
    _validate_unicode_scalars(_load_e2a_yaml(yaml_block))


def _extract_e2a_raw_frontmatter_bytes(document: object) -> str:
    if type(document) is not bytes:
        raise ValueError(_E2A_INVALID)
    opening_end = _e2a_delimiter_end(document, 0)
    if opening_end is None:
        raise ValueError(_E2A_INVALID)
    yaml_start = opening_end
    payload_limit = yaml_start + MAX_E2A_FRONTMATTER_BYTES
    candidate_search_end = min(len(document), payload_limit + 5)
    position = yaml_start
    while position <= payload_limit:
        closing_start = document.find(b"\n---", position, candidate_search_end)
        if closing_start < 0:
            break
        yaml_end = closing_start - (document[closing_start - 1] == ord("\r"))
        if yaml_end - yaml_start > MAX_E2A_FRONTMATTER_BYTES:
            break
        closing_end = _e2a_delimiter_end(document, closing_start + 1)
        if closing_end is not None:
            try:
                return document[yaml_start:yaml_end].decode("utf-8", "strict")
            except UnicodeDecodeError:
                raise ValueError(_E2A_INVALID) from None
        position = closing_start + 1
    raise ValueError(_E2A_INVALID)


def _e2a_delimiter_end(document: bytes, start: int) -> int | None:
    if document[start : start + 3] != b"---":
        return None
    lookahead_end = min(len(document), start + _E2A_DELIMITER_LOOKAHEAD_BYTES)
    position = start + 3
    horizontal_whitespace = 0
    while position < lookahead_end:
        character = document[position]
        if character in {ord(" "), ord("\t")}:
            horizontal_whitespace += 1
            if horizontal_whitespace > MAX_E2A_DELIMITER_HWS:
                return None
            position += 1
            continue
        if character == ord("\n"):
            return position + 1
        if (
            character == ord("\r")
            and position + 1 < lookahead_end
            and document[position + 1] == ord("\n")
        ):
            return position + 2
        return None
    return None


def _extract_e2a_frontmatter(document: object) -> tuple[str, str]:
    try:
        validated = _require_unicode_scalar(document)
        extracted = extract_bounded_frontmatter(validated)
    except (TypeError, UnicodeEncodeError, ValueError):
        raise ValueError(_E2A_INVALID) from None
    if extracted is None:
        raise ValueError(_E2A_INVALID)
    return extracted


def _load_e2a_yaml(yaml_block: str) -> dict[str, Any]:
    loader = _E2aSafeLoader(yaml_block)
    try:
        parsed = loader.get_single_data()
        if parsed is None:
            return {}
        if type(parsed) is not dict:
            raise ValueError(_E2A_INVALID)
        return parsed
    except _E2aYamlResourceLimit:
        raise ValueError(_E2A_RESOURCE_LIMIT) from None
    except (TypeError, UnicodeEncodeError, ValueError, yaml.YAMLError):
        raise ValueError(_E2A_INVALID) from None
    finally:
        loader.dispose()


def _validate_unicode_scalars(value: object) -> None:
    if type(value) is str:
        _require_unicode_scalar(value)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _require_unicode_scalar(key)
            _validate_unicode_scalars(item)
        return
    if type(value) in {list, tuple}:
        for item in cast(Iterable[object], value):
            _validate_unicode_scalars(item)


def _require_unicode_scalar(value: object) -> str:
    if type(value) is not str:
        raise ValueError(_E2A_INVALID)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError(_E2A_INVALID) from None
    return value
