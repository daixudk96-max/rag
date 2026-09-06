"""Deterministic structural hashes for raw OKF synchronization."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Any, cast

from llamaindex_runtime.okf.sidecar import SpanSidecar

_CANONICAL_MAX_DEPTH = 64
_CANONICAL_MAX_WORK = 10_000
_CYCLE_ERROR = "frontmatter_canonical_cycle"
_UNSUPPORTED_ERROR = "frontmatter_canonical_unsupported"
_RESOURCE_ERROR = "frontmatter_canonical_resource_limit"


def canonical_serialize(value: Any) -> bytes:
    """Serialize the exact canonical-v1 value domain as stable UTF-8 JSON."""
    return json.dumps(
        _normalize_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_hash(frontmatter: dict[str, Any], sidecar: SpanSidecar) -> str:
    """Return SHA256 for exact-dict frontmatter and sidecar coordinates."""
    return hashlib.sha256(
        canonical_serialize(frontmatter)
        + canonical_serialize([span.to_dict() for span in sidecar.spans])
    ).hexdigest()


def validate_canonical_value(value: Any) -> None:
    """Fail closed unless ``value`` belongs to the frozen canonical-v1 domain."""
    _normalize_value(value)


def _normalize_value(value: Any) -> Any:
    return _normalize(value, _TraversalState(), 0)


class _TraversalState:
    def __init__(self) -> None:
        self.active_ids: set[int] = set()
        self.work = 0

    def visit(self, value: object, depth: int) -> None:
        self.work += 1
        if self.work > _CANONICAL_MAX_WORK or depth > _CANONICAL_MAX_DEPTH:
            raise ValueError(_RESOURCE_ERROR)
        if id(value) in self.active_ids:
            raise ValueError(_CYCLE_ERROR)


def _normalize(value: Any, state: _TraversalState, depth: int) -> Any:
    state.visit(value, depth)
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(_UNSUPPORTED_ERROR)
        return value
    if type(value) is str:
        _validate_utf8_string(value)
        return value
    if type(value) is datetime:
        if value.tzinfo is not None and type(value.tzinfo) is not timezone:
            raise ValueError(_UNSUPPORTED_ERROR)
        return datetime.isoformat(value)
    if type(value) is date:
        return date.isoformat(value)
    if type(value) is dict:
        return _normalize_dict(value, state, depth)
    if type(value) in (list, tuple):
        return _normalize_sequence(value, state, depth)
    raise ValueError(_UNSUPPORTED_ERROR)


def _normalize_dict(
    value: dict[Any, Any], state: _TraversalState, depth: int
) -> dict[str, Any]:
    state.active_ids.add(id(value))
    try:
        normalized: dict[str, Any] = {}
        for key, item in dict.items(value):
            if type(key) is not str:
                raise ValueError(_UNSUPPORTED_ERROR)
            _validate_utf8_string(key)
            normalized[key] = _normalize(item, state, depth + 1)
        return normalized
    finally:
        state.active_ids.remove(id(value))


def _normalize_sequence(
    value: list[Any] | tuple[Any, ...], state: _TraversalState, depth: int
) -> list[Any]:
    state.active_ids.add(id(value))
    try:
        if type(value) is list:
            iterator = list.__iter__(cast(list[Any], value))
        else:
            iterator = tuple.__iter__(cast(tuple[Any, ...], value))
        return [_normalize(item, state, depth + 1) for item in iterator]
    finally:
        state.active_ids.remove(id(value))


def _validate_utf8_string(value: str) -> None:
    try:
        str.encode(value, "utf-8")
    except UnicodeEncodeError:
        raise ValueError(_UNSUPPORTED_ERROR) from None
