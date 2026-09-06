from __future__ import annotations

from collections import UserDict
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from llamaindex_runtime.registry.contracts import Relation
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter


class _Cursor:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.executions: list[tuple[str, tuple | None]] = []
        self._rows = rows or []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executions.append((sql, params))

    def fetchall(self) -> list[dict]:
        return deepcopy(self._rows)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self, **_kwargs: object) -> _Cursor:
        return self._cursor

    def transaction(self) -> _Cursor:
        return self._cursor


class _HostileDict(dict[str, object]):
    """A dict subtype whose traversal and copying must never be reached."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.deepcopy_calls = 0
        self.iteration_calls = 0

    def __deepcopy__(self, memo: dict[int, object]) -> _HostileDict:
        self.deepcopy_calls += 1
        raise AssertionError("dict-subclass-canary")

    def items(self):  # type: ignore[no-untyped-def]
        self.iteration_calls += 1
        raise AssertionError("dict-subclass-canary")


class _HostileList(list[object]):
    """A list subtype whose traversal and copying must never be reached."""

    def __init__(self, values: list[object]) -> None:
        super().__init__(values)
        self.deepcopy_calls = 0
        self.iteration_calls = 0

    def __deepcopy__(self, memo: dict[int, object]) -> _HostileList:
        self.deepcopy_calls += 1
        raise AssertionError("list-subclass-canary")

    def __iter__(self):  # type: ignore[no-untyped-def]
        self.iteration_calls += 1
        raise AssertionError("list-subclass-canary")


def _writer(cursor: _Cursor) -> PostgresRegistryWriter:
    writer = object.__new__(PostgresRegistryWriter)
    writer._connection = _Connection(cursor)
    writer._validate_relations_against_schemas = lambda _relations: None
    return writer


def _relation(**overrides: object) -> dict:
    return {
        "relation_id": uuid4(),
        "relation_key": "rain-causes-flood",
        "relation_type": "causes",
        "source_entity_id": uuid4(),
        "target_entity_id": uuid4(),
        **overrides,
    }


def test_write_relations_persists_all_qualifiers_as_jsonb_and_upserts() -> None:
    cursor = _Cursor()
    relation = _relation(
        negation=True,
        condition="during storms",
        direction="forward",
        confidence=0.75,
        qualifiers={
            "valid_time": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-12-31T00:00:00Z",
            },
            "source": "model-v2",
        },
    )

    _writer(cursor).write_relations(relations=[relation])

    sql, params = cursor.executions[0]
    assert "negation, condition, direction, confidence, qualifiers" in sql
    assert "ON CONFLICT (relation_id) DO UPDATE SET" in sql
    assert "DO NOTHING" not in sql
    assert params is not None
    assert params[6:10] == (True, "during storms", "forward", 0.75)
    assert isinstance(params[10], Jsonb)
    assert params[10].obj == relation["qualifiers"]


def test_write_relations_normalizes_legacy_relation_to_false_and_empty_qualifiers() -> (
    None
):
    cursor = _Cursor()

    _writer(cursor).write_relations(relations=[_relation(description="legacy")])

    _sql, params = cursor.executions[0]
    assert params is not None
    assert params[5] == "legacy"
    assert params[6:10] == (False, None, None, None)
    assert isinstance(params[10], Jsonb)
    assert params[10].obj == {}


def test_write_relations_returns_without_executing_for_an_empty_batch() -> None:
    cursor = _Cursor()

    _writer(cursor).write_relations(relations=[])

    assert cursor.executions == []


def test_write_relations_normalizes_explicit_none_qualifiers_to_empty_jsonb() -> None:
    cursor = _Cursor()

    _writer(cursor).write_relations(relations=[_relation(qualifiers=None)])

    _sql, params = cursor.executions[0]
    assert params is not None
    assert isinstance(params[10], Jsonb)
    assert params[10].obj == {}


def test_write_relations_rejects_invalid_second_batch_item_before_execute() -> None:
    cursor = _Cursor()
    canary = "mapping-subclass-must-not-reach-the-database"

    with pytest.raises(ValueError) as exc_info:
        _writer(cursor).write_relations(
            relations=[
                _relation(qualifiers={"extension": ["plain", "dict", "✓"]}),
                _relation(qualifiers={"extension": UserDict({"canary": canary})}),
            ]
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert canary not in str(exc_info.value)
    assert cursor.executions == []


def test_write_relations_rejects_builtin_container_subclasses_before_side_effects() -> (
    None
):
    root_dict = _HostileDict({"canary": "root-dict-subclass-canary"})
    nested_dict = _HostileDict({"canary": "nested-dict-subclass-canary"})
    nested_list = _HostileList(["nested-list-subclass-canary"])
    cases: tuple[tuple[object, _HostileDict | _HostileList, str], ...] = (
        (root_dict, root_dict, "root-dict-subclass-canary"),
        ({"extension": nested_dict}, nested_dict, "nested-dict-subclass-canary"),
        ({"extension": nested_list}, nested_list, "nested-list-subclass-canary"),
    )

    for invalid_qualifiers, hostile_container, canary in cases:
        cursor = _Cursor()

        with pytest.raises(ValueError) as exc_info:
            _writer(cursor).write_relations(
                relations=[
                    _relation(qualifiers={"extension": ["plain", "JSON", "✓"]}),
                    _relation(qualifiers=invalid_qualifiers),
                ]
            )

        assert (
            str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
        )
        assert canary not in str(exc_info.value)
        assert cursor.executions == []
        assert hostile_container.deepcopy_calls == 0
        assert hostile_container.iteration_calls == 0


@pytest.mark.parametrize(
    "qualifiers, canary",
    [
        (UserDict({"canary": "root-mapping-subclass"}), "root-mapping-subclass"),
        (
            {"extension": UserDict({"canary": "nested-mapping-subclass"})},
            "nested-mapping-subclass",
        ),
    ],
)
def test_write_relations_rejects_mapping_subclass_qualifiers_before_execute(
    qualifiers: object, canary: str
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError) as exc_info:
        _writer(cursor).write_relations(relations=[_relation(qualifiers=qualifiers)])

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert canary not in str(exc_info.value)
    assert cursor.executions == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("negation", "false"),
        ("condition", ""),
        ("direction", 1),
        ("confidence", True),
        ("confidence", float("nan")),
        ("confidence", float("inf")),
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("qualifiers", []),
        ("qualifiers", {"valid_time": {}}),
        ("qualifiers", {"valid_time": {"start": "not-a-date"}}),
        (
            "qualifiers",
            {
                "valid_time": {
                    "start": "2026-12-31T00:00:00Z",
                    "end": "2026-01-01T00:00:00Z",
                }
            },
        ),
    ],
)
def test_write_relations_rejects_invalid_qualifiers_before_execute(
    field: str, value: object
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError):
        _writer(cursor).write_relations(relations=[_relation(**{field: value})])

    assert cursor.executions == []


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
def test_write_relations_rejects_non_json_qualifier_extensions_before_execute(
    invalid_extension: object,
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError) as exc_info:
        _writer(cursor).write_relations(
            relations=[_relation(qualifiers={"extension": invalid_extension})]
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert cursor.executions == []


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
def test_write_relations_rejects_surrogate_qualifiers_before_execute(
    qualifiers: dict[str, object], canary: str
) -> None:
    cursor = _Cursor()

    with pytest.raises(ValueError) as exc_info:
        _writer(cursor).write_relations(relations=[_relation(qualifiers=qualifiers)])

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert canary not in str(exc_info.value)
    assert cursor.executions == []


def test_write_relations_preserves_valid_unicode_qualifiers() -> None:
    cursor = _Cursor()
    qualifiers = {"语言😀": {"message": "中文、emoji 😀、café"}}

    _writer(cursor).write_relations(relations=[_relation(qualifiers=qualifiers)])

    assert cursor.executions[0][1] is not None
    assert cursor.executions[0][1][10].obj == qualifiers


def test_write_relations_rejects_cyclic_qualifier_extensions_before_execute() -> None:
    cursor = _Cursor()
    cycle: dict[str, object] = {}
    cycle["self"] = cycle

    with pytest.raises(ValueError) as exc_info:
        _writer(cursor).write_relations(
            relations=[_relation(qualifiers={"extension": cycle})]
        )

    assert str(exc_info.value) == "qualifiers must contain only JSON-compatible values"
    assert cursor.executions == []


def test_write_relations_allows_none_qualifiers_and_preserves_unknown_qualifier_keys() -> (
    None
):
    cursor = _Cursor()
    relation = _relation(
        negation=None,
        qualifiers={
            "valid_time": {"expression": "Q1 2026"},
            "extension": {
                "unicode": "雪",
                "nested": {"values": [None, True, False, 0, 1.25, "✓"]},
            },
        },
    )

    _writer(cursor).write_relations(relations=[relation])

    _sql, params = cursor.executions[0]
    assert params is not None
    assert params[6] is False
    assert isinstance(params[10], Jsonb)
    assert params[10].obj == relation["qualifiers"]


def test_query_relations_returns_float_confidence_and_independent_qualifier_snapshot() -> (
    None
):
    relation_id, source_id, target_id = uuid4(), uuid4(), uuid4()
    qualifiers = {"valid_time": {"expression": "2026"}, "extension": ["α"]}
    cursor = _Cursor(
        [
            {
                "relation_id": relation_id,
                "relation_key": "rain-causes-flood",
                "relation_type": "causes",
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "description": "weather relation",
                "negation": None,
                "condition": "during storms",
                "direction": "forward",
                "confidence": Decimal("0.75"),
                "qualifiers": qualifiers,
                "created_at": "now",
            }
        ]
    )

    result = _writer(cursor).query_relations()

    assert result[0]["relation_id"] == relation_id
    assert result[0]["negation"] is False
    assert result[0]["confidence"] == 0.75
    assert result[0]["qualifiers"] == qualifiers
    assert result[0]["qualifiers"] is not qualifiers
    assert result[0]["qualifiers"]["valid_time"] is not qualifiers["valid_time"]


def test_relation_dto_additive_qualifier_defaults_preserve_legacy_construction() -> (
    None
):
    relation = Relation(
        relation_id=uuid4(),
        relation_key="legacy",
        relation_type="related_to",
        source_entity_id=uuid4(),
        target_entity_id=uuid4(),
    )

    assert relation.negation is False
    assert relation.condition is None
    assert relation.direction is None
    assert relation.confidence is None
    assert relation.qualifiers is None
