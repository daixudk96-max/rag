"""Deterministic token-aware segmentation for raw corpus spans (Phase 16-05).

Pure in-memory segmentation of ``CorpusSpanInput.normalized_text`` into
immutable frozen ``Segment`` values. Segment coordinates are Python Unicode
code-point half-open ``[start, end)`` intervals; concatenating every segment's
text reproduces ``normalized_text`` exactly with zero overlap and zero gap.

Tokenizer boundary
------------------
``tokenizer`` is an injected callable mirroring a HuggingFace **fast** tokenizer.
``segment_text`` invokes it with exactly three keyword arguments:

* ``return_offsets_mapping=True`` (a fast tokenizer otherwise emits no offsets),
* ``add_special_tokens=False`` (no CLS/SEP ``(0, 0)`` offsets),
* ``truncation=False`` (the full text is always tokenized).

A tokenizer that explicitly advertises ``is_fast = False`` (a slow tokenizer
that cannot produce authoritative offsets) fails closed before any call. The
result must expose ``offset_mapping`` either as an attribute
(``result.offset_mapping``) or as a mapping key (``result["offset_mapping"]``),
matching ``transformers.BatchEncoding``. Each entry is a ``(start, end)`` pair
of Python code-point half-open offsets into ``text``. Pair order is irrelevant:
offsets are canonicalized by sorting before consumption, so shuffled-but-valid
tokenizer output yields byte-identical segments. The segmenter consumes these
authoritative offsets directly and never recovers text positions by substring
search or ModelScope split-length truncation.

Segmentation guarantees
-----------------------
* exact full-span coverage with zero gap and zero overlap;
* every ``token_count`` is at most ``max_tokens``;
* every non-whitespace code point is covered by at least one validated token
  interval (an empty or partial offset list on non-whitespace text fails
  closed, so silent tokenizer truncation can never defeat the budget);
* ``segment_id`` derives only from ``(parent_span_id, start, end,
  segmentation_version)``;
* ``max_tokens <= 0``, empty ``segmentation_version``, empty
  ``normalized_text``, a non-callable tokenizer, a slow tokenizer
  (``is_fast is False``), and malformed offset output all fail closed.

This module imports only the standard library plus ``.contracts``; it never
imports modelscope, torch, transformers, tokenizers, sentencepiece, or jieba.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .contracts import CorpusSpanInput, canonical_json, deterministic_id

_TOKENIZER_ERROR = "tokenizer must return an offset_mapping"


@dataclass(frozen=True)
class Segment:
    """Immutable token-aware segment over exact normalized-text coordinates."""

    segment_id: str
    parent_span_id: str
    start: int
    end: int
    text: str
    segmentation_version: str
    token_count: int

    def __post_init__(self) -> None:
        if type(self.segment_id) is not str or not self.segment_id:
            raise ValueError("segment_id must be a non-empty string")
        if type(self.parent_span_id) is not str or not self.parent_span_id:
            raise ValueError("parent_span_id must be a non-empty string")
        if type(self.start) is not int or type(self.end) is not int:
            raise ValueError("segment coordinates must be integers")
        if not (0 <= self.start < self.end):
            raise ValueError("segment coordinates must satisfy 0 <= start < end")
        if type(self.text) is not str or not self.text:
            raise ValueError("segment text must be a non-empty string")
        if self.end - self.start != len(self.text):
            raise ValueError("segment text length must equal end - start")
        if type(self.segmentation_version) is not str or not self.segmentation_version:
            raise ValueError("segmentation_version must be a non-empty string")
        if type(self.token_count) is not int or self.token_count < 0:
            raise ValueError("token_count must be a non-negative integer")
        if self.token_count == 0 and not self.text.isspace():
            raise ValueError("token_count == 0 requires whitespace-only segment text")


def _validate_tokenizer(tokenizer: object) -> None:
    """Reject non-callable and explicitly-slow tokenizers before any call."""
    if not callable(tokenizer):
        raise ValueError("tokenizer must be callable")
    if getattr(tokenizer, "is_fast", None) is False:
        raise ValueError("tokenizer must be a fast tokenizer (is_fast=True)")


def _extract_offset_mapping(tokenizer_output: object) -> object:
    if hasattr(tokenizer_output, "offset_mapping"):
        return getattr(tokenizer_output, "offset_mapping")
    if isinstance(tokenizer_output, Mapping) and "offset_mapping" in tokenizer_output:
        return tokenizer_output["offset_mapping"]
    raise ValueError(_TOKENIZER_ERROR)


def _validate_offsets(
    offset_mapping: object, text_length: int
) -> list[tuple[int, int]]:
    if not isinstance(offset_mapping, Sequence) or isinstance(
        offset_mapping, (str, bytes)
    ):
        raise ValueError("offset_mapping must be a sequence of offset pairs")
    offsets: list[tuple[int, int]] = []
    for entry in offset_mapping:
        if (
            not isinstance(entry, Sequence)
            or isinstance(entry, (str, bytes))
            or len(entry) != 2
        ):
            raise ValueError("each offset must be a (start, end) pair")
        start, end = entry
        if type(start) is not int or type(end) is not int:
            raise ValueError("offset coordinates must be integers")
        if start < 0 or end > text_length:
            raise ValueError("offset coordinates are out of range")
        if start >= end:
            raise ValueError("offset coordinates must satisfy start < end")
        offsets.append((start, end))
    offsets.sort()
    for previous, current in zip(offsets, offsets[1:]):
        if previous[1] > current[0]:
            raise ValueError("offset coordinates must not overlap")
    return offsets


def _validate_offset_coverage(
    offsets: Sequence[tuple[int, int]], text: str
) -> None:
    """Every code point not covered by a validated token interval is whitespace.

    Consumes authoritative token coordinates with a single code-point scan of
    the normalized text; never recovers positions by substring search. An empty
    offset list is legitimate only when the entire text is whitespace, so a
    tokenizer that silently drops or truncates non-whitespace content (despite
    ``truncation=False``) fails closed instead of defeating the max-token
    truncation protection.
    """
    text_length = len(text)
    if not offsets:
        if not all(character.isspace() for character in text):
            raise ValueError("tokenizer must cover every non-whitespace code point")
        return
    position = 0
    for start, end in offsets:
        for index in range(position, start):
            if not text[index].isspace():
                raise ValueError("tokenizer must cover every non-whitespace code point")
        position = end
    for index in range(position, text_length):
        if not text[index].isspace():
            raise ValueError("tokenizer must cover every non-whitespace code point")


def _segment_bounds(
    offsets: Sequence[tuple[int, int]], text_length: int, max_tokens: int
) -> list[tuple[int, int, int]]:
    """Return ``(start, end, token_count)`` triples in canonical offset order.

    Tokens are packed greedily in sorted offset order until adding the next
    token would exceed the budget; the segment then closes at the start of the
    first excluded token (or at ``text_length`` for the final segment), so
    boundaries always land on authoritative token offsets and never split a
    code point.
    """
    if not offsets:
        return [(0, text_length, 0)]
    bounds: list[tuple[int, int, int]] = []
    segment_start = 0
    position = 0
    while position < len(offsets):
        token_count = 0
        while position < len(offsets) and token_count < max_tokens:
            token_count += 1
            position += 1
        if position < len(offsets):
            end = offsets[position][0]
        else:
            end = text_length
        bounds.append((segment_start, end, token_count))
        segment_start = end
    return bounds


def _segment_identity(
    span: CorpusSpanInput, start: int, end: int, segmentation_version: str
) -> str:
    """Deterministic segment id from the frozen canonical payload only."""
    return deterministic_id(
        "segment",
        canonical_json(
            {
                "parent_span_id": span.span_id,
                "start": start,
                "end": end,
                "segmentation_version": segmentation_version,
            }
        ),
    )


def _verify_exact_coverage(segments: Sequence[Segment], text: str) -> None:
    """Fail closed if concatenated segment texts drift from the source text."""
    if "".join(segment.text for segment in segments) != text:
        raise ValueError("segments must exactly cover normalized_text with zero gap")


def segment_text(
    span: CorpusSpanInput,
    *,
    max_tokens: int,
    tokenizer: object,
    segmentation_version: str,
) -> tuple[Segment, ...]:
    if not isinstance(span, CorpusSpanInput):
        raise ValueError("span must be a CorpusSpanInput")
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    if type(segmentation_version) is not str or not segmentation_version:
        raise ValueError("segmentation_version must be a non-empty string")
    _validate_tokenizer(tokenizer)

    text = span.normalized_text
    if type(text) is not str or not text:
        raise ValueError("normalized_text must be a non-empty string")

    offsets = _validate_offsets(
        _extract_offset_mapping(
            tokenizer(
                text,
                return_offsets_mapping=True,
                add_special_tokens=False,
                truncation=False,
            )
        ),
        len(text),
    )
    _validate_offset_coverage(offsets, text)
    bounds = _segment_bounds(offsets, len(text), max_tokens)

    segments = [
        Segment(
            segment_id=_segment_identity(span, start, end, segmentation_version),
            parent_span_id=span.span_id,
            start=start,
            end=end,
            text=text[start:end],
            segmentation_version=segmentation_version,
            token_count=token_count,
        )
        for start, end, token_count in bounds
    ]

    _verify_exact_coverage(segments, text)
    return tuple(segments)


__all__ = ["Segment", "segment_text"]
