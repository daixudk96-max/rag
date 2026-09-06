"""PostgreSQL NUMERIC/JSONB semantic equality for E2a reconciliation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from ._e2a_materialization_values import SQL_NULL


def _normalize_numeric(value: object) -> tuple[bool, Decimal | None]:
    """Normalize a value to PostgreSQL NUMERIC semantics.

    Returns:
        (is_numeric, normalized_decimal):
        - (True, Decimal) for finite int/float/Decimal
        - (True, None) for non-finite float/Decimal (infinity, NaN)
        - (False, None) for non-numeric types (bool, str, etc.)
    """
    # Booleans are explicitly NOT numeric in PostgreSQL JSONB semantics
    if type(value) is bool:
        return False, None
    if type(value) is int:
        return True, Decimal(value)
    if type(value) is float:
        if not math.isfinite(value):
            return True, None
        try:
            return True, Decimal(str(value))
        except (InvalidOperation, ValueError):
            return True, None
    if isinstance(value, Decimal):
        return True, value if value.is_finite() else None
    return False, None


def postgres_values_equal(
    existing: object,
    desired: object,
    *,
    cast: Literal["jsonb"] | None = None,
) -> bool:
    """Compare values using PostgreSQL NUMERIC/JSONB semantics.

    PostgreSQL NUMERIC type considers Decimal("0.1") equal to 0.1 (float).
    PostgreSQL JSONB normalizes key order and numeric representation.

    Args:
        existing: The existing database value.
        desired: The desired value to compare against.
        cast: Optional cast hint - "jsonb" enables JSONB normalization.

    Returns:
        True if values are semantically equal in PostgreSQL terms.
    """
    if existing is SQL_NULL and desired is None:
        return False
    if existing is None and desired is None:
        return True
    if existing is SQL_NULL or desired is SQL_NULL:
        return False
    if existing is None or desired is None:
        return False
    # Bool vs int must be checked before generic equality (True == 1 in Python)
    if cast == "jsonb":
        return _jsonb_equal(existing, desired)
    if type(existing) is bool or type(desired) is bool:
        return type(existing) is type(desired) and existing == desired
    # Check for non-finite numeric values before type equality check
    # Non-finite values fail closed (even same non-finite pairs)
    existing_is_numeric, existing_normalized = _normalize_numeric(existing)
    desired_is_numeric, desired_normalized = _normalize_numeric(desired)
    if existing_is_numeric and desired_is_numeric:
        if existing_normalized is None or desired_normalized is None:
            return False
        return existing_normalized == desired_normalized
    if type(existing) is type(desired):
        return existing == desired
    return False


def _numeric_equal(existing: object, desired: object) -> bool:
    """Compare using PostgreSQL NUMERIC semantics.

    PostgreSQL NUMERIC considers Decimal("0.1") == 0.1.
    But bool and int are distinct types in JSONB.
    Non-finite values fail closed (even same non-finite pairs).
    """
    existing_is_numeric, existing_normalized = _normalize_numeric(existing)
    desired_is_numeric, desired_normalized = _normalize_numeric(desired)

    if not existing_is_numeric or not desired_is_numeric:
        return False

    # Non-finite values fail closed
    if existing_normalized is None or desired_normalized is None:
        return False

    return existing_normalized == desired_normalized


def _jsonb_equal(existing: object, desired: object) -> bool:
    """Compare using PostgreSQL JSONB semantics.

    JSONB:
    - Normalizes key order in objects
    - Distinguishes bool from int (true != 1)
    - Preserves array order
    - Considers Decimal("0.1") equivalent to 0.1 in numeric context (without precision loss)
    """
    # Boolean comparison must be exact type match
    if type(existing) is bool or type(desired) is bool:
        if type(existing) is not type(desired):
            return False
        return existing == desired

    # Numeric comparison using PostgreSQL NUMERIC semantics
    existing_is_numeric, existing_normalized = _normalize_numeric(existing)
    desired_is_numeric, desired_normalized = _normalize_numeric(desired)

    if existing_is_numeric and desired_is_numeric:
        # Non-finite values fail closed (even same non-finite pairs)
        if existing_normalized is None or desired_normalized is None:
            return False
        return existing_normalized == desired_normalized

    # String comparison
    if type(existing) is str and type(desired) is str:
        return existing == desired

    # Object comparison (key order normalized)
    if isinstance(existing, Mapping) and isinstance(desired, Mapping):
        return _jsonb_object_equal(existing, desired)

    # Array comparison (order preserved)
    if type(existing) in (list, tuple) and type(desired) in (list, tuple):
        return _jsonb_array_equal(
            cast("list[object] | tuple[object, ...]", existing),
            cast("list[object] | tuple[object, ...]", desired),
        )

    return existing == desired


def _jsonb_object_equal(
    existing: Mapping[str, object], desired: Mapping[str, object]
) -> bool:
    """Compare JSONB objects with key-order normalization."""
    if set(existing) != set(desired):
        return False
    for key in existing:
        if not _jsonb_equal(existing[key], desired[key]):
            return False
    return True


def _jsonb_array_equal(existing: list | tuple, desired: list | tuple) -> bool:
    """Compare JSONB arrays - order matters."""
    if len(existing) != len(desired):
        return False
    for left, right in zip(existing, desired):
        if not _jsonb_equal(left, right):
            return False
    return True


__all__ = ["postgres_values_equal"]
