"""Psycopg row normalization for E2a reconciliation cursors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from psycopg import Cursor
from psycopg.rows import RowMaker, dict_row


def e2a_dict_row(cursor: Cursor[Any]) -> RowMaker[dict[str, object]]:
    make_dict_row = dict_row(cursor)

    def make_e2a_dict_row(values: Sequence[Any]) -> dict[str, object]:
        return {
            key: _normalize_value(value) for key, value in make_dict_row(values).items()
        }

    return make_e2a_dict_row


def _normalize_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    return value
