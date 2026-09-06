"""Phase 16-05 RED tests: frozen deterministic token-aware segmenter.

Pins ``segment_text(span, *, max_tokens, tokenizer, segmentation_version)``
returning a tuple of frozen ``Segment`` values: the exact seven-field frozen
shape; full-span code-point coverage with zero gap and zero overlap (never
splitting a surrogate pair); deterministic ``segment_id`` derived only from
the frozen canonical payload ``(parent_span_id, start, end,
segmentation_version)``; shuffle-equivalent determinism; fail-closed budgets,
versions, empty text, malformed tokenizer output, and slow tokenizers; the
frozen fast-tokenizer call contract (``return_offsets_mapping=True``,
``add_special_tokens=False``, ``truncation=False``); no substring coordinate
recovery; and the zero heavy-import boundary (no modelscope/torch/
sentencepiece/jieba) in-process and in a fresh subprocess. Tokenizers are
injected fakes only; no heavy dependency is imported by this module.
"""

from __future__ import annotations

import inspect
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from uuid import UUID

import pytest

from llamaindex_runtime.entity import Segment, segment_text
from llamaindex_runtime.entity import segmenter
from llamaindex_runtime.entity.contracts import (
    CorpusSpanInput,
    canonical_json,
    deterministic_id,
)

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_CORPUS_NORMALIZED = "猫猫今天开会"
_SEG_VERSION = "seg-1"


