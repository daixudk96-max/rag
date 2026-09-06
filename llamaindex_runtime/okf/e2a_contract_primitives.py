"""Shared immutable primitives for E2a corpus-admission contracts."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID

from .rooted_open import validate_relative_path


def _canonical_value(value: object) -> object:
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is str:
        return _unicode_scalar(value, "JSON string")
    if type(value) is float:
        if math.isfinite(value):
            return value
        raise ValueError("JSON values must be finite")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        return {
            _unicode_scalar(key, "JSON object key"): _canonical_value(child)
            for key, child in value.items()
        }
    if type(value) in {list, tuple}:
        return [_canonical_value(child) for child in cast(Iterable[object], value)]
    raise ValueError("JSON value is not canonical")


def _frozen_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return MappingProxyType(
        {key: _freeze_json(child) for key, child in value.items() if _string_key(key)}
    )


def _string_key(key: object) -> bool:
    _unicode_scalar(key, "JSON object key")
    return True


def _unicode_scalar(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be a Unicode scalar string")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError(f"{name} must be a Unicode scalar string") from None
    return value


def _freeze_json(value: object) -> object:
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is str:
        return _unicode_scalar(value, "JSON string")
    if type(value) is float:
        if math.isfinite(value):
            return value
        raise ValueError("JSON values must be finite")
    if isinstance(value, Mapping):
        return _frozen_mapping(value, "metadata")
    if type(value) in {list, tuple}:
        return tuple(_freeze_json(item) for item in cast(Iterable[object], value))
    raise ValueError("JSON value is not canonical")


def _tuple(value: object, name: str) -> tuple[object, ...]:
    if type(value) not in {tuple, list}:
        raise ValueError(f"{name} must be a tuple")
    return tuple(cast(Iterable[object], value))


def _frozen_json_tuple(value: object, name: str) -> tuple[object, ...]:
    if type(value) not in {tuple, list}:
        raise ValueError(f"{name} must be a tuple")
    return tuple(_freeze_json(item) for item in cast(Iterable[object], value))


def _typed(values: tuple[object, ...], expected: type[object], name: str) -> None:
    if any(type(value) is not expected for value in values):
        raise ValueError(f"{name} has invalid values")


def _counts(value: Mapping[str, int]) -> Mapping[str, int]:
    if not isinstance(value, Mapping) or any(
        type(key) is not str or type(count) is not int or count < 0
        for key, count in value.items()
    ):
        raise ValueError("DML counts must be non-negative integer mappings")
    return MappingProxyType(
        {_unicode_scalar(key, "DML count key"): count for key, count in value.items()}
    )


def _uuid(value: object, name: str) -> None:
    value = _unicode_scalar(value, name)
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError(f"{name} must be a UUID") from None
    if str(parsed) != value:
        raise ValueError(f"{name} must be a UUID")


def _digest(value: object, name: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    _unicode_scalar(value, name)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _path(value: object) -> None:
    if type(value) is not str or "\\" in value:
        raise ValueError("safe relative path is required")
    _unicode_scalar(value, "relative path")
    try:
        validate_relative_path(value, windows=True)
    except ValueError:
        raise ValueError("safe relative path is required") from None


def _unique(values: tuple[Any, ...], key: Any, name: str) -> None:
    if len({key(value) for value in values}) != len(values):
        raise ValueError(f"duplicate {name} identity")
