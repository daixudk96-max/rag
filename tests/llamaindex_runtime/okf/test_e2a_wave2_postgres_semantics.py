"""Pure PostgreSQL NUMERIC/JSONB semantic parity regressions for E2a."""

from __future__ import annotations

import importlib
from decimal import Decimal

from llamaindex_runtime.okf._e2a_materialization_values import SQL_NULL


def _equal(existing: object, desired: object, *, cast: str | None = None) -> bool:
    semantics = importlib.import_module(
        "llamaindex_runtime.okf._e2a_postgres_semantics"
    )
    return semantics.postgres_values_equal(existing, desired, cast=cast)


def test_numeric_float_and_decimal_follow_postgresql_numeric_equality() -> None:
    assert _equal(Decimal("0.1"), 0.1)
    assert not _equal(Decimal("0.1001"), 0.1)
    assert not _equal(True, 1)
    assert not _equal(1, True)


def test_nested_jsonb_normalizes_key_order_and_numeric_representation() -> None:
    existing = {
        "z": [Decimal("0.1"), {"json_null": None, "rank": Decimal("2.0")}],
        "a": {"enabled": False},
    }
    desired = {
        "a": {"enabled": False},
        "z": [0.1, {"rank": 2, "json_null": None}],
    }

    assert _equal(existing, desired, cast="jsonb")


def test_jsonb_does_not_collapse_boolean_numeric_or_array_order() -> None:
    assert not _equal({"value": True}, {"value": 1}, cast="jsonb")
    assert not _equal({"items": [1, 2]}, {"items": [2, 1]}, cast="jsonb")


def test_sql_null_and_json_null_remain_distinct() -> None:
    assert not _equal(SQL_NULL, None, cast="jsonb")
    assert _equal(None, None, cast="jsonb")


def test_postgres_numeric_equal_values_not_rejected_for_digit_count() -> None:
    # Trailing zeros must not be mistaken for excess precision: PostgreSQL
    # NUMERIC considers Decimal("0.1000000000000000") equal to 0.1.
    assert _equal(Decimal("0.1000000000000000"), 0.1)
    assert _equal(0.1, Decimal("0.1000000000000000"))
    # Exact integer/Decimal parity must survive past 15 significant digits.
    assert _equal(Decimal("1234567890123456"), 1234567890123456)
    assert _equal(1234567890123456, Decimal("1234567890123456"))


def test_jsonb_nested_trailing_zero_decimal_not_rejected_for_digit_count() -> None:
    existing = {"metric": Decimal("0.1000000000000000")}
    desired = {"metric": 0.1}
    assert _equal(existing, desired, cast="jsonb")


def test_postgres_numeric_semantics_preserves_boolean_distinction_and_nonfinite_fail_closed() -> (
    None
):
    # Boolean distinction must survive numeric normalization.
    assert not _equal(True, 1)
    assert not _equal(1, True)
    assert not _equal(True, 1.0)
    assert not _equal(1.0, True)
    # Non-finite floats must remain fail-closed against any finite Decimal.
    assert not _equal(float("inf"), Decimal("1"))
    assert not _equal(Decimal("1"), float("inf"))
    assert not _equal(float("-inf"), Decimal("1"))
    assert not _equal(float("nan"), Decimal("1"))
    assert not _equal(Decimal("1"), float("nan"))


def test_postgres_semantics_fails_closed_for_same_nonfinite_pairs() -> None:
    # Same non-finite values must NOT compare equal under PostgreSQL NUMERIC
    # semantics: non-finite payloads are non-numeric and must fail closed,
    # even when both sides are the same infinity.
    assert not _equal(float("inf"), float("inf"))
    assert not _equal(float("-inf"), float("-inf"))
    assert not _equal(Decimal("Infinity"), float("inf"))
    assert not _equal(float("inf"), Decimal("Infinity"))
    assert not _equal(Decimal("-Infinity"), float("-inf"))
    assert not _equal(float("-inf"), Decimal("-Infinity"))
    # Nested JSONB same-nonfinite must also fail closed; the helper accepts the
    # structure, so the non-finite payload must not compare equal.
    assert not _equal({"v": float("inf")}, {"v": float("inf")}, cast="jsonb")
    assert not _equal({"v": float("-inf")}, {"v": float("-inf")}, cast="jsonb")


def test_postgres_numeric_semantics_requires_integer_float_equivalence_but_preserves_boolean_distinction() -> (
    None
):
    # PostgreSQL NUMERIC considers 1 and 1.0 equal: integer and float with same
    # mathematical value must compare equal in both directions.
    assert _equal(1, 1.0)
    assert _equal(1.0, 1)
    # High-precision Decimal from string must equal its float representation.
    assert _equal(Decimal(str(1.1234567890123457)), 1.1234567890123457)
    assert _equal(1.1234567890123457, Decimal(str(1.1234567890123457)))
    # Boolean distinction must survive: True is not 1, False is not 0.
    assert not _equal(True, 1)
    assert not _equal(1, True)
    assert not _equal(True, 1.0)
    assert not _equal(1.0, True)
    assert not _equal(False, 0)
    assert not _equal(0, False)
    assert not _equal(False, 0.0)
    assert not _equal(0.0, False)
