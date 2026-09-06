"""Read-only PostgreSQL catalog validators for migration-019 acceptance."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from llamaindex_runtime.okf.e2a_disposable_catalog_contracts import (
    _ConstraintExpectation,
    _EXPECTED_018_APPEND_ONLY_FUNCTION,
    _EXPECTED_018_TRIGGER_ROWS,
    _EXPECTED_019_COLUMNS,
    _EXPECTED_019_CONSTRAINT_ROWS,
    _EXPECTED_019_INDEX_DEFINITIONS,
    _EXPECTED_019_INDEX_ROWS,
    _FunctionExpectation,
    _IndexExpectation,
)
from llamaindex_runtime.okf.e2a_disposable_sql_lexer import (
    _check_body,
    _check_definitions_match,
    _definition,
    _expressions_match,
)


_FAILURE = "executed_failed"


def _catalog_string(value: object) -> str:
    """Return only a built-in PostgreSQL text value."""
    if type(value) is str:
        return value
    raise ValueError(_FAILURE)


def _optional_catalog_string(value: object) -> str | None:
    if value is None or type(value) is str:
        return value
    raise ValueError(_FAILURE)


def _catalog_integer(value: object) -> int:
    """Return only a real PostgreSQL integer field; reject coercible impostors."""
    if type(value) is int:
        return value
    raise ValueError(_FAILURE)


def _positive_catalog_integer(value: object) -> int:
    result = _catalog_integer(value)
    if result <= 0:
        raise ValueError(_FAILURE)
    return result


def _catalog_boolean(value: object) -> bool:
    if type(value) is bool:
        return value
    raise ValueError(_FAILURE)


def _catalog_bytes(value: object) -> bytes:
    if type(value) is bytes:
        return value
    raise ValueError(_FAILURE)


def _catalog_row(value: object, size: int) -> tuple[object, ...]:
    if type(value) is not tuple or len(value) != size:
        raise ValueError(_FAILURE)
    return value


def _catalog_index_row(value: object) -> tuple[object, ...]:
    if type(value) is not tuple or len(value) not in {10, 18}:
        raise ValueError(_FAILURE)
    return value


def _assert_019_catalog_shape(cursor: Any) -> None:
    relation_oids = _relation_oids(cursor, _expected_relations())
    _assert_constraint_rows(cursor, relation_oids)
    _assert_backing_index_rows(cursor, relation_oids)
    _assert_index_rows(cursor, relation_oids)
    _assert_trigger_rows(cursor, relation_oids)
    _assert_column_rows(cursor)


def _expected_relations() -> tuple[str, ...]:
    values = {item.table for item in _EXPECTED_019_CONSTRAINT_ROWS}
    values.update(
        item.reference_table
        for item in _EXPECTED_019_CONSTRAINT_ROWS
        if item.reference_table is not None
    )
    values.update(item.table for item in _EXPECTED_019_INDEX_ROWS)
    return tuple(sorted(values))


def _relation_oids(cursor: Any, expected: Iterable[str]) -> dict[str, int]:
    expected_names = tuple(expected)
    cursor.execute(
        """
        SELECT class_row.relname, class_row.oid
        FROM pg_class class_row
        JOIN pg_namespace namespace_row ON namespace_row.oid = class_row.relnamespace
        WHERE namespace_row.nspname = current_schema()
          AND class_row.relname = ANY (%s)
        ORDER BY 1
        """,
        (list(expected_names),),
    )
    result: dict[str, int] = {}
    for raw_row in tuple(cursor.fetchall()):
        name, oid = _catalog_row(raw_row, 2)
        result[_catalog_string(name)] = _positive_catalog_integer(oid)
    if tuple(sorted(result)) != expected_names:
        raise ValueError(_FAILURE)
    return result


def _assert_constraint_rows(
    cursor: Any,
    relation_oids: dict[str, int],
    expected_rows: tuple[_ConstraintExpectation, ...] = _EXPECTED_019_CONSTRAINT_ROWS,
) -> None:
    cursor.execute(
        """
        SELECT table_class.relname, constraint_row.conname, constraint_row.contype,
               CASE WHEN constraint_row.contype = 'c'
                    THEN pg_get_expr(constraint_row.conbin, constraint_row.conrelid, false)
                    ELSE pg_get_constraintdef(constraint_row.oid, true)
               END,
               COALESCE((
                   SELECT string_agg(attribute_row.attname, ',' ORDER BY key_row.ordinality)
                   FROM unnest(constraint_row.conkey) WITH ORDINALITY AS key_row(attnum, ordinality)
                   JOIN pg_attribute attribute_row ON attribute_row.attrelid = constraint_row.conrelid
                                                AND attribute_row.attnum = key_row.attnum
               ), ''),
               COALESCE((
                   SELECT string_agg(attribute_row.attname, ',' ORDER BY key_row.ordinality)
                   FROM unnest(constraint_row.confkey) WITH ORDINALITY AS key_row(attnum, ordinality)
                   JOIN pg_attribute attribute_row ON attribute_row.attrelid = constraint_row.confrelid
                                                AND attribute_row.attnum = key_row.attnum
               ), ''),
               constraint_row.conrelid, constraint_row.confrelid,
               constraint_row.convalidated, constraint_row.confdeltype,
               constraint_row.confmatchtype, constraint_row.confupdtype,
               constraint_row.condeferrable, constraint_row.condeferred,
               constraint_row.conindid
        FROM pg_constraint constraint_row
        JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_class.relnamespace
        WHERE schema_row.nspname = current_schema()
          AND (table_class.relname, constraint_row.conname) = ANY (%s)
        ORDER BY 1, 2
        """,
        (list(sorted((item.table, item.name) for item in expected_rows)),),
    )
    rows = tuple(cursor.fetchall())
    expected_names = tuple(sorted((item.table, item.name) for item in expected_rows))
    actual_names = tuple(
        (
            _catalog_string(_catalog_row(row, 15)[0]),
            _catalog_string(_catalog_row(row, 15)[1]),
        )
        for row in rows
    )
    if actual_names != expected_names:
        raise ValueError(_FAILURE)
    expected_by_name = {(item.table, item.name): item for item in expected_rows}
    for row in rows:
        actual = _catalog_row(row, 15)
        expected = expected_by_name[
            (_catalog_string(actual[0]), _catalog_string(actual[1]))
        ]
        _validate_constraint_row(actual, expected, relation_oids)


def _validate_constraint_row(
    row: tuple[object, ...],
    expected: _ConstraintExpectation,
    relation_oids: dict[str, int],
) -> None:
    actual = _catalog_row(row, 15)
    table, name, contype, definition, columns, reference_columns = (
        _catalog_string(actual[position]) for position in range(6)
    )
    table_oid = _catalog_integer(actual[6])
    reference_oid = _catalog_integer(actual[7])
    validated = _catalog_boolean(actual[8])
    delete_type = _catalog_string(actual[9])
    match_type = _catalog_string(actual[10])
    update_type = _catalog_string(actual[11])
    deferrable = _catalog_boolean(actual[12])
    deferred = _catalog_boolean(actual[13])
    backing_index_oid = _catalog_integer(actual[14])
    definitions_match = (
        (
            _check_definitions_match(definition, expected.definition)
            if definition.startswith("CHECK")
            else _expressions_match(definition, _check_body(expected.definition))
        )
        if expected.contype == "c"
        else _definition(definition) == _definition(expected.definition)
    )
    if (
        table != expected.table
        or name != expected.name
        or contype != expected.contype
        or not definitions_match
        or columns != expected.columns
        or table_oid != relation_oids[expected.table]
        or validated is not True
    ):
        raise ValueError(_FAILURE)
    if expected.contype == "f":
        if (
            expected.reference_table is None
            or reference_columns != expected.reference_columns
            or reference_oid != relation_oids[expected.reference_table]
            or delete_type != "r"
            or match_type != "s"
            or update_type != "a"
            or deferrable is not False
            or deferred is not False
            or backing_index_oid != 0
        ):
            raise ValueError(_FAILURE)
    elif expected.contype in {"p", "u"} and backing_index_oid == 0:
        raise ValueError(_FAILURE)


def _assert_index_rows(
    cursor: Any,
    relation_oids: dict[str, int],
    expected_rows: tuple[_IndexExpectation, ...] = _EXPECTED_019_INDEX_ROWS,
) -> None:
    cursor.execute(
        """
        SELECT table_class.relname, index_class.relname,
               index_row.indrelid, index_row.indexrelid,
               index_row.indisunique, index_row.indisprimary,
               index_row.indisvalid, index_row.indisready, index_row.indislive,
               index_row.indisexclusion, index_method.amname,
               index_row.indnkeyatts, index_row.indnatts,
               COALESCE((
                   SELECT string_agg(attribute_row.attname, ',' ORDER BY key_position.ordinality)
                   FROM generate_series(0, index_row.indnkeyatts - 1) WITH ORDINALITY
                        AS key_position(offset, ordinality)
                   JOIN pg_attribute attribute_row
                     ON attribute_row.attrelid = index_row.indrelid
                    AND attribute_row.attnum = index_row.indkey[key_position.offset]
               ), ''),
               COALESCE(pg_get_expr(index_row.indexprs, index_row.indrelid, false), ''),
               COALESCE(pg_get_expr(index_row.indpred, index_row.indrelid, false), ''),
               COALESCE((
                   SELECT bool_and(
                       opclass_row.opcdefault
                       AND opclass_row.opcmethod = index_class.relam
                       AND index_row.indcollation[key_position.offset]
                           = attribute_row.attcollation
                       AND index_row.indoption[key_position.offset] >= 0
                   )
                   FROM generate_series(0, index_row.indnkeyatts - 1) WITH ORDINALITY
                        AS key_position(offset, ordinality)
                   JOIN pg_attribute attribute_row
                     ON attribute_row.attrelid = index_row.indrelid
                    AND attribute_row.attnum = index_row.indkey[key_position.offset]
                   JOIN pg_opclass opclass_row
                     ON opclass_row.oid = index_row.indclass[key_position.offset]
                   WHERE key_position.offset = key_position.ordinality - 1
               ), true),
               array_to_string(index_row.indoption, ',')
        FROM pg_index index_row
        JOIN pg_class index_class ON index_class.oid = index_row.indexrelid
        JOIN pg_am index_method ON index_method.oid = index_class.relam
        JOIN pg_class table_class ON table_class.oid = index_row.indrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_class.relnamespace
        WHERE schema_row.nspname = current_schema()
          AND (table_class.relname, index_class.relname) = ANY (%s)
        ORDER BY 1, 2
        """,
        (list(sorted((item.table, item.name) for item in expected_rows)),),
    )
    rows = tuple(cursor.fetchall())
    expected_names = tuple(sorted((item.table, item.name) for item in expected_rows))
    actual_names = tuple(
        (
            _catalog_string(_catalog_index_row(row)[0]),
            _catalog_string(_catalog_index_row(row)[1]),
        )
        for row in rows
    )
    if actual_names != expected_names:
        raise ValueError(_FAILURE)
    expected_by_name = {(item.table, item.name): item for item in expected_rows}
    for row in rows:
        actual = _catalog_index_row(row)
        expected = expected_by_name[
            (_catalog_string(actual[0]), _catalog_string(actual[1]))
        ]
        _validate_index_row(actual, expected, relation_oids)


def _validate_index_row(
    row: tuple[object, ...],
    expected: _IndexExpectation,
    relation_oids: dict[str, int],
) -> None:
    """Validate structural pg_index data; legacy fake rows stay test-only adapters."""
    if type(row) is not tuple or len(row) not in {10, 18}:
        raise ValueError(_FAILURE)
    if len(row) == 10:
        table, name = _catalog_string(row[0]), _catalog_string(row[1])
        relation_oid, index_oid = _catalog_integer(row[2]), _catalog_integer(row[3])
        unique, valid = _catalog_boolean(row[4]), _catalog_boolean(row[5])
        keys, expressions, predicate, definition = (
            _catalog_string(row[position]) for position in range(6, 10)
        )
        expected_definition = (
            expected.definition
            or _EXPECTED_019_INDEX_DEFINITIONS[(expected.table, expected.name)]
        )
        if (
            table != expected.table
            or name != expected.name
            or relation_oid != relation_oids[expected.table]
            or index_oid <= 0
            or unique is not expected.unique
            or valid is not True
            or keys != expected.keys
            or expressions != ""
            or not _expressions_match(predicate, expected.predicate)
            or _definition(definition) != _definition(expected_definition)
        ):
            raise ValueError(_FAILURE)
        return

    expected_key_count = len(expected.keys.split(","))
    expected_options = expected.options or ",".join(
        "0" for _ in range(expected_key_count)
    )
    table, name = _catalog_string(row[0]), _catalog_string(row[1])
    relation_oid, index_oid = _catalog_integer(row[2]), _catalog_integer(row[3])
    unique, primary, valid, ready, live, exclusion = (
        _catalog_boolean(row[position]) for position in range(4, 10)
    )
    method = _catalog_string(row[10])
    key_count, attribute_count = _catalog_integer(row[11]), _catalog_integer(row[12])
    keys, expressions, predicate = (
        _catalog_string(row[position]) for position in range(13, 16)
    )
    default_opclass_and_collation = _catalog_boolean(row[16])
    options = _catalog_string(row[17])
    if (
        table != expected.table
        or name != expected.name
        or relation_oid != relation_oids[expected.table]
        or index_oid <= 0
        or unique is not expected.unique
        or primary is not expected.primary
        or valid is not True
        or ready is not True
        or live is not True
        or exclusion is not False
        or method != "btree"
        or key_count != expected_key_count
        or attribute_count != expected_key_count
        or keys != expected.keys
        or expressions != ""
        or not _expressions_match(predicate, expected.predicate)
        or default_opclass_and_collation is not True
        or options != expected_options
    ):
        raise ValueError(_FAILURE)


def _assert_backing_index_rows(cursor: Any, relation_oids: dict[str, int]) -> None:
    """Verify every managed PRIMARY KEY/UNIQUE constraint has a live btree index."""
    expected_rows = tuple(
        item for item in _EXPECTED_019_CONSTRAINT_ROWS if item.contype in {"p", "u"}
    )
    cursor.execute(
        """
        SELECT table_class.relname, constraint_row.conname, constraint_row.contype,
               constraint_row.conindid, index_row.indrelid, index_row.indisunique,
               index_row.indisprimary, index_row.indisvalid, index_row.indisready,
               index_row.indislive, index_row.indisexclusion, index_method.amname,
               index_row.indnkeyatts, index_row.indnatts,
               COALESCE((
                   SELECT string_agg(attribute_row.attname, ',' ORDER BY key_position.ordinality)
                   FROM generate_series(0, index_row.indnkeyatts - 1) WITH ORDINALITY
                        AS key_position(offset, ordinality)
                   JOIN pg_attribute attribute_row
                     ON attribute_row.attrelid = index_row.indrelid
                    AND attribute_row.attnum = index_row.indkey[key_position.offset]
               ), ''),
               COALESCE(pg_get_expr(index_row.indexprs, index_row.indrelid, false), ''),
               COALESCE(pg_get_expr(index_row.indpred, index_row.indrelid, false), ''),
               COALESCE((
                   SELECT bool_and(
                       opclass_row.opcdefault
                       AND opclass_row.opcmethod = index_class.relam
                       AND index_row.indcollation[key_position.offset]
                           = attribute_row.attcollation
                   )
                   FROM generate_series(0, index_row.indnkeyatts - 1) WITH ORDINALITY
                        AS key_position(offset, ordinality)
                   JOIN pg_attribute attribute_row
                     ON attribute_row.attrelid = index_row.indrelid
                    AND attribute_row.attnum = index_row.indkey[key_position.offset]
                   JOIN pg_opclass opclass_row
                     ON opclass_row.oid = index_row.indclass[key_position.offset]
                   WHERE key_position.offset = key_position.ordinality - 1
               ), true),
               array_to_string(index_row.indoption, ',')
        FROM pg_constraint constraint_row
        JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_class.relnamespace
        JOIN pg_index index_row ON index_row.indexrelid = constraint_row.conindid
        JOIN pg_class index_class ON index_class.oid = index_row.indexrelid
        JOIN pg_am index_method ON index_method.oid = index_class.relam
        WHERE schema_row.nspname = current_schema()
          AND (table_class.relname, constraint_row.conname) = ANY (%s)
        ORDER BY 1, 2
        """,
        (list(sorted((item.table, item.name) for item in expected_rows)),),
    )
    rows = tuple(cursor.fetchall())
    expected_names = tuple(sorted((item.table, item.name) for item in expected_rows))
    actual_names = tuple(
        (
            _catalog_string(_catalog_row(row, 19)[0]),
            _catalog_string(_catalog_row(row, 19)[1]),
        )
        for row in rows
    )
    if actual_names != expected_names:
        raise ValueError(_FAILURE)
    expected_by_name = {(item.table, item.name): item for item in expected_rows}
    for raw_row in rows:
        row = _catalog_row(raw_row, 19)
        expected = expected_by_name[(_catalog_string(row[0]), _catalog_string(row[1]))]
        key_count = len(expected.columns.split(","))
        expected_options = ",".join("0" for _ in range(key_count))
        table, name, contype = (_catalog_string(row[position]) for position in range(3))
        constraint_index_oid = _catalog_integer(row[3])
        relation_oid = _catalog_integer(row[4])
        unique, primary, valid, ready, live, exclusion = (
            _catalog_boolean(row[position]) for position in range(5, 11)
        )
        method = _catalog_string(row[11])
        key_attributes, attributes = (
            _catalog_integer(row[12]),
            _catalog_integer(row[13]),
        )
        keys, expressions, predicate = (
            _catalog_string(row[position]) for position in range(14, 17)
        )
        default_opclass_and_collation = _catalog_boolean(row[17])
        options = _catalog_string(row[18])
        if (
            table != expected.table
            or name != expected.name
            or contype != expected.contype
            or constraint_index_oid <= 0
            or relation_oid != relation_oids[expected.table]
            or unique is not True
            or primary is not (expected.contype == "p")
            or valid is not True
            or ready is not True
            or live is not True
            or exclusion is not False
            or method != "btree"
            or key_attributes != key_count
            or attributes != key_count
            or keys != expected.columns
            or expressions != ""
            or predicate != ""
            or default_opclass_and_collation is not True
            or options != expected_options
        ):
            raise ValueError(_FAILURE)


def _assert_append_only_function(cursor: Any) -> int:
    """Attest the exact same-schema 018 append-only trigger function once."""
    expected = _EXPECTED_018_APPEND_ONLY_FUNCTION
    cursor.execute(
        """
        SELECT procedure_row.oid, procedure_row.proname, procedure_row.prokind,
               procedure_row.pronargs, procedure_row.proargtypes::text,
               procedure_row.provariadic, procedure_row.prorettype::regtype::text,
               procedure_row.proretset, language_row.lanname, procedure_row.prosrc
        FROM pg_proc procedure_row
        JOIN pg_namespace procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        JOIN pg_language language_row ON language_row.oid = procedure_row.prolang
        WHERE procedure_schema.nspname = current_schema()
          AND procedure_row.proname = %s
        ORDER BY procedure_row.oid
        """,
        (expected.name,),
    )
    rows = tuple(cursor.fetchall())
    if len(rows) != 1:
        raise ValueError(_FAILURE)
    return _validate_append_only_function_row(_catalog_row(rows[0], 10), expected)


def _validate_append_only_function_row(
    row: tuple[object, ...], expected: _FunctionExpectation
) -> int:
    oid = _positive_catalog_integer(row[0])
    name, prokind = _catalog_string(row[1]), _catalog_string(row[2])
    pronargs = _catalog_integer(row[3])
    proargtypes = _catalog_string(row[4])
    provariadic = _catalog_integer(row[5])
    prorettype = _catalog_string(row[6])
    proretset = _catalog_boolean(row[7])
    language = _catalog_string(row[8])
    source = _catalog_string(row[9])
    if (
        name != expected.name
        or prokind != expected.prokind
        or pronargs != expected.pronargs
        or proargtypes != expected.proargtypes
        or provariadic != expected.provariadic
        or prorettype != expected.prorettype
        or proretset is not expected.proretset
        or language != expected.language
        or _definition(source, _comparison=True)
        != _definition(expected.source, _comparison=True)
    ):
        raise ValueError(_FAILURE)
    return oid


def _assert_trigger_rows(cursor: Any, relation_oids: dict[str, int]) -> None:
    """Verify retained triggers use the one independently attested function OID."""
    function_oid = _assert_append_only_function(cursor)
    audit_oid = relation_oids["okf_rebuild_failure_audit"]
    cursor.execute(
        """
        SELECT table_class.relname, trigger_row.tgname, procedure_row.proname,
               trigger_row.tgrelid, trigger_row.tgtype, trigger_row.tgenabled,
               trigger_row.tgisinternal, trigger_row.tgargs, trigger_row.tgqual,
               trigger_row.tgattr, trigger_row.tgconstraint, trigger_row.tgfoid
        FROM pg_trigger trigger_row
        JOIN pg_class table_class ON table_class.oid = trigger_row.tgrelid
        JOIN pg_proc procedure_row ON procedure_row.oid = trigger_row.tgfoid
        WHERE trigger_row.tgrelid = %s
        ORDER BY 1, 2
        """,
        (audit_oid,),
    )
    rows = tuple(cursor.fetchall())
    expected_names = tuple(
        sorted((item.table, item.name) for item in _EXPECTED_018_TRIGGER_ROWS)
    )
    actual_names = tuple(
        (
            _catalog_string(_catalog_row(row, 12)[0]),
            _catalog_string(_catalog_row(row, 12)[1]),
        )
        for row in rows
    )
    if actual_names != expected_names:
        raise ValueError(_FAILURE)
    expected_by_name = {
        (item.table, item.name): item for item in _EXPECTED_018_TRIGGER_ROWS
    }
    for raw_row in rows:
        row = _catalog_row(raw_row, 12)
        table, name, function = (
            _catalog_string(row[position]) for position in range(3)
        )
        relation_oid, trigger_type = _catalog_integer(row[3]), _catalog_integer(row[4])
        enabled = _catalog_string(row[5])
        internal = _catalog_boolean(row[6])
        arguments = _catalog_bytes(row[7])
        condition = _optional_catalog_string(row[8])
        attributes = _catalog_string(row[9])
        constraint_oid, trigger_function_oid = (
            _catalog_integer(row[10]),
            _catalog_integer(row[11]),
        )
        expected = expected_by_name[(table, name)]
        if (
            function != expected.function
            or relation_oid != relation_oids[expected.table]
            or trigger_type != expected.trigger_type
            or enabled != "O"
            or internal is not False
            or arguments != b""
            or condition is not None
            or attributes != ""
            or constraint_oid != 0
            or trigger_function_oid != function_oid
        ):
            raise ValueError(_FAILURE)


def _assert_column_rows(
    cursor: Any,
    expected_columns: tuple[
        tuple[str, str, str, str, str | None], ...
    ] = _EXPECTED_019_COLUMNS,
) -> None:
    cursor.execute(
        """
        SELECT table_class.relname, attribute_row.attname,
               format_type(attribute_row.atttypid, attribute_row.atttypmod),
               CASE WHEN attribute_row.attnotnull THEN 'NO' ELSE 'YES' END,
               pg_get_expr(default_row.adbin, default_row.adrelid)
        FROM pg_attribute attribute_row
        JOIN pg_class table_class ON table_class.oid = attribute_row.attrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_class.relnamespace
        LEFT JOIN pg_attrdef default_row ON default_row.adrelid = attribute_row.attrelid
                                          AND default_row.adnum = attribute_row.attnum
        WHERE schema_row.nspname = current_schema()
          AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
          AND (table_class.relname, attribute_row.attname) = ANY (%s)
        ORDER BY 1, 2
        """,
        ([(table, column) for table, column, *_ in expected_columns],),
    )
    actual: list[tuple[str, str, str, str, str | None]] = []
    for raw_row in tuple(cursor.fetchall()):
        row = _catalog_row(raw_row, 5)
        default = _optional_catalog_string(row[4])
        if default is not None and default == "":
            raise ValueError(_FAILURE)
        actual.append(
            (
                _catalog_string(row[0]),
                _catalog_string(row[1]),
                _catalog_string(row[2]),
                _catalog_string(row[3]),
                default,
            )
        )
    if len(actual) != len(expected_columns):
        raise ValueError(_FAILURE)
    for actual_row, expected_row in zip(actual, expected_columns, strict=True):
        if actual_row[:4] != expected_row[:4]:
            raise ValueError(_FAILURE)
        actual_default, expected_default = actual_row[4], expected_row[4]
        if (actual_default is None) != (expected_default is None) or (
            actual_default is not None
            and expected_default is not None
            and not _expressions_match(actual_default, expected_default)
        ):
            raise ValueError(_FAILURE)
