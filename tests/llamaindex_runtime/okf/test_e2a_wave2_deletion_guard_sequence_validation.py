"""Parameter-boundary validation tests for has_external_fact_dependency."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from llamaindex_runtime.okf._e2a_materialization_deletion_guards import (
    has_external_fact_dependency,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class RecordingCursor:
    """Minimal fake cursor for parameter validation tests."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, object | None]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.execute_calls.append((statement, parameters))

    def fetchall(self) -> tuple[dict[str, bool], ...]:
        return ({"present": False},)


# Test data: non-empty scalar representations that should be rejected
SCALAR_REPRESENTATIONS: Sequence[object] = [
    pytest.param("owner-1", id="str"),
    pytest.param(b"owner-1", id="bytes"),
    pytest.param(bytearray(b"owner-1"), id="bytearray"),
    pytest.param(memoryview(b"owner-1"), id="memoryview"),
]


@pytest.mark.parametrize("scalar_value", SCALAR_REPRESENTATIONS)
def test_retiring_owner_ids_rejects_scalar_before_cursor_activity(
    scalar_value: object,
) -> None:
    """retiring_owner_ids must reject scalar values before cursor activity."""
    cursor = RecordingCursor()

    with pytest.raises(ValueError, match="retiring ownership identifiers are invalid"):
        has_external_fact_dependency(
            cursor,
            fact_id="entity-1",
            kind="entity",
            retiring_owner_ids=scalar_value,  # type: ignore[arg-type]
        )

    assert len(cursor.execute_calls) == 0


@pytest.mark.parametrize("scalar_value", SCALAR_REPRESENTATIONS)
def test_safely_retiring_relation_ids_rejects_scalar_before_cursor_activity(
    scalar_value: object,
) -> None:
    """safely_retiring_relation_ids must reject scalar values before cursor activity."""
    cursor = RecordingCursor()

    with pytest.raises(
        ValueError, match="safely retiring relation identifiers are invalid"
    ):
        has_external_fact_dependency(
            cursor,
            fact_id="entity-1",
            kind="entity",
            retiring_owner_ids=("owner-1",),
            safely_retiring_relation_ids=scalar_value,  # type: ignore[arg-type]
        )

    assert len(cursor.execute_calls) == 0


def test_safely_retiring_relation_ids_normalizes_to_sorted_deduplicated() -> None:
    """safely_retiring_relation_ids must normalize to sorted deduplicated list."""
    cursor = RecordingCursor()

    has_external_fact_dependency(
        cursor,
        fact_id="entity-1",
        kind="entity",
        retiring_owner_ids=("owner-1",),
        safely_retiring_relation_ids=("relation-b", "relation-a", "relation-a"),
    )

    # Find the relations WHERE probe with the safely_retiring_relation_ids parameter
    relations_probe = next(
        (
            (stmt, params)
            for stmt, params in cursor.execute_calls
            if "relations WHERE" in stmt and "source_entity_id" in stmt
        ),
        None,
    )
    assert relations_probe is not None, "relations probe not found"
    _, params = relations_probe
    assert isinstance(params, tuple)
    # The last parameter should be the normalized relation list
    relation_param = params[-1]
    # _array_parameters converts tuple to list
    assert relation_param == ["relation-a", "relation-b"]


def test_invalid_kind_error_precedes_sequence_validation() -> None:
    """Invalid kind error must precede sequence validation."""
    cursor = RecordingCursor()

    with pytest.raises(ValueError, match="ownership fact kind is invalid"):
        has_external_fact_dependency(
            cursor,
            fact_id="entity-1",
            kind="concept",
            retiring_owner_ids="owner-1",  # type: ignore[arg-type]
        )

    assert len(cursor.execute_calls) == 0
