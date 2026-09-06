"""Exclusive E2a ownership operations for shared ``okf_sync_state`` rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from .e2a_contracts import DmlRecorder
from .e2a_materialization_dml import DmlTemplate, execute_template


class Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...

    def fetchone(self) -> Mapping[str, object] | None: ...


_SYNC_FIELDS = (
    "okf_file_path",
    "doc_id",
    "version_id",
    "source_checksum",
    "canonical_hash",
    "status",
    "materialization_owner",
)


def ensure_sync_path_ownership(cursor: Cursor, desired: object) -> None:
    """Reject visible same-path rows that are owned by another materializer."""
    paths = tuple(
        sorted(
            {
                _string(_mapping(value).get("okf_file_path"))
                for value in _sync_rows(desired)
            }
        )
    )
    if not paths:
        return
    cursor.execute(
        "SELECT okf_file_path, materialization_owner FROM okf_sync_state "
        "WHERE okf_file_path = ANY(%s)",
        (list(paths),),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("sync ownership query returned an invalid result set")
    for value in rows:
        if not isinstance(value, Mapping) or frozenset(value) != {
            "okf_file_path",
            "materialization_owner",
        }:
            raise ValueError("sync ownership query returned a malformed row")
        if (
            _string(value["okf_file_path"]) in paths
            and value["materialization_owner"] != "e2a"
        ):
            raise ValueError("sync ownership collision with a non-E2a row")


def upsert_sync_state(
    cursor: Cursor,
    desired: object,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    """Upsert only E2a-owned rows and fail closed on a raced legacy conflict."""
    old = {_string(row.get("okf_file_path")): row for row in existing["okf_sync_state"]}
    for value in _sync_rows(desired):
        row = _fields(_mapping(value), *_SYNC_FIELDS)
        current = old.get(_string(row["okf_file_path"]))
        if current is not None and _same_row(current, row):
            continue
        _upsert_owned_row(cursor, row, recorder)


def delete_stale_sync_state(
    cursor: Cursor,
    desired: object,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    desired_paths = {
        _string(_mapping(value).get("okf_file_path")) for value in _sync_rows(desired)
    }
    stale_paths = [
        _string(row.get("okf_file_path"))
        for row in existing["okf_sync_state"]
        if _string(row.get("okf_file_path")) not in desired_paths
    ]
    if not stale_paths:
        return
    execute_template(
        cursor,
        DmlTemplate.DELETE_SYNC_STATE_BY_PATHS,
        (stale_paths, "e2a"),
        recorder,
    )
    stale_counts["okf_sync_state"] = len(stale_paths)


def _upsert_owned_row(
    cursor: Cursor, row: Mapping[str, object], recorder: DmlRecorder
) -> None:
    execute_template(
        cursor,
        DmlTemplate.UPSERT_SYNC_STATE,
        (*tuple(row[column] for column in _SYNC_FIELDS), "e2a"),
        recorder,
    )
    fetchone = getattr(cursor, "fetchone", None)
    if not callable(fetchone) or fetchone() is None:
        raise ValueError("sync ownership conflict prevented materialization")


def _sync_rows(desired: object) -> Sequence[object]:
    try:
        rows = getattr(desired, "sync_state_rows")
    except AttributeError:
        raise ValueError("desired sync projection is invalid") from None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("desired sync projection is invalid")
    return rows


def _fields(row: Mapping[str, object], *names: str) -> Mapping[str, object]:
    if any(name not in row for name in names):
        raise ValueError("desired sync projection is missing required fields")
    return {name: row[name] for name in names}


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("desired sync projection is invalid")
    return value


def _same_row(current: Mapping[str, object], desired: Mapping[str, object]) -> bool:
    return all(current.get(field) == desired[field] for field in desired)


def _string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("sync projection identifier is invalid")
    return value


__all__ = [
    "delete_stale_sync_state",
    "ensure_sync_path_ownership",
    "upsert_sync_state",
]
