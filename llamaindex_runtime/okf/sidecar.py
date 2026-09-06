"""Versioned JSON sidecars preserving normalized OKF span coordinates."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, cast
from uuid import UUID

SIDECAR_SCHEMA_VERSION = 1
MAX_SIDECAR_BYTES = 64 * 1024 * 1024
MAX_SIDECAR_JSON_DEPTH = 64
MAX_SIDECAR_SPAN_COUNT = 100_000
MAX_SPAN_TEXT_BYTES = 1024 * 1024
MAX_HEADING_SEGMENTS = 64
MAX_HEADING_SEGMENT_BYTES = 64 * 1024
MAX_SIDECAR_STRUCTURAL_TOKENS = 1_200_000
MAX_JSON_NUMBER_TOKEN_BYTES = 64
MAX_JSON_KEY_TOKEN_BYTES = 384
MAX_HEADING_SEGMENTS_TOTAL = 100_000
# Source bytes conservatively bound all decoded JSON strings before materialization.
MAX_JSON_STRING_SOURCE_BYTES = MAX_SIDECAR_BYTES

_KEY_TOKEN_DECODER = json.JSONDecoder()
_VALUE_TOKEN_DECODER = json.JSONDecoder()

_ROOT_FIELDS = frozenset({"schema_version", "doc_id", "version_id", "spans"})
_SPAN_FIELDS = frozenset({"span_id", "page_no", "heading_path", "offset", "text"})


@dataclass(frozen=True)
class SpanRecord:
    """A normalized span whose identity is independent of Markdown layout."""

    span_id: str
    page_no: int | None
    heading_path: tuple[str, ...]
    offset: int
    text: str

    def __post_init__(self) -> None:
        _validate_span_record_values(
            object.__getattribute__(self, "span_id"),
            object.__getattribute__(self, "page_no"),
            object.__getattribute__(self, "heading_path"),
            object.__getattribute__(self, "offset"),
            object.__getattribute__(self, "text"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpanRecord:
        _validate_exact_dict_fields(value, _SPAN_FIELDS)
        payload = cast(dict[str, Any], value)
        _require_dict_fields(
            payload, ("heading_path", "span_id", "offset", "text", "page_no")
        )
        span_id: object = dict.__getitem__(payload, "span_id")
        page_no: object = dict.__getitem__(payload, "page_no")
        heading_path: object = dict.__getitem__(payload, "heading_path")
        offset: object = dict.__getitem__(payload, "offset")
        text: object = dict.__getitem__(payload, "text")
        if type(heading_path) is not list:
            raise ValueError("heading_path must be a list")
        headings = cast(list[str], heading_path)
        if any(type(heading) is not str for heading in list.__iter__(headings)):
            raise ValueError("heading_path must be a list of strings")
        canonical_heading_path = tuple(list.__iter__(headings))
        _validate_span_record_values(
            span_id, page_no, canonical_heading_path, offset, text
        )
        return cls(
            cast(str, span_id),
            cast(int | None, page_no),
            canonical_heading_path,
            cast(int, offset),
            cast(str, text),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "page_no": self.page_no,
            "heading_path": list(self.heading_path),
            "offset": self.offset,
            "text": self.text,
        }


@dataclass(frozen=True)
class SpanSidecar:
    """Schema-v1 sidecar for the machine-generated raw OKF Markdown file."""

    schema_version: int
    doc_id: str
    version_id: str
    spans: tuple[SpanRecord, ...]

    def __post_init__(self) -> None:
        schema_version = object.__getattribute__(self, "schema_version")
        doc_id = object.__getattribute__(self, "doc_id")
        version_id = object.__getattribute__(self, "version_id")
        spans = object.__getattribute__(self, "spans")
        if type(schema_version) is not int or schema_version != SIDECAR_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {SIDECAR_SCHEMA_VERSION}, got invalid value"
            )
        _validate_uuid(doc_id, "doc_id")
        _validate_uuid(version_id, "version_id")
        if type(spans) is not tuple:
            raise ValueError("spans must be a tuple of SpanRecord instances")
        for span in tuple.__iter__(spans):
            _span_record_values(span)
        if tuple.__len__(spans) > MAX_SIDECAR_SPAN_COUNT:
            raise ValueError("sidecar exceeds maximum span count")

    @classmethod
    def load(cls, path: Path) -> SpanSidecar:
        """Load through the legacy standalone safe reader."""
        return cls.from_bytes(_read_sidecar_bytes_bounded(path))

    @classmethod
    def from_bytes(cls, raw: bytes) -> SpanSidecar:
        """Parse bounded sidecar bytes without performing filesystem I/O."""
        if len(raw) > MAX_SIDECAR_BYTES:
            raise ValueError("sidecar exceeds maximum size")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("sidecar must be valid UTF-8") from None
        _preflight_json_resources(text)
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateJsonKey:
            raise ValueError("sidecar contains duplicate JSON key") from None
        except (json.JSONDecodeError, _InvalidJsonConstant):
            raise ValueError("sidecar contains invalid JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("sidecar root must be a JSON object")
        return cls.from_dict(parsed)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpanSidecar:
        _validate_exact_dict_fields(value, _ROOT_FIELDS)
        payload = cast(dict[str, Any], value)
        _require_dict_fields(
            payload, ("spans", "schema_version", "doc_id", "version_id")
        )
        schema_version: object = dict.__getitem__(payload, "schema_version")
        doc_id: object = dict.__getitem__(payload, "doc_id")
        version_id: object = dict.__getitem__(payload, "version_id")
        spans: object = dict.__getitem__(payload, "spans")
        if type(schema_version) is not int:
            raise ValueError("schema_version must be an integer")
        if type(doc_id) is not str:
            raise ValueError("doc_id must be a string")
        if type(version_id) is not str:
            raise ValueError("version_id must be a string")
        if type(spans) is not list:
            raise ValueError("spans must be a list")
        span_payloads = cast(list[object], spans)
        if list.__len__(span_payloads) > MAX_SIDECAR_SPAN_COUNT:
            raise ValueError("sidecar exceeds maximum span count")
        records: list[SpanRecord] = []
        for index, span in enumerate(list.__iter__(span_payloads)):
            if type(span) is not dict:
                raise ValueError(f"spans[{index}] must be an object")
            span_payload = cast(dict[str, Any], span)
            _validate_span_payload_budget(span_payload)
            records.append(SpanRecord.from_dict(span_payload))
        return cls(
            cast(int, schema_version),
            cast(str, doc_id),
            cast(str, version_id),
            tuple(records),
        )

    def to_bytes(self) -> bytes:
        """Return the frozen schema-v1 byte representation without filesystem I/O."""
        raw = b"".join(_sidecar_json_chunks(self))
        if len(raw) > MAX_SIDECAR_BYTES:
            raise ValueError("sidecar exceeds maximum size")
        return raw

    def dump(self, path: Path) -> None:
        """Atomically replace ``path`` with exact schema-v1 JSON bytes."""
        size = sum(len(chunk) for chunk in _sidecar_json_chunks(self))
        if size > MAX_SIDECAR_BYTES:
            raise ValueError("sidecar exceeds maximum size")
        descriptor: int | None = None
        temporary_name: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            temporary_file = os.fdopen(descriptor, "wb")
            descriptor = None
            with temporary_file:
                _write_all(temporary_file, _sidecar_json_chunks(self))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
        except (OSError, ValueError):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            raise ValueError("sidecar cannot be written") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "doc_id": self.doc_id,
            "version_id": self.version_id,
            "spans": [span.to_dict() for span in self.spans],
        }


def _span_record_values(
    value: object,
) -> tuple[str, int | None, tuple[str, ...], int, str]:
    if type(value) is not SpanRecord:
        raise ValueError("spans must be a tuple of SpanRecord instances")
    try:
        values = (
            object.__getattribute__(value, "span_id"),
            object.__getattribute__(value, "page_no"),
            object.__getattribute__(value, "heading_path"),
            object.__getattribute__(value, "offset"),
            object.__getattribute__(value, "text"),
        )
    except AttributeError:
        raise ValueError("span record has invalid canonical fields") from None
    _validate_span_record_values(*values)
    return cast(tuple[str, int | None, tuple[str, ...], int, str], values)


def _validate_span_record_values(
    span_id: object,
    page_no: object,
    heading_path: object,
    offset: object,
    text: object,
) -> None:
    _validate_uuid(span_id, "span_id")
    if page_no is not None and (type(page_no) is not int or page_no < 0):
        raise ValueError("page_no must be a non-negative integer or null")
    if type(heading_path) is not tuple:
        raise ValueError("heading_path must be a tuple of strings")
    if any(type(heading) is not str for heading in tuple.__iter__(heading_path)):
        raise ValueError("heading_path must be a tuple of strings")
    _validate_heading_path_budget(heading_path)
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    _validate_non_empty_string(text, "text")
    _validate_span_text_budget(cast(str, text))


def _is_non_negative_integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _validate_non_empty_string(value: object, field: str) -> None:
    if type(value) is not str or str.__len__(value) == 0:
        raise ValueError(f"{field} must be a non-empty string")


def _validate_uuid(value: object, field: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{field} must be a UUID")
    try:
        UUID(value)
    except ValueError:
        raise ValueError(f"{field} must be a UUID") from None


def _validate_exact_dict_fields(value: object, allowed: frozenset[str]) -> None:
    if type(value) is not dict:
        raise ValueError("sidecar must be an object")
    keys = dict.keys(value)
    if any(type(field) is not str for field in dict.__iter__(value)):
        raise ValueError("sidecar contains unknown field")
    if frozenset(keys) - allowed:
        raise ValueError("sidecar contains unknown field")


def _require_dict_fields(value: dict[str, Any], required: tuple[str, ...]) -> None:
    for field in required:
        if not dict.__contains__(value, field):
            raise ValueError(f"{field} is required")


def _read_sidecar_bytes_bounded(path: Path) -> bytes:
    """Reject swapped or nonregular paths, then bounded-read the opened fd."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        initial_metadata = os.lstat(path)
        if not stat.S_ISREG(initial_metadata.st_mode):
            raise OSError
        descriptor = os.open(os.fspath(path), flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError
        if metadata.st_size > MAX_SIDECAR_BYTES:
            raise ValueError("sidecar exceeds maximum size")
        if not os.path.samestat(initial_metadata, metadata):
            raise OSError
        chunks = bytearray()
        while True:
            remaining = MAX_SIDECAR_BYTES + 1 - len(chunks)
            if remaining == 0:
                raise ValueError("sidecar exceeds maximum size")
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            if len(chunk) > remaining:
                raise ValueError("sidecar exceeds maximum size")
            chunks.extend(chunk)
    except ValueError:
        raise
    except OSError:
        raise ValueError("sidecar cannot be read") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return bytes(chunks)


@dataclass
class _JsonFrame:
    kind: str
    seen: set[str]
    expect_key: bool = True
    key: str | None = None
    count: int = 0
    segments: int = 0


@dataclass
class _JsonPreflight:
    stack: list[_JsonFrame]
    nodes: int = 0
    string_source_bytes: int = 0
    heading_segments_total: int = 0


def _preflight_json_resources(text: str) -> None:
    """Apply bounded schema-aware lexical checks before JSON materialization."""
    state = _JsonPreflight([])
    index = 0
    while index < len(text):
        index = _preflight_json_token(text, index, state)
        if state.nodes > MAX_SIDECAR_STRUCTURAL_TOKENS:
            raise ValueError("sidecar JSON resource limit exceeded")


def _preflight_json_token(text: str, index: int, state: _JsonPreflight) -> int:
    character = text[index]
    if character.isspace() or character in ":,":
        if (
            character == ","
            and state.stack
            and state.stack[-1].kind in {"root", "span"}
        ):
            state.stack[-1].expect_key = True
        return index + 1
    if character == '"':
        end = _scan_json_string(text, index)
        if end is None:
            return len(text)
        token = text[index:end]
        state.string_source_bytes = _count_string_bytes(
            state.string_source_bytes, token
        )
        frame = state.stack[-1] if state.stack else None
        if frame and frame.kind in {"root", "span"} and frame.expect_key:
            _accept_json_key(frame, token)
        else:
            state.heading_segments_total = _accept_scalar(
                frame, True, state.heading_segments_total, token
            )
            state.nodes += 1
        return end
    if character in "[{":
        frame = state.stack[-1] if state.stack else None
        state.stack.append(_JsonFrame(_accept_container(frame, character), set()))
        state.nodes += 1
        if len(state.stack) > MAX_SIDECAR_JSON_DEPTH:
            raise ValueError("sidecar JSON exceeds maximum depth")
        return index + 1
    if character in "]}":
        if state.stack:
            state.stack.pop()
        return index + 1
    return _preflight_json_scalar(text, index, state)


def _preflight_json_scalar(text: str, index: int, state: _JsonPreflight) -> int:
    end = index
    while end < len(text) and not text[end].isspace() and text[end] not in ",]}:":
        end += 1
    token = text[index:end]
    if (
        token
        and token[0] in "-0123456789"
        and len(token.encode("utf-8")) > MAX_JSON_NUMBER_TOKEN_BYTES
    ):
        raise ValueError("sidecar JSON resource limit exceeded")
    state.heading_segments_total = _accept_scalar(
        state.stack[-1] if state.stack else None, False, state.heading_segments_total
    )
    state.nodes += 1
    return end


def _count_string_bytes(total: int, token: str) -> int:
    total += len(token.encode("utf-8"))
    if total > MAX_JSON_STRING_SOURCE_BYTES:
        raise ValueError("sidecar JSON resource limit exceeded")
    return total


def _accept_json_key(frame: _JsonFrame, token: str) -> None:
    if len(token.encode("utf-8")) > MAX_JSON_KEY_TOKEN_BYTES:
        raise ValueError("sidecar JSON resource limit exceeded")
    try:
        key = _KEY_TOKEN_DECODER.decode(token)
    except (json.JSONDecodeError, ValueError):
        frame.key = None
        frame.expect_key = False
        return
    allowed = _ROOT_FIELDS if frame.kind == "root" else _SPAN_FIELDS
    if key not in allowed:
        raise ValueError("sidecar contains unknown field")
    if key in frame.seen:
        raise ValueError("sidecar contains duplicate JSON key")
    frame.seen.add(key)
    frame.key = key
    frame.expect_key = False


def _accept_container(frame: _JsonFrame | None, character: str) -> str:
    if frame is None:
        return "root" if character == "{" else "other"
    if frame.kind == "root":
        if frame.key == "spans" and character == "[":
            _finish_object_value(frame)
            return "spans"
        raise ValueError("sidecar schema has invalid container position")
    if frame.kind == "spans":
        if character != "{":
            raise ValueError("sidecar schema has invalid container position")
        frame.count += 1
        if frame.count > MAX_SIDECAR_SPAN_COUNT:
            raise ValueError("sidecar exceeds maximum span count")
        return "span"
    if frame.kind == "span":
        if frame.key == "heading_path" and character == "[":
            _finish_object_value(frame)
            return "heading"
        raise ValueError("sidecar schema has invalid container position")
    if frame.kind == "heading":
        raise ValueError("sidecar schema has invalid container position")
    return "other"


def _accept_scalar(
    frame: _JsonFrame | None,
    is_string: bool,
    heading_segments_total: int,
    token: str | None = None,
) -> int:
    if frame is None or frame.kind == "other":
        return heading_segments_total
    if frame.kind == "heading":
        if not is_string:
            raise ValueError("sidecar schema has invalid container position")
        _validate_decoded_string_token(
            token,
            MAX_HEADING_SEGMENT_BYTES,
            "heading_path segment exceeds maximum size",
            "heading_path segment must be valid UTF-8",
        )
        frame.segments += 1
        heading_segments_total += 1
        if (
            frame.segments > MAX_HEADING_SEGMENTS
            or heading_segments_total > MAX_HEADING_SEGMENTS_TOTAL
        ):
            raise ValueError("heading_path exceeds maximum segment count")
        return heading_segments_total
    if frame.kind == "spans":
        raise ValueError("sidecar schema has invalid container position")
    if frame.key == "spans" or frame.key == "heading_path":
        raise ValueError("sidecar schema has invalid container position")
    if is_string and frame.key == "text":
        _validate_decoded_string_token(
            token,
            MAX_SPAN_TEXT_BYTES,
            "span text exceeds maximum size",
            "span text must be valid UTF-8",
        )
    _finish_object_value(frame)
    return heading_segments_total


def _validate_decoded_string_token(
    token: str | None, maximum_bytes: int, size_error: str, encoding_error: str
) -> None:
    """Bound a schema-relevant decoded string without materializing the document."""
    if token is None:
        return
    try:
        value = _VALUE_TOKEN_DECODER.decode(token)
    except (json.JSONDecodeError, ValueError):
        return
    _validate_utf8_size(value, maximum_bytes, size_error, encoding_error)


def _finish_object_value(frame: _JsonFrame) -> None:
    frame.key = None
    frame.expect_key = True


def _scan_json_string(text: str, start: int) -> int | None:
    escaped = False
    for index in range(start + 1, len(text)):
        character = text[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return index + 1
    return None


class _DuplicateJsonKey(ValueError):
    pass


class _InvalidJsonConstant(ValueError):
    pass


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _InvalidJsonConstant


def _sidecar_json_chunks(sidecar: SpanSidecar) -> Iterator[bytes]:
    """Yield the historical ``indent=2`` representation without whole-output allocation."""

    def scalar(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    yield b"{\n"
    yield b'  "schema_version": ' + scalar(sidecar.schema_version) + b",\n"
    yield b'  "doc_id": ' + scalar(sidecar.doc_id) + b",\n"
    yield b'  "version_id": ' + scalar(sidecar.version_id) + b",\n"
    if not sidecar.spans:
        yield b'  "spans": []\n'
    else:
        yield b'  "spans": [\n'
        for span_index, span in enumerate(sidecar.spans):
            yield b"    {\n"
            yield b'      "span_id": ' + scalar(span.span_id) + b",\n"
            yield b'      "page_no": ' + scalar(span.page_no) + b",\n"
            if not span.heading_path:
                yield b'      "heading_path": [],\n'
            else:
                yield b'      "heading_path": [\n'
                for heading_index, heading in enumerate(span.heading_path):
                    suffix = b"," if heading_index + 1 < len(span.heading_path) else b""
                    yield b"        " + scalar(heading) + suffix + b"\n"
                yield b"      ],\n"
            yield b'      "offset": ' + scalar(span.offset) + b",\n"
            yield b'      "text": ' + scalar(span.text) + b"\n"
            suffix = b"," if span_index + 1 < len(sidecar.spans) else b""
            yield b"    }" + suffix + b"\n"
        yield b"  ]\n"
    yield b"}\n"


def _write_all(file: Any, chunks: Iterator[bytes]) -> None:
    for chunk in chunks:
        view = memoryview(chunk)
        while view:
            written = file.write(view)
            if written is None:
                written = len(view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]


def _validate_span_payload_budget(span: Mapping[str, Any]) -> None:
    if type(span) is not dict:
        return
    heading_path = dict.get(span, "heading_path")
    if type(heading_path) is list:
        _validate_heading_path_budget(heading_path)
    text = dict.get(span, "text")
    if type(text) is str:
        _validate_span_text_budget(text)


def _validate_heading_path_budget(heading_path: tuple[str, ...] | list[str]) -> None:
    if type(heading_path) is tuple:
        tuple_sequence = cast(tuple[str, ...], heading_path)
        if tuple.__len__(tuple_sequence) > MAX_HEADING_SEGMENTS:
            raise ValueError("heading_path exceeds maximum segment count")
        _validate_heading_segments(tuple.__iter__(tuple_sequence))
        return
    list_sequence = cast(list[str], heading_path)
    if list.__len__(list_sequence) > MAX_HEADING_SEGMENTS:
        raise ValueError("heading_path exceeds maximum segment count")
    _validate_heading_segments(list.__iter__(list_sequence))


def _validate_heading_segments(segments: Iterator[str]) -> None:
    for segment in segments:
        if type(segment) is str:
            _validate_utf8_size(
                segment,
                MAX_HEADING_SEGMENT_BYTES,
                "heading_path segment exceeds maximum size",
                "heading_path segment must be valid UTF-8",
            )


def _validate_span_text_budget(text: str) -> None:
    _validate_utf8_size(
        text,
        MAX_SPAN_TEXT_BYTES,
        "span text exceeds maximum size",
        "span text must be valid UTF-8",
    )


def _validate_utf8_size(
    value: str, maximum_bytes: int, size_error: str, encoding_error: str
) -> None:
    try:
        encoded = str.encode(value, "utf-8")
    except UnicodeEncodeError:
        raise ValueError(encoding_error) from None
    if len(encoded) > maximum_bytes:
        raise ValueError(size_error)
