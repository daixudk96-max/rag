"""Deterministic span identity checks shared by OKF tools and regression tests."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from .diagnostics import (
    diagnostic_safe_path,
    diagnostic_safe_text,
    diagnostic_safe_uuid,
)
from .sidecar import SpanRecord, _span_record_values

SPAN_FIELDS: tuple[str, ...] = ("page_no", "heading_path", "offset", "text", "span_id")
_INVALID = "invalid-type=non-string"


def recompute_span_id(span: SpanRecord, *, doc_id: str, version_id: str) -> str:
    """Compute S_okf from validated provenance and sidecar coordinates."""
    if type(doc_id) is not str or type(version_id) is not str:
        raise ValueError("span identity inputs must be canonical strings")
    _, page_no, heading_path, offset, text = _span_record_values(span)
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{doc_id}|{version_id}|{page_no}|"
            f"{'/'.join(heading_path)}|{offset}|{text}",
        )
    )


def _validated_span_records(spans: object) -> tuple[SpanRecord, ...]:
    if not _exact_sequence(spans):
        raise ValueError("span records must be an exact list or tuple")
    records = tuple(_sequence_iter(spans))
    for span in records:
        _span_record_values(span)
    return cast(tuple[SpanRecord, ...], records)


def validate_span_identity_admission(
    spans: Sequence[SpanRecord], *, doc_id: str, version_id: str
) -> None:
    """Reject duplicate or non-canonical span identities at sidecar admission."""
    records = _validated_span_records(spans)
    persisted_ids = [_span_record_values(span)[0] for span in records]
    recomputed_ids = [
        recompute_span_id(span, doc_id=doc_id, version_id=version_id)
        for span in records
    ]
    if len(set(persisted_ids)) != len(persisted_ids):
        raise ValueError("sidecar contains duplicate persisted span identity")
    if len(set(recomputed_ids)) != len(recomputed_ids):
        raise ValueError("sidecar contains duplicate recomputed span identity")
    if persisted_ids != recomputed_ids:
        raise ValueError("sidecar span identity does not match canonical coordinates")


def recompute_span_dicts(
    spans: Sequence[SpanRecord], *, doc_id: str, version_id: str
) -> list[dict[str, Any]]:
    """Return sidecar coordinates with S_okf recomputed rather than trusted."""
    records = _validated_span_records(spans)
    return [
        {
            "span_id": recompute_span_id(span, doc_id=doc_id, version_id=version_id),
            "page_no": values[1],
            "heading_path": list(values[2]),
            "offset": values[3],
            "text": values[4],
        }
        for span in records
        for values in (_span_record_values(span),)
    ]


def persisted_span_id_mismatch(
    persisted: Sequence[SpanRecord], recomputed: Sequence[dict[str, Any]]
) -> str | None:
    """Return the first stored-sidecar identity mismatch, if any."""
    if not _exact_sequence(persisted) or not _exact_sequence(recomputed):
        return "SIDECAR SPAN ID MISMATCH: invalid-type=non-canonical"
    invalid = _persisted_invalid_index(persisted, recomputed)
    if invalid is not None:
        return f"SIDECAR SPAN ID MISMATCH at span[{invalid}]: {_INVALID}"
    return _persisted_mismatch(persisted, recomputed)


def _persisted_invalid_index(persisted: object, recomputed: object) -> int | None:
    limit = min(_sequence_len(persisted), _sequence_len(recomputed))
    for index in range(limit):
        stored = _sequence_item(persisted, index)
        rebuilt = _sequence_item(recomputed, index)
        if type(stored) is not SpanRecord or not _recomputed_span_is_valid(rebuilt):
            return index
        try:
            _span_record_values(stored)
        except ValueError:
            try:
                for field in ("page_no", "heading_path", "offset", "text"):
                    object.__getattribute__(stored, field)
            except AttributeError:
                continue
            return index
    return None


def _persisted_mismatch(persisted: object, recomputed: object) -> str | None:
    persisted_count, recomputed_count = _sequence_len(persisted), _sequence_len(
        recomputed
    )
    for index in range(min(persisted_count, recomputed_count)):
        stored_id = object.__getattribute__(_sequence_item(persisted, index), "span_id")
        rebuilt_id = dict.__getitem__(
            cast(dict[str, Any], _sequence_item(recomputed, index)), "span_id"
        )
        if stored_id != rebuilt_id:
            return (
                f"SIDECAR SPAN ID MISMATCH at span[{index}]: "
                f"persisted={diagnostic_safe_uuid(stored_id)} "
                f"recomputed={diagnostic_safe_uuid(rebuilt_id)}"
            )
    if persisted_count != recomputed_count:
        return f"SIDECAR SPAN ID MISMATCH: persisted_count={persisted_count} recomputed_count={recomputed_count}"
    return None


def _recomputed_span_is_valid(value: object) -> bool:
    return type(value) is dict and type(dict.get(value, "span_id")) is str


def _text_summary(value: Any) -> str:
    return diagnostic_safe_text(value)


def _heading_path_summary(value: Any) -> str:
    if not _heading_path_is_valid(value):
        return _INVALID
    encoded = [
        str.encode(segment, "utf-8", "surrogatepass")
        for segment in _sequence_iter(value)
    ]
    canonical = b"".join(
        len(segment).to_bytes(8, "big") + segment for segment in encoded
    )
    return (
        f"len={sum(map(len, encoded))} sha256={hashlib.sha256(canonical).hexdigest()}"
    )


def _mismatch_value(field: str, value: Any) -> Any:
    if field == "text":
        return _text_summary(value)
    if field == "heading_path":
        return _heading_path_summary(value)
    if field == "span_id":
        return diagnostic_safe_uuid(value)
    if field == "page_no" and (value is None or type(value) is int):
        return value
    if field == "offset" and type(value) is int:
        return value
    return _INVALID


def first_roundtrip_mismatch(
    direct: Sequence[dict[str, Any]],
    okf: Sequence[dict[str, Any]],
    *,
    doc_id: str,
    file_path: str,
) -> str | None:
    """Return the deterministic first S_direct versus S_okf mismatch."""
    context = _diagnostic_context(doc_id, file_path)
    invalid = _roundtrip_invalid_index(direct, okf)
    if invalid is not None:
        return f"ROUNDTRIP MISMATCH at span[{invalid}]: field=span direct={_INVALID} okf={_INVALID} {context}"
    return _roundtrip_valid_mismatch(direct, okf, context)


def _roundtrip_invalid_index(direct: object, okf: object) -> int | None:
    if not _exact_sequence(direct) or not _exact_sequence(okf):
        return 0
    for index, span in enumerate(_sequence_iter(direct)):
        if not _span_is_valid(span):
            return index
    for index, span in enumerate(_sequence_iter(okf)):
        if not _span_is_valid(span):
            return index
    return None


def _roundtrip_valid_mismatch(direct: object, okf: object, context: str) -> str | None:
    direct_count, okf_count = _sequence_len(direct), _sequence_len(okf)
    for index in range(min(direct_count, okf_count)):
        mismatch = _span_mismatch(
            cast(dict[str, Any], _sequence_item(direct, index)),
            cast(dict[str, Any], _sequence_item(okf, index)),
        )
        if mismatch is not None:
            field, left, right = mismatch
            return f"ROUNDTRIP MISMATCH at span[{index}]: field={field} direct={left} okf={right} {context}"
    if direct_count != okf_count:
        index = min(direct_count, okf_count)
        return f"ROUNDTRIP MISMATCH at span[{index}]: field=span_count direct={direct_count} okf={okf_count} {context}"
    return None


def _span_mismatch(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[str, Any, Any] | None:
    for field in SPAN_FIELDS:
        left_value, right_value = dict.__getitem__(left, field), dict.__getitem__(
            right, field
        )
        if not _canonical_equal(left_value, right_value):
            return (
                field,
                _mismatch_value(field, left_value),
                _mismatch_value(field, right_value),
            )
    return None


def _span_is_valid(value: object) -> bool:
    if type(value) is not dict:
        return False
    if any(not dict.__contains__(value, field) for field in SPAN_FIELDS):
        return False
    page_no, offset = dict.__getitem__(value, "page_no"), dict.__getitem__(
        value, "offset"
    )
    return (
        (page_no is None or type(page_no) is int)
        and type(offset) is int
        and type(dict.__getitem__(value, "text")) is str
        and type(dict.__getitem__(value, "span_id")) is str
        and _heading_path_is_valid(dict.__getitem__(value, "heading_path"))
    )


def _heading_path_is_valid(value: object) -> bool:
    return _exact_sequence(value) and all(
        type(segment) is str for segment in _sequence_iter(value)
    )


def _canonical_equal(left: object, right: object) -> bool:
    if _exact_sequence(left) and _exact_sequence(right):
        return _sequence_equal(left, right)
    return left == right


def _sequence_equal(left: object, right: object) -> bool:
    if _sequence_len(left) != _sequence_len(right):
        return False
    return all(
        first == second
        for first, second in zip(_sequence_iter(left), _sequence_iter(right))
    )


def _exact_sequence(value: object) -> bool:
    return type(value) in (list, tuple)


def _sequence_len(value: object) -> int:
    if type(value) is list:
        return list.__len__(cast(list[Any], value))
    return tuple.__len__(cast(tuple[Any, ...], value))


def _sequence_item(value: object, index: int) -> object:
    if type(value) is list:
        return list.__getitem__(cast(list[Any], value), index)
    return tuple.__getitem__(cast(tuple[Any, ...], value), index)


def _sequence_iter(value: object) -> Iterator[Any]:
    if type(value) is list:
        return list.__iter__(cast(list[Any], value))
    return tuple.__iter__(cast(tuple[Any, ...], value))


def _diagnostic_context(doc_id: object, file_path: object) -> str:
    return (
        f"(doc={diagnostic_safe_uuid(doc_id)} file={diagnostic_safe_path(file_path)})"
    )


def roundtrip_mismatch(
    *,
    direct: Sequence[dict[str, Any]],
    spans: Sequence[SpanRecord],
    doc_id: str,
    version_id: str,
    file_path: str,
) -> str | None:
    """Verify sidecar integrity and compare frozen direct identities to S_okf."""
    recomputed = recompute_span_dicts(spans, doc_id=doc_id, version_id=version_id)
    direct_mismatch = first_roundtrip_mismatch(
        direct, recomputed, doc_id=doc_id, file_path=file_path
    )
    return direct_mismatch or persisted_span_id_mismatch(spans, recomputed)