def _corpus_input(**overrides: object) -> CorpusSpanInput:
    base: dict[str, object] = {
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "span_id": _SPAN_ID,
        "document_revision": "abc-v2",
        "input_revision": "abc-v2",
        "normalized_text": _CORPUS_NORMALIZED,
        "normalization_version": "norm-1",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return CorpusSpanInput(**base)  # type: ignore[arg-type]


_DEFAULT_TOKENIZER = object()


def _segment(
    text: str | None = None,
    *,
    max_tokens: object = 2,
    tokenizer: object = _DEFAULT_TOKENIZER,
    segmentation_version: object = _SEG_VERSION,
    span: object = None,
) -> tuple[Segment, ...]:
    """Compact ``segment_text`` wrapper with focused defaults."""
    if text is not None:
        span = _corpus_input(normalized_text=text)
    elif span is None:
        span = _corpus_input()
    return segment_text(
        span,  # type: ignore[arg-type]
        max_tokens=max_tokens,  # type: ignore[arg-type]
        tokenizer=tokenizer if tokenizer is not _DEFAULT_TOKENIZER else _CharTokenizer(),
        segmentation_version=segmentation_version,  # type: ignore[arg-type]
    )


def _assert_raises(
    text: str, offsets: object, match: str, *, max_tokens: object = 2
) -> None:
    """Assert ``segment_text`` fails closed for a fixed offset mapping."""
    with pytest.raises(ValueError, match=match):
        _segment(text, max_tokens=max_tokens, tokenizer=_FixedTokenizer(offsets))


class _TokenizeResult:
    """Fake fast-tokenizer output exposing ``offset_mapping`` as an attribute."""

    def __init__(self, offset_mapping: object) -> None:
        self.offset_mapping = offset_mapping


def _require_fast_kwargs(
    return_offsets_mapping: object, add_special_tokens: object, truncation: object
) -> None:
    assert return_offsets_mapping is True
    assert add_special_tokens is False
    assert truncation is False


class _FastTokenizer:
    """Shared fake-fast-tokenizer base enforcing the frozen kwarg contract."""

    is_fast = True

    def __call__(
        self,
        text: str,
        *,
        return_offsets_mapping: object,
        add_special_tokens: object,
        truncation: object,
    ) -> _TokenizeResult:
        _require_fast_kwargs(return_offsets_mapping, add_special_tokens, truncation)
        return _TokenizeResult(self._offsets_for(text))

    def _offsets_for(self, text: str) -> object:
        raise NotImplementedError


class _CharTokenizer(_FastTokenizer):
    """One token per Unicode code point; optional shuffle proves order invariance."""

    def __init__(self, *, shuffle_seed: int | None = None) -> None:
        self._shuffle_seed = shuffle_seed

    def _offsets_for(self, text: str) -> tuple[tuple[int, int], ...]:
        offsets = [(i, i + 1) for i in range(len(text))]
        if self._shuffle_seed is not None:
            random.Random(self._shuffle_seed).shuffle(offsets)
        return tuple(offsets)


class _FixedTokenizer(_FastTokenizer):
    """Returns exactly the supplied offset mapping (malformed-input tests)."""

    def __init__(self, offset_mapping: object) -> None:
        self._offset_mapping = offset_mapping

    def _offsets_for(self, text: str) -> object:
        return self._offset_mapping


class _WordTokenizer(_FastTokenizer):
    """Whitespace-skipping word tokenizer (no special tokens)."""

    def _offsets_for(self, text: str) -> tuple[tuple[int, int], ...]:
        offsets: list[tuple[int, int]] = []
        length = len(text)
        position = 0
        while position < length:
            if text[position].isspace():
                position += 1
                continue
            start = position
            while position < length and not text[position].isspace():
                position += 1
            offsets.append((start, position))
        return tuple(offsets)


class _RecordingTokenizer(_FastTokenizer):
    """Records the exact kwargs passed by ``segment_text``."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def _offsets_for(self, text: str) -> object:
        self.calls.append(
            {
                "text": text,
                "return_offsets_mapping": True,
                "add_special_tokens": False,
                "truncation": False,
            }
        )
        return tuple((i, i + 1) for i in range(len(text)))


def test_segment_text_public_signature_is_keyword_only_for_options() -> None:
    parameters = inspect.signature(segment_text).parameters
    names = list(parameters)
    assert names[0] == "span"
    assert names[1:] == ["max_tokens", "tokenizer", "segmentation_version"]
    for name in ("max_tokens", "tokenizer", "segmentation_version"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_segment_is_frozen_with_exact_seven_field_shape() -> None:
    assert [field.name for field in fields(Segment)] == [
        "segment_id",
        "parent_span_id",
        "start",
        "end",
        "text",
        "segmentation_version",
        "token_count",
    ]
    assert Segment.__dataclass_params__.frozen  # type: ignore[attr-defined]
    segment = _segment()[0]
    with pytest.raises(FrozenInstanceError):
        segment.text = "changed"  # type: ignore[misc]


_SEGMENT_BASE: dict[str, object] = {
    "segment_id": "seg-1",
    "parent_span_id": _SPAN_ID,
    "start": 0,
    "end": 2,
    "text": "猫猫",
    "segmentation_version": _SEG_VERSION,
    "token_count": 2,
}


@pytest.mark.parametrize(
    ("field", "bad", "match"),
    [
        ("segment_id", "", "segment_id"),
        ("parent_span_id", "", "parent_span_id"),
        ("start", 0.0, "coordinates"),
        ("start", True, "coordinates"),
        ("start", 2, "start < end"),
        ("text", "", "text"),
        ("segmentation_version", "", "segmentation_version"),
        ("token_count", -1, "token_count"),
        ("token_count", True, "token_count"),
    ],
)
def test_segment_rejects_invalid_field_values(
    field: str, bad: object, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        Segment(**{**_SEGMENT_BASE, field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["猫猫猫", "猫"])
def test_segment_rejects_text_length_mismatch(text: str) -> None:
    with pytest.raises(ValueError, match="length"):
        Segment(**{**_SEGMENT_BASE, "text": text})  # type: ignore[arg-type]


def test_segment_token_count_zero_requires_whitespace_only_text() -> None:
    with pytest.raises(ValueError, match="whitespace"):
        Segment(**{**_SEGMENT_BASE, "token_count": 0})  # type: ignore[arg-type]
    whitespace = Segment(
        segment_id="seg-2",
        parent_span_id=_SPAN_ID,
        start=0,
        end=3,
        text="   ",
        segmentation_version=_SEG_VERSION,
        token_count=0,
    )
    assert whitespace.token_count == 0


def test_short_span_within_budget_yields_single_covering_segment() -> None:
    text = "猫猫今天开会"
    segments = _segment(text, max_tokens=100)
    assert len(segments) == 1
    segment = segments[0]
    assert (segment.start, segment.end, segment.text, segment.token_count) == (
        0,
        len(text),
        text,
        len(text),
    )
    assert segment.parent_span_id == _SPAN_ID
    assert segment.segmentation_version == _SEG_VERSION


def test_long_span_splits_into_deterministic_segments() -> None:
    text = "猫猫今天开会"
    segments = _segment(text, max_tokens=2)
    assert [(s.start, s.end, s.text, s.token_count) for s in segments] == [
        (0, 2, "猫猫", 2),
        (2, 4, "今天", 2),
        (4, 6, "开会", 2),
    ]
    for segment in segments:
        assert segment.parent_span_id == _SPAN_ID


def test_full_span_coverage_zero_gap_zero_overlap() -> None:
    text = "猫猫今天开会议程很紧张"
    segments = _segment(text, max_tokens=2)
    assert segments
    assert segments[0].start == 0
    assert segments[-1].end == len(text)
    for left, right in zip(segments, segments[1:]):
        assert left.end == right.start  # zero gap and zero overlap
    assert "".join(segment.text for segment in segments) == text
    for segment in segments:
        assert text[segment.start : segment.end] == segment.text
        assert 0 <= segment.start < segment.end <= len(text)


@pytest.mark.parametrize("max_tokens", [1, 2, 3, 5, 100])
def test_every_segment_respects_token_budget(max_tokens: int) -> None:
    text = "猫猫今天开会议程很紧张，我们讨论了😀emoji与é组合字符。"
    segments = _segment(text, max_tokens=max_tokens)
    for segment in segments:
        assert segment.token_count <= max_tokens
        assert segment.token_count > 0
    assert "".join(segment.text for segment in segments) == text


def test_segment_ids_use_exact_canonical_identity_payload() -> None:
    span = _corpus_input(normalized_text="猫猫今天开会")
    segments = _segment(span=span, max_tokens=2)
    for segment in segments:
        expected = deterministic_id(
            "segment",
            canonical_json(
                {
                    "parent_span_id": span.span_id,
                    "start": segment.start,
                    "end": segment.end,
                    "segmentation_version": _SEG_VERSION,
                }
            ),
        )
        assert segment.segment_id == expected


def test_segment_ids_are_unique_and_exclude_model_or_tokenizer_identity() -> None:
    text = "猫猫今天开会议程很紧张"
    span = _corpus_input(normalized_text=text)
    segments = _segment(span=span, max_tokens=2)
    ids = [segment.segment_id for segment in segments]
    assert len(ids) == len(set(ids))
    offsets = [(i, i + 1) for i in range(len(text))]
    fixed = _segment(span=span, max_tokens=2, tokenizer=_FixedTokenizer(offsets))
    assert [segment.segment_id for segment in fixed] == ids


def test_repeated_calls_are_byte_identical() -> None:
    span = _corpus_input(normalized_text="猫猫今天开会议程很紧张")
    first = _segment(span=span, max_tokens=3)
    second = _segment(span=span, max_tokens=3)
    assert first == second


def test_shuffled_offset_ordering_is_byte_identical() -> None:
    span = _corpus_input(normalized_text="猫猫今天开会")
    natural = _segment(span=span, max_tokens=2)
    for seed in range(4):
        shuffled = _segment(
            span=span, max_tokens=2, tokenizer=_CharTokenizer(shuffle_seed=seed)
        )
        assert shuffled == natural


def test_equivalent_tokenizer_output_orderings_are_identical() -> None:
    natural = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]
    span = _corpus_input(normalized_text="猫猫今天开会")
    forward = _segment(span=span, max_tokens=2, tokenizer=_FixedTokenizer(natural))
    backward = _segment(
        span=span,
        max_tokens=2,
        tokenizer=_FixedTokenizer(list(reversed(natural))),
    )
    assert forward == backward


def test_code_point_safety_emoji_combining_and_cjk() -> None:
    text = "😀猫é😀"  # 5 code points: astral, CJK, latin+combining, astral
    assert len(text) == 5
    segments = _segment(text, max_tokens=2)
    assert [(s.start, s.end, s.text) for s in segments] == [
        (0, 2, "😀猫"),
        (2, 4, "é"),
        (4, 5, "😀"),
    ]
    for segment in segments:
        segment.text.encode("utf-16", errors="strict")  # no lone surrogate
        assert text[segment.start : segment.end] == segment.text
    assert "".join(segment.text for segment in segments) == text


def test_astral_and_combining_text_slices_back_exactly() -> None:
    text = "é😀é"
    segments = _segment(text, max_tokens=2)
    for segment in segments:
        assert text[segment.start : segment.end] == segment.text
    assert "".join(segment.text for segment in segments) == text


@pytest.mark.parametrize(
    ("text", "max_tokens", "expected"),
    [
        ("猫猫猫猫", 2, [(0, 2, "猫猫"), (2, 4, "猫猫")]),
        ("猫猫狗狗猫猫", 3, [(0, 3, "猫猫狗"), (3, 6, "狗猫猫")]),
    ],
)
def test_repeated_text_no_substring_coordinate_recovery(
    text: str, max_tokens: int, expected: list[tuple[int, int, str]]
) -> None:
    segments = _segment(text, max_tokens=max_tokens)
    assert [(s.start, s.end, s.text) for s in segments] == expected
    ids = [segment.segment_id for segment in segments]
    assert len(ids) == len(set(ids))
    assert "".join(segment.text for segment in segments) == text


def test_leading_trailing_and_inter_token_whitespace_preserved() -> None:
    text = "  猫猫  狗狗  "
    segments = _segment(text, max_tokens=2, tokenizer=_WordTokenizer())
    assert "".join(segment.text for segment in segments) == text
    assert segments[0].start == 0
    assert segments[-1].end == len(text)
    for segment in segments:
        assert text[segment.start : segment.end] == segment.text


def test_inter_token_whitespace_attaches_to_preceding_segment() -> None:
    segments = _segment("hello world", max_tokens=1, tokenizer=_WordTokenizer())
    assert [(s.start, s.end, s.text, s.token_count) for s in segments] == [
        (0, 6, "hello ", 1),
        (6, 11, "world", 1),
    ]


def test_leading_whitespace_multi_segment_boundaries() -> None:
    text = "  猫猫  狗狗"  # 8 code points
    assert len(text) == 8
    segments = _segment(text, max_tokens=1, tokenizer=_WordTokenizer())
    assert [(s.start, s.end, s.text, s.token_count) for s in segments] == [
        (0, 6, "  猫猫  ", 1),
        (6, 8, "狗狗", 1),
    ]


def test_whitespace_only_text_yields_single_covering_segment_with_zero_tokens() -> None:
    text = "   "
    segments = _segment(text, max_tokens=2, tokenizer=_WordTokenizer())
    assert len(segments) == 1
    segment = segments[0]
    assert (segment.start, segment.end, segment.text, segment.token_count) == (
        0,
        len(text),
        text,
        0,
    )


@pytest.mark.parametrize("bad", [0, -1, -100, True, False, 2.5, "2", None, [2]])
def test_max_tokens_invalid_fails_closed(bad: object) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        _segment(max_tokens=bad)


@pytest.mark.parametrize("bad", ["", None, 3, 3.5, ["seg"]])
def test_empty_or_non_string_segmentation_version_fails_closed(bad: object) -> None:
    with pytest.raises(ValueError, match="segmentation_version"):
        _segment(segmentation_version=bad)


def test_non_corpus_span_input_rejected() -> None:
    with pytest.raises(ValueError, match="CorpusSpanInput"):
        _segment(span=object())


def test_empty_normalized_text_fails_closed_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llamaindex_runtime.entity.contracts as contracts

    # Bypass CorpusSpanInput's own empty-text rejection so the segmenter's
    # defense-in-depth guard is exercised.
    monkeypatch.setattr(contracts.CorpusSpanInput, "__post_init__", lambda self: None)
    span = CorpusSpanInput(
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        span_id=_SPAN_ID,
        document_revision="abc-v2",
        input_revision="abc-v2",
        normalized_text="",
        normalization_version="norm-1",
        projection={"document_char_start": 0, "document_char_end": 2},
    )
    with pytest.raises(ValueError, match="normalized_text"):
        _segment(span=span)


@pytest.mark.parametrize("bad", [42, None, "not-callable", [1, 2]])
def test_tokenizer_non_callable_fails_closed(bad: object) -> None:
    with pytest.raises(ValueError, match="tokenizer"):
        _segment(tokenizer=bad)


@pytest.mark.parametrize("result", [object(), {"ids": [0]}])
def test_tokenizer_output_without_offset_mapping_fails_closed(result: object) -> None:
    class NoOffsets:
        is_fast = True

        def __call__(
            self,
            text: str,
            *,
            return_offsets_mapping: object,
            add_special_tokens: object,
            truncation: object,
        ) -> object:
            _require_fast_kwargs(return_offsets_mapping, add_special_tokens, truncation)
            return result

    with pytest.raises(ValueError, match="offset_mapping"):
        _segment(tokenizer=NoOffsets())


@pytest.mark.parametrize("bad", [42, "ab", None, {"a": 1}])
def test_offset_mapping_not_a_sequence_fails_closed(bad: object) -> None:
    with pytest.raises(ValueError, match="offset"):
        _segment("abc", tokenizer=_FixedTokenizer(bad))


@pytest.mark.parametrize(
    "bad",
    [[(0, 1, 2)], [(0,)], [["a", 1]], [(True, 1)], [(0, 2.5)], [("0", 1)]],
)
def test_offset_entries_malformed_fail_closed(bad: object) -> None:
    with pytest.raises(ValueError, match="offset"):
        _segment("abc", tokenizer=_FixedTokenizer(bad))


@pytest.mark.parametrize(
    ("text", "offsets", "match"),
    [
        ("abc", [(-1, 1)], "range"),
        ("abc", [(0, 4)], "range"),
        ("abc", [(1, 1)], "start < end"),
        ("abc", [(2, 1)], "start < end"),
        ("abcde", [(0, 4), (2, 5)], "overlap"),
        ("abcde", [(1, 3), (1, 3)], "overlap"),
        ("abc", [(0, 0), (0, 1), (1, 2), (2, 3)], "start < end"),
    ],
)
def test_malformed_offsets_fail_closed(text: str, offsets: object, match: str) -> None:
    _assert_raises(text, offsets, match)


def test_tokenizer_result_supports_mapping_key_offset_mapping() -> None:
    class DictOutput:
        is_fast = True

        def __call__(
            self,
            text: str,
            *,
            return_offsets_mapping: object,
            add_special_tokens: object,
            truncation: object,
        ) -> dict[str, object]:
            _require_fast_kwargs(return_offsets_mapping, add_special_tokens, truncation)
            return {"offset_mapping": [(0, 1), (1, 2), (2, 3)]}

    segments = _segment("abc", tokenizer=DictOutput())
    assert [(s.start, s.end, s.text) for s in segments] == [
        (0, 2, "ab"),
        (2, 3, "c"),
    ]


def test_tokenizer_invoked_with_required_fast_tokenizer_kwargs() -> None:
    # Regression: a real HF fast tokenizer defaults to no offsets, so the call
    # MUST pass return_offsets_mapping=True, add_special_tokens=False,
    # truncation=False; the strict fake requires those keywords.
    tokenizer = _RecordingTokenizer()
    segments = _segment(tokenizer=tokenizer)
    assert len(tokenizer.calls) == 1
    call = tokenizer.calls[0]
    assert call["text"] == _CORPUS_NORMALIZED
    assert call["return_offsets_mapping"] is True
    assert call["add_special_tokens"] is False
    assert call["truncation"] is False
    assert segments


def test_slow_tokenizer_advertising_is_fast_false_fails_closed() -> None:
    # is_fast=False is the direct fast-only boundary; the slow tokenizer must
    # not even be invoked.
    class SlowTokenizer:
        is_fast = False

        def __init__(self) -> None:
            self.called = False

        def __call__(self, text: str, **kwargs: object) -> _TokenizeResult:
            self.called = True
            return _TokenizeResult([(0, 1), (1, 2)])

    slow = SlowTokenizer()
    with pytest.raises(ValueError, match="fast tokenizer"):
        _segment("ab", tokenizer=slow)
    assert slow.called is False


def test_tokenizer_full_text_no_truncation_and_no_special_tokens() -> None:
    text = "猫猫今天开会"
    tokenizer = _RecordingTokenizer()
    segments = _segment(text, tokenizer=tokenizer)
    assert tokenizer.calls[0]["text"] == text  # full text, never truncated
    assert "".join(segment.text for segment in segments) == text
    for segment in segments:
        assert text[segment.start : segment.end] == segment.text


@pytest.mark.parametrize(
    ("text", "offsets", "max_tokens"),
    [
        ("abc", [], 2),
        ("abc", [(2, 3)], 2),
        ("abc", [(0, 1), (2, 3)], 2),
        ("abc", [(0, 1)], 2),
        ("hello world", [(0, 5)], 10),
    ],
)
def test_uncovered_non_whitespace_fails_closed(
    text: str, offsets: object, max_tokens: object
) -> None:
    # Empty or partially-covering offsets for non-whitespace text must fail
    # closed: otherwise the max-token truncation protection is defeated.
    _assert_raises(text, offsets, "cover", max_tokens=max_tokens)


@pytest.mark.parametrize(
    ("text", "offsets"),
    [
        (" abc", [(1, 2), (2, 3), (3, 4)]),
        ("abc ", [(0, 1), (1, 2), (2, 3)]),
        ("a b", [(0, 1), (2, 3)]),
    ],
)
def test_whitespace_gaps_and_edges_remain_allowed(text: str, offsets: object) -> None:
    # Leading/trailing/inter-token whitespace uncovered by tokens stays legal.
    segments = _segment(text, max_tokens=10, tokenizer=_FixedTokenizer(offsets))
    assert "".join(segment.text for segment in segments) == text


def test_segmenter_source_never_uses_substring_search_or_split_length_apis() -> None:
    source = Path(segmenter.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "str.find",
        ".find(",
        "str.index",
        ".index(",
        "split_max_length",
    ):
        assert forbidden not in source, f"forbidden substring: {forbidden}"


def test_segmenter_source_imports_only_stdlib_and_contracts() -> None:
    source = Path(segmenter.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import modelscope",
        "from modelscope",
        "import torch",
        "from torch",
        "import transformers",
        "from transformers",
        "import tokenizers",
        "from tokenizers",
        "import sentencepiece",
        "from sentencepiece",
        "import jieba",
        "from jieba",
    ):
        assert forbidden not in source, f"forbidden import: {forbidden}"


def test_segmenter_source_uses_immutable_explicit_tokenizer_kwargs() -> None:
    # The call contract must not live in a mutable module-level dict; the frozen
    # keyword values are pinned explicitly at the call site.
    source = Path(segmenter.__file__).read_text(encoding="utf-8")
    assert "_TOKENIZER_KWARGS" not in source
    assert "return_offsets_mapping=True" in source
    assert "add_special_tokens=False" in source
    assert "truncation=False" in source


def test_facade_exports_segment_and_segment_text() -> None:
    import llamaindex_runtime.entity as entity

    assert entity.segment_text is segment_text
    assert entity.Segment is Segment
    assert "segment_text" in entity.__all__
    assert "Segment" in entity.__all__


def test_importing_entity_package_imports_no_heavy_dependencies() -> None:
    import llamaindex_runtime.entity as entity

    assert hasattr(entity, "segment_text")
    assert hasattr(entity, "Segment")
    for name in ("modelscope", "torch", "jieba", "sentencepiece"):
        assert name not in sys.modules, (
            f"llamaindex_runtime.entity must not import {name}"
        )


def test_fresh_process_import_of_entity_has_no_heavy_dependencies() -> None:
    root = Path(__file__).resolve().parents[3]
    code = (
        "import sys\n"
        "import llamaindex_runtime.entity\n"
        "heavy = ('modelscope', 'torch', 'jieba', 'sentencepiece')\n"
        "sys.exit(1 if any(name in sys.modules for name in heavy) else 0)\n"
    )
    env = {"PYTHONPATH": str(root), "PATH": os.environ.get("PATH", "")}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
