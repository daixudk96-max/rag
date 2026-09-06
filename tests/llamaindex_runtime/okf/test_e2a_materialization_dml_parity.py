"""RED cursor-only regressions for E2a persisted-value DML parity."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from decimal import Decimal

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
)
from llamaindex_runtime.okf import (
    e2a_materialization_dml as dml,
)
from llamaindex_runtime.okf.e2a_materialization_dml import upsert_if_changed


class PgVectorLike:
    """Local stand-in for a pgvector adapter value returned by a cursor."""

    def __init__(self, components: tuple[float, ...]) -> None:
        self._components = components

    def to_list(self) -> list[float]:
        return list(self._components)


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        return []

    def fetchone(self) -> tuple[int, ...] | None:
        return (1,)


def _dml_calls(cursor: _Cursor) -> list[tuple[str, object | None]]:
    return [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]


def _upsert(
    cursor: _Cursor,
    *,
    table: str,
    row: Mapping[str, object],
    key_fields: tuple[str, ...],
    mutable_fields: tuple[str, ...],
    existing: Mapping[str, object] | None,
    casts: Mapping[str, str] | None = None,
) -> DmlRecorder:
    recorder = DmlRecorder()
    upsert_if_changed(
        cursor,
        table,
        row,
        key_fields,
        mutable_fields,
        existing,
        recorder,
        casts=casts,
    )
    return recorder


def _relation_row(**overrides: object) -> dict[str, object]:
    return {"relation_id": "relation-1", "confidence": 0.75, **overrides}


def _vector_components(first: float = 1.0) -> tuple[float, ...]:
    return (first, *(float(index) for index in range(1, 16)))


def _vector_text(components: tuple[float, ...]) -> str:
    return "[" + ",".join(str(component) for component in components) + "]"


def _vector_row(embedding: object) -> dict[str, object]:
    return {"chunk_id": "chunk-1", "embedding": embedding}


_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS: tuple[str, ...] = (
    "version_id",
    "chunk_type",
    "chunk_order",
    "token_count",
    "text_preview",
    "page_no",
    "heading_path",
    "node_id",
    "embedding",
)

_VECTOR_CHUNKS_CASTS: Mapping[str, str] = {"embedding": "vector"}


def _scoped_vector_row(embedding: object) -> dict[str, object]:
    return {
        "chunk_id": "chunk-1",
        "version_id": "version-1",
        "chunk_type": "text",
        "chunk_order": 0,
        "token_count": 16,
        "text_preview": "preview",
        "page_no": 1,
        "heading_path": "root",
        "node_id": "node-1",
        "embedding": embedding,
    }


def test_numeric_decimal_parity_skips_unchanged_dml_without_collapsing_booleans() -> (
    None
):
    changed_cursor = _Cursor()
    changed_recorder = _upsert(
        changed_cursor,
        table="relations",
        row=_relation_row(),
        key_fields=("relation_id",),
        mutable_fields=("confidence",),
        existing=_relation_row(confidence=Decimal("0.751")),
    )
    assert len(_dml_calls(changed_cursor)) == 1
    assert changed_recorder.issued_dml_by_table == {"relations": 1}

    for persisted, desired in ((True, 1), (1, True)):
        boolean_cursor = _Cursor()
        _upsert(
            boolean_cursor,
            table="relations",
            row=_relation_row(confidence=desired),
            key_fields=("relation_id",),
            mutable_fields=("confidence",),
            existing=_relation_row(confidence=persisted),
        )
        assert len(_dml_calls(boolean_cursor)) == 1

    equivalent_cursor = _Cursor()
    _upsert(
        equivalent_cursor,
        table="relations",
        row=_relation_row(),
        key_fields=("relation_id",),
        mutable_fields=("confidence",),
        existing=_relation_row(confidence=Decimal("0.750")),
    )

    assert _dml_calls(equivalent_cursor) == []


def test_jsonb_parity_normalizes_object_order_and_numeric_spelling_only() -> None:
    reversed_array_cursor = _Cursor()
    _upsert(
        reversed_array_cursor,
        table="relations",
        row={"relation_id": "relation-1", "qualifiers": {"items": [2, 1]}},
        key_fields=("relation_id",),
        mutable_fields=("qualifiers",),
        existing={"relation_id": "relation-1", "qualifiers": {"items": [1, 2]}},
        casts={"qualifiers": "jsonb"},
    )
    assert len(_dml_calls(reversed_array_cursor)) == 1

    boolean_cursor = _Cursor()
    _upsert(
        boolean_cursor,
        table="relations",
        row={"relation_id": "relation-1", "qualifiers": {"enabled": 1}},
        key_fields=("relation_id",),
        mutable_fields=("qualifiers",),
        existing={"relation_id": "relation-1", "qualifiers": {"enabled": True}},
        casts={"qualifiers": "jsonb"},
    )
    assert len(_dml_calls(boolean_cursor)) == 1

    equivalent_cursor = _Cursor()
    _upsert(
        equivalent_cursor,
        table="relations",
        row={
            "relation_id": "relation-1",
            "qualifiers": {
                "array": [{"position": 1}, 2],
                "metadata": {"scale": 1, "signed_zero": 0},
            },
        },
        key_fields=("relation_id",),
        mutable_fields=("qualifiers",),
        existing={
            "relation_id": "relation-1",
            "qualifiers": {
                "metadata": {"signed_zero": -0.0, "scale": 1.0},
                "array": [{"position": 1.0}, 2.0],
            },
        },
        casts={"qualifiers": "jsonb"},
    )

    assert _dml_calls(equivalent_cursor) == []


def test_vector_pgvector_like_parity_uses_float32_components() -> None:
    changed_cursor = _Cursor()
    _upsert(
        changed_cursor,
        table="vector_chunks",
        row=_scoped_vector_row(_vector_components(1.0 + 2**-20)),
        key_fields=("chunk_id",),
        mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
        existing=_scoped_vector_row(_vector_text(_vector_components())),
        casts=_VECTOR_CHUNKS_CASTS,
    )
    assert len(_dml_calls(changed_cursor)) == 1

    equivalent_cursor = _Cursor()
    _upsert(
        equivalent_cursor,
        table="vector_chunks",
        row=_scoped_vector_row(_vector_components(1.0 + 2**-25)),
        key_fields=("chunk_id",),
        mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
        existing=_scoped_vector_row(PgVectorLike(_vector_components())),
        casts=_VECTOR_CHUNKS_CASTS,
    )
    assert _dml_calls(equivalent_cursor) == []

    changed_pgvector_cursor = _Cursor()
    _upsert(
        changed_pgvector_cursor,
        table="vector_chunks",
        row=_scoped_vector_row(_vector_components(1.0 + 2**-20)),
        key_fields=("chunk_id",),
        mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
        existing=_scoped_vector_row(PgVectorLike(_vector_components())),
        casts=_VECTOR_CHUNKS_CASTS,
    )
    assert len(_dml_calls(changed_pgvector_cursor)) == 1


@pytest.mark.skipif(
    importlib.util.find_spec("numpy") is None,
    reason="NumPy is an optional already-installed persisted-vector representation",
)
def test_vector_numpy_float32_parity_skips_unchanged_dml() -> None:
    import numpy as np

    cursor = _Cursor()
    _upsert(
        cursor,
        table="vector_chunks",
        row=_scoped_vector_row(_vector_components(1.0 + 2**-25)),
        key_fields=("chunk_id",),
        mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
        existing=_scoped_vector_row(np.array(_vector_components(), dtype=np.float32)),
        casts=_VECTOR_CHUNKS_CASTS,
    )

    assert _dml_calls(cursor) == []


@pytest.mark.parametrize(
    "embedding",
    (
        pytest.param(_vector_components()[:-1], id="fifteen-components"),
        pytest.param(_vector_components() + (16.0,), id="seventeen-components"),
        pytest.param(_vector_components(float("nan")), id="nan-component"),
        pytest.param(_vector_components(float("inf")), id="infinite-component"),
    ),
)
def test_vectors_require_exactly_sixteen_finite_components_before_dml(
    embedding: tuple[float, ...],
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError, match="vector chunk embedding is invalid"):
        _upsert(
            cursor,
            table="vector_chunks",
            row=_scoped_vector_row(embedding),
            key_fields=("chunk_id",),
            mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
            existing=None,
            casts=_VECTOR_CHUNKS_CASTS,
        )

    assert _dml_calls(cursor) == []


@pytest.mark.parametrize(
    ("row", "existing"),
    (
        pytest.param(
            {"relation_id": "relation-1", "confidence": 0.75, "unexpected": "x"},
            {"relation_id": "relation-1", "confidence": 0.75},
            id="unexpected-desired-field",
        ),
        pytest.param(
            {"relation_id": "relation-1"},
            {"relation_id": "relation-1", "confidence": 0.75},
            id="missing-desired-field",
        ),
        pytest.param(
            {"relation_id": "relation-1", "confidence": 0.75},
            {"relation_id": "relation-1", "confidence": 0.75, "unexpected": "x"},
            id="unexpected-existing-field",
        ),
        pytest.param(
            {"relation_id": "relation-1", "confidence": 0.75},
            {"relation_id": "relation-1"},
            id="missing-existing-field",
        ),
    ),
)
def test_generic_upsert_rejects_non_projection_rows_before_cursor_execute(
    row: Mapping[str, object], existing: Mapping[str, object]
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError, match="upsert projection"):
        _upsert(
            cursor,
            table="relations",
            row=row,
            key_fields=("relation_id",),
            mutable_fields=("confidence",),
            existing=existing,
        )

    assert cursor.calls == []


class _MutatingMapping(Mapping[str, object]):
    """Expose replacement values only after an iterator has been consumed."""

    def __init__(
        self, original: Mapping[str, object], replacement: Mapping[str, object]
    ) -> None:
        self._current = dict(original)
        self._replacement = dict(replacement)

    def __getitem__(self, key: str) -> object:
        return self._current[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield from tuple(self._current)
        self._current = dict(self._replacement)

    def __len__(self) -> int:
        return len(self._current)


class _ChangingCasts(Mapping[str, str]):
    """Mutate after exposing one valid cast snapshot."""

    def __init__(self, malicious: str) -> None:
        self._current = {"qualifiers": "jsonb"}
        self._malicious = malicious

    def __getitem__(self, key: str) -> str:
        return self._current[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._current)

    def __len__(self) -> int:
        return len(self._current)

    def items(self):  # type: ignore[no-untyped-def]
        snapshot = tuple(self._current.items())
        self._current = {"qualifiers": self._malicious}
        return snapshot


class _ChangingJsonObject(Mapping[str, object]):
    def __init__(self) -> None:
        self._value = "first"

    def __getitem__(self, key: str) -> object:
        if key != "phase":
            raise KeyError(key)
        return self._value

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(("phase",))

    def __len__(self) -> int:
        return 1

    def items(self):  # type: ignore[no-untyped-def]
        snapshot = (("phase", self._value),)
        self._value = "second"
        return snapshot


class _ChangingVector:
    def __init__(self) -> None:
        self.calls = 0

    def to_list(self) -> list[float]:
        self.calls += 1
        return list(_vector_components(float(self.calls)))


class _BrokenVector:
    def to_list(self) -> list[float]:
        raise RuntimeError("adapter fault")


def test_upsert_snapshots_mutable_rows_and_existing_before_comparison_and_binding() -> (
    None
):
    cursor = _Cursor()
    row = _MutatingMapping(_relation_row(), _relation_row(confidence=0.99))
    existing = _MutatingMapping(_relation_row(), _relation_row(confidence=0.25))

    _upsert(
        cursor,
        table="relations",
        row=row,
        key_fields=("relation_id",),
        mutable_fields=("confidence",),
        existing=existing,
    )

    assert _dml_calls(cursor) == []


def test_upsert_snapshots_casts_before_internal_sql_fragment_selection() -> None:
    cursor = _Cursor()
    malicious = "jsonb) ON CONFLICT (relation_id) DO NOTHING"

    _upsert(
        cursor,
        table="relations",
        row={"relation_id": "relation-1", "qualifiers": {"safe": True}},
        key_fields=("relation_id",),
        mutable_fields=("qualifiers",),
        existing=None,
        casts=_ChangingCasts(malicious),
    )

    assert len(_dml_calls(cursor)) == 1
    assert malicious not in _dml_calls(cursor)[0][0]
    assert "::jsonb" in _dml_calls(cursor)[0][0]


def test_jsonb_and_vector_values_are_prepared_once_for_all_upsert_stages() -> None:
    json_cursor = _Cursor()
    changing_json = _ChangingJsonObject()
    _upsert(
        json_cursor,
        table="relations",
        row={"relation_id": "relation-1", "qualifiers": changing_json},
        key_fields=("relation_id",),
        mutable_fields=("qualifiers",),
        existing={"relation_id": "relation-1", "qualifiers": {"phase": "first"}},
        casts={"qualifiers": "jsonb"},
    )

    vector_cursor = _Cursor()
    changing_vector = _ChangingVector()
    _upsert(
        vector_cursor,
        table="vector_chunks",
        row=_scoped_vector_row(changing_vector),
        key_fields=("chunk_id",),
        mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
        existing=_scoped_vector_row(_vector_text(_vector_components(1.0))),
        casts=_VECTOR_CHUNKS_CASTS,
    )

    assert _dml_calls(json_cursor) == []
    assert _dml_calls(vector_cursor) == []
    assert changing_vector.calls == 1


@pytest.mark.parametrize(
    "value",
    (float("nan"), float("inf"), Decimal("NaN"), Decimal("Infinity")),
)
def test_uncast_nonfinite_scalars_fail_before_cursor_activity(value: object) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError, match="finite"):
        _upsert(
            cursor,
            table="relations",
            row=_relation_row(confidence=value),
            key_fields=("relation_id",),
            mutable_fields=("confidence",),
            existing=None,
        )

    assert cursor.calls == []


def test_jsonb_null_characters_fail_recursively_before_cursor_activity() -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError, match="NUL"):
        _upsert(
            cursor,
            table="relations",
            row={
                "relation_id": "relation-1",
                "qualifiers": {"nested": ["safe", {"bad\x00key": "value"}]},
            },
            key_fields=("relation_id",),
            mutable_fields=("qualifiers",),
            existing=None,
            casts={"qualifiers": "jsonb"},
        )

    assert cursor.calls == []


def test_vector_adapter_failures_normalize_to_the_public_validation_error() -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError, match=r"^vector chunk embedding is invalid$"):
        _upsert(
            cursor,
            table="vector_chunks",
            row=_scoped_vector_row(_BrokenVector()),
            key_fields=("chunk_id",),
            mutable_fields=_VECTOR_CHUNKS_FULL_MUTABLE_FIELDS,
            existing=None,
            casts=_VECTOR_CHUNKS_CASTS,
        )

    assert cursor.calls == []


def test_dml_boundary_exports_no_arbitrary_raw_statement_executor() -> None:
    assert not hasattr(dml, "execute_dml")


def test_upsert_rejects_caller_defined_table_projections_before_cursor_activity() -> (
    None
):
    cursor = _Cursor()

    with pytest.raises(ValueError, match="upsert projection"):
        _upsert(
            cursor,
            table="relations",
            row={"relation_id": "relation-1", "unapproved": "value"},
            key_fields=("relation_id",),
            mutable_fields=("unapproved",),
            existing=None,
        )

    assert cursor.calls == []


def test_upsert_rejects_embedding_only_vector_chunks_projection_without_version_scope() -> (
    None
):
    # RED: vector_chunks with embedding-only projection cannot enforce version
    # scope; the global-key projection (chunk_id only, no version_id) must be
    # rejected before cursor activity.
    cursor = _Cursor()

    with pytest.raises(ValueError, match="projection|scope|global"):
        _upsert(
            cursor,
            table="vector_chunks",
            row=_vector_row(_vector_components()),
            key_fields=("chunk_id",),
            mutable_fields=("embedding",),
            existing=None,
            casts={"embedding": "vector"},
        )

    assert _dml_calls(cursor) == []
