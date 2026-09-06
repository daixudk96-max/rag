"""RED dictionary/frontmatter supplementary-source tests (Phase 16-08).

Pins the frozen 16-08 supplementary candidate contract:

- ``load_dictionary_candidates(dictionary, span) -> list[MentionCandidate]``,
- ``frontmatter_declared_candidates(frontmatter, span) -> list[MentionCandidate]``,
- CorpusSpanInput-only inputs; QueryTextInput is rejected fail-closed,
- deliberately plain source envelopes (no public DTOs): both carry the frozen
  ``extractor_id="supplementary"`` (any other value fails closed) plus
  non-empty ``extractor_version`` / ``schema_version`` /
  ``segmentation_version`` and a 64-lowercase-hex ``label_map_digest``;
  dictionary occurrences live under ``entries``, frontmatter declarations under
  the existing ``mentions`` key,
- explicit zero-based half-open Python Unicode code-point coordinates that are
  parent-span-local; the loader validates exact slice-back and NEVER locates
  text with find/index/search; duplicate mention text at distinct explicit
  coordinates stays distinct,
- full corpus identity/projection copied from CorpusSpanInput (input_id ==
  span_id, input_revision == document_revision, segment_id == None,
  normalization_version inherited from the span) while schema/segmentation/
  label-map/extractor provenance comes from the explicit source envelope,
- source/confidence_kind attribution (dictionary/dictionary_exact,
  frontmatter/frontmatter_declared); confidence == 1.0 is only an exact/
  declaration marker, never a calibrated probability or numeric ranking signal,
- model_id/model_revision/artifact_digest/runtime_compatibility_id all None,
- frontmatter candidates come ONLY from explicit ``mentions``; ``title`` and
  ``aliases`` are never scanned,
- typed fail-closed ValueError subclasses exposed by each module
  (``DictionarySourceError`` / ``FrontmatterSourceError``),
- inputs are never mutated; a dictionary-only pipeline never satisfies C1
  acceptance on its own (the RaNER model remains the primary recall source),
- zero heavy/model/persistence/network/generative-LLM imports and zero
  substring coordinate recovery.

RED by design: this file imports the missing production modules directly so
collection genuinely fails (ModuleNotFoundError) until dictionary_loader.py
and frontmatter_supplement.py exist.
"""

from __future__ import annotations

import ast
import copy
import inspect
import sys
from typing import Any
from uuid import UUID

import pytest

from llamaindex_runtime.entity.contracts import (
    CorpusSpanInput,
    MentionCandidate,
    QueryTextInput,
)
from llamaindex_runtime.entity.dictionary_loader import (
    DictionarySourceError,
    load_dictionary_candidates,
)
from llamaindex_runtime.entity.frontmatter_supplement import (
    FrontmatterSourceError,
    frontmatter_declared_candidates,
)
import llamaindex_runtime.entity.dictionary_loader as dictionary_loader_module
import llamaindex_runtime.entity.frontmatter_supplement as frontmatter_supplement_module

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_QUERY_ID = str(UUID(int=10))
_NORMALIZED = "猫猫今天开会议程很紧张"
_LABEL_MAP_DIGEST = "c" * 64

_FORBIDDEN_IMPORT_MARKERS = (
    "modelscope",
    "torch",
    "jieba",
    "psycopg",
    "sqlite",
    "postgres",
    "urllib",
    "requests",
    "http",
    "socket",
    "openai",
    "anthropic",
    "raner_adapter",
    "offline_mirror",
    "registry",
    "llm",
)


def _corpus_input(**overrides: object) -> CorpusSpanInput:
    base: dict[str, object] = {
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "span_id": _SPAN_ID,
        "document_revision": "abc-v2",
        "input_revision": "abc-v2",
        "normalized_text": _NORMALIZED,
        "normalization_version": "norm-1",
        "projection": {"document_char_start": 0, "document_char_end": 6},
    }
    base.update(overrides)
    return CorpusSpanInput(**base)  # type: ignore[arg-type]


def _query_input(**overrides: object) -> QueryTextInput:
    base: dict[str, object] = {
        "query_id": _QUERY_ID,
        "query_revision": "query-v7",
        "input_revision": "query-v7",
        "normalized_text": _NORMALIZED,
        "normalization_version": "norm-1",
    }
    base.update(overrides)
    return QueryTextInput(**base)  # type: ignore[arg-type]


def _entry(**overrides: object) -> dict[str, object]:
    """One explicit dictionary occurrence / frontmatter declaration."""
    base: dict[str, object] = {
        "char_start": 0,
        "char_end": 2,
        "mention_text": "猫猫",
        "raw_label": "PER",
        "canonical_label": "Person",
        "entity_type": "Person",
    }
    base.update(overrides)
    return base


def _declaration(**overrides: object) -> dict[str, object]:
    return _entry(**overrides)


def _dict_envelope(
    entries: list[dict[str, object]] | None = None, **meta: object
) -> dict[str, object]:
    envelope: dict[str, object] = {
        "extractor_id": "supplementary",
        "extractor_version": "dict-1.0.0",
        "schema_version": "e2b-dict-schema-1",
        "segmentation_version": "seg-1",
        "label_map_digest": _LABEL_MAP_DIGEST,
        "entries": [_entry()] if entries is None else entries,
    }
    envelope.update(meta)
    return envelope


def _fm_envelope(
    mentions: list[dict[str, object]] | None = None, **meta: object
) -> dict[str, object]:
    envelope: dict[str, object] = {
        "extractor_id": "supplementary",
        "extractor_version": "fm-1.0.0",
        "schema_version": "e2b-fm-schema-1",
        "segmentation_version": "seg-1",
        "label_map_digest": _LABEL_MAP_DIGEST,
        "title": "猫猫公司",
        "aliases": ["猫猫", "别名"],
        "mentions": [_declaration()] if mentions is None else mentions,
    }
    envelope.update(meta)
    return envelope


def _module_imported_names(module: Any) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_supplementary_functions_exported_from_entity_facade() -> None:
    import llamaindex_runtime.entity as entity

    assert entity.load_dictionary_candidates is load_dictionary_candidates
    assert entity.frontmatter_declared_candidates is frontmatter_declared_candidates


def test_loader_signatures_are_frozen() -> None:
    dictionary_params = inspect.signature(load_dictionary_candidates).parameters
    assert list(dictionary_params) == ["dictionary", "span"]
    frontmatter_params = inspect.signature(frontmatter_declared_candidates).parameters
    assert list(frontmatter_params) == ["frontmatter", "span"]


def test_load_dictionary_candidates_returns_frozen_mention_candidates() -> None:
    candidates = load_dictionary_candidates(_dict_envelope(), _corpus_input())
    assert isinstance(candidates, list)
    assert all(isinstance(candidate, MentionCandidate) for candidate in candidates)


def test_frontmatter_declared_candidates_returns_frozen_mention_candidates() -> None:
    candidates = frontmatter_declared_candidates(_fm_envelope(), _corpus_input())
    assert isinstance(candidates, list)
    assert all(isinstance(candidate, MentionCandidate) for candidate in candidates)


def test_empty_dictionary_entries_yield_no_candidates() -> None:
    assert load_dictionary_candidates(_dict_envelope(entries=[]), _corpus_input()) == []


def test_empty_frontmatter_mentions_yield_no_candidates() -> None:
    assert frontmatter_declared_candidates(_fm_envelope(mentions=[]), _corpus_input()) == []


# ---------------------------------------------------------------------------
# Dictionary candidate projection
# ---------------------------------------------------------------------------


def test_dictionary_candidate_carries_full_corpus_identity_from_span() -> None:
    span = _corpus_input(
        normalized_text="猫猫",
        projection={"document_char_start": 0, "document_char_end": 2},
    )
    candidate = load_dictionary_candidates(
        _dict_envelope(entries=[_entry(char_start=0, char_end=2, mention_text="猫猫")]),
        span,
    )[0]
    assert candidate.input_kind == "corpus_span"
    assert candidate.input_id == span.span_id == _SPAN_ID
    assert candidate.span_id == span.span_id
    assert candidate.input_revision == span.document_revision == "abc-v2"
    assert candidate.document_revision == span.document_revision
    assert candidate.document_id == span.document_id
    assert candidate.version_id == span.version_id
    assert candidate.segment_id is None
    assert candidate.normalized_text == span.normalized_text
    assert candidate.normalization_version == span.normalization_version
    assert dict(candidate.projection) == dict(span.projection)


def test_dictionary_candidate_uses_envelope_provenance_not_span() -> None:
    span = _corpus_input()  # normalization_version == "norm-1"
    candidate = load_dictionary_candidates(
        _dict_envelope(
            extractor_id="supplementary",
            extractor_version="dict-1.0.0",
            schema_version="e2b-dict-schema-1",
            segmentation_version="seg-1",
            label_map_digest="c" * 64,
        ),
        span,
    )[0]
    assert candidate.extractor_id == "supplementary"
    assert candidate.extractor_version == "dict-1.0.0"
    assert candidate.schema_version == "e2b-dict-schema-1"
    assert candidate.segmentation_version == "seg-1"
    assert candidate.label_map_digest == "c" * 64
    # normalization_version is inherited from the span; the envelope supplies
    # the schema/segmentation/label-map/extractor provenance the span lacks.
    assert candidate.normalization_version == span.normalization_version == "norm-1"
    assert candidate.segmentation_version != span.normalization_version


def test_dictionary_candidate_attribution_and_marker_confidence() -> None:
    candidate = load_dictionary_candidates(_dict_envelope(), _corpus_input())[0]
    assert candidate.source == "dictionary"
    assert candidate.confidence_kind == "dictionary_exact"
    assert candidate.confidence == 1.0  # marker only, never a calibrated probability
    assert candidate.raw_label == "PER"
    assert candidate.canonical_label == "Person"
    assert candidate.entity_type == "Person"
    assert candidate.mention_text == "猫猫"
    assert candidate.char_start == 0
    assert candidate.char_end == 2
    assert candidate.model_id is None
    assert candidate.model_revision is None
    assert candidate.artifact_digest is None
    assert candidate.runtime_compatibility_id is None


# ---------------------------------------------------------------------------
# Coordinate discipline (shared by both loaders)
# ---------------------------------------------------------------------------


def test_dictionary_offsets_are_span_local_code_points() -> None:
    span = _corpus_input(normalized_text="北京和北京今天开会")
    candidates = load_dictionary_candidates(
        _dict_envelope(
            entries=[
                _entry(
                    char_start=0,
                    char_end=2,
                    mention_text="北京",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
                _entry(
                    char_start=3,
                    char_end=5,
                    mention_text="北京",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
            ]
        ),
        span,
    )
    assert len(candidates) == 2
    assert candidates[0].char_start == 0
    assert candidates[0].char_end == 2
    assert candidates[1].char_start == 3
    assert candidates[1].char_end == 5
    assert span.normalized_text[0:2] == "北京"
    assert span.normalized_text[3:5] == "北京"
    # Duplicate mention text at distinct explicit coordinates stays distinct.
    assert candidates[0].mention_text == candidates[1].mention_text == "北京"
    assert candidates[0].char_start != candidates[1].char_start


def test_dictionary_offsets_count_unicode_code_points_not_bytes() -> None:
    span = _corpus_input(normalized_text="😀猫😀")
    assert len(span.normalized_text) == 3  # astral emoji == one code point
    candidate = load_dictionary_candidates(
        _dict_envelope(entries=[_entry(char_start=0, char_end=2, mention_text="😀猫")]),
        span,
    )[0]
    assert span.normalized_text[0:2] == "😀猫"
    assert candidate.mention_text == "😀猫"


def test_dictionary_slice_back_invariant_holds_for_every_candidate() -> None:
    candidates = load_dictionary_candidates(
        _dict_envelope(
            entries=[
                _entry(char_start=0, char_end=2, mention_text="猫猫"),
                _entry(
                    char_start=2,
                    char_end=4,
                    mention_text="今天",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
                _entry(
                    char_start=9,
                    char_end=11,
                    mention_text="紧张",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
            ]
        ),
        _corpus_input(),
    )
    for candidate in candidates:
        assert (
            0 <= candidate.char_start < candidate.char_end <= len(candidate.normalized_text)
        )
        assert (
            candidate.normalized_text[candidate.char_start : candidate.char_end]
            == candidate.mention_text
        )


def test_dictionary_slice_mismatch_fails_closed_even_when_text_appears_elsewhere() -> None:
    # "开会" appears at [4,6) but the entry explicitly claims [0,2). A loader
    # that locates text with find/index/search would silently recover; the
    # frozen contract requires hard slice-back and fail-closed rejection.
    with pytest.raises(DictionarySourceError):
        load_dictionary_candidates(
            _dict_envelope(entries=[_entry(char_start=0, char_end=2, mention_text="开会")]),
            _corpus_input(),
        )


@pytest.mark.parametrize(
    "entry",
    [
        {"char_start": -1, "char_end": 2},
        {"char_start": 2, "char_end": 1},
        {"char_start": 1, "char_end": 1},
        {"char_start": 0, "char_end": 12},  # end beyond len(normalized_text)
        {"char_start": True, "char_end": 2},  # bool is not an int coordinate
        {"char_start": "0", "char_end": 2},
        {"char_start": 0, "char_end": 2.0},
        {"char_start": 0, "char_end": 2, "mention_text": ""},
        {"char_start": 0, "char_end": 2, "mention_text": "狗狗"},  # slice mismatch
    ],
)
def test_dictionary_malformed_or_out_of_range_coordinates_fail_closed(
    entry: dict[str, object],
) -> None:
    with pytest.raises(DictionarySourceError):
        load_dictionary_candidates(
            _dict_envelope(entries=[_entry(**entry)]), _corpus_input()
        )


# ---------------------------------------------------------------------------
# Dictionary envelope / metadata fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "meta",
    [
        {"extractor_id": ""},
        {"extractor_id": None},
        {"extractor_id": "domain-dictionary"},  # != frozen "supplementary"
        {"extractor_id": "frontmatter-supplement"},  # != frozen "supplementary"
        {"extractor_version": ""},
        {"schema_version": ""},
        {"segmentation_version": ""},
        {"label_map_digest": ""},
        {"label_map_digest": "xyz"},
        {"label_map_digest": "A" * 64},  # uppercase is not lowercase hex
        {"label_map_digest": "b" * 63},
    ],
)
def test_dictionary_envelope_malformed_provenance_fails_closed(
    meta: dict[str, object],
) -> None:
    with pytest.raises(DictionarySourceError):
        load_dictionary_candidates(_dict_envelope(**meta), _corpus_input())


@pytest.mark.parametrize(
    "envelope",
    [
        {},  # missing all provenance
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
        },  # no entries key
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
            "entries": "not-a-list",
        },
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
            "entries": [42],
        },
    ],
)
def test_dictionary_envelope_missing_or_malformed_entries_fails_closed(
    envelope: dict[str, object],
) -> None:
    with pytest.raises(DictionarySourceError):
        load_dictionary_candidates(envelope, _corpus_input())


def test_dictionary_loader_rejects_query_input() -> None:
    with pytest.raises(DictionarySourceError):
        load_dictionary_candidates(_dict_envelope(), _query_input())


def test_dictionary_loader_does_not_mutate_envelope_or_span() -> None:
    envelope = _dict_envelope(
        entries=[_entry(), _entry(char_start=2, char_end=4, mention_text="今天")]
    )
    span = _corpus_input()
    snapshot = copy.deepcopy(envelope)
    candidates = load_dictionary_candidates(envelope, span)
    assert candidates
    assert envelope == snapshot
    assert span.input_revision == "abc-v2"
    assert span.normalized_text == _NORMALIZED


# ---------------------------------------------------------------------------
# Frontmatter candidate projection
# ---------------------------------------------------------------------------


def test_frontmatter_candidate_attribution_and_projection() -> None:
    span = _corpus_input()
    envelope = _fm_envelope(
        mentions=[_declaration(char_start=0, char_end=2, mention_text="猫猫")]
    )
    candidate = frontmatter_declared_candidates(envelope, span)[0]
    assert candidate.source == "frontmatter"
    assert candidate.confidence_kind == "frontmatter_declared"
    assert candidate.confidence == 1.0  # declaration marker, never a probability
    assert candidate.input_kind == "corpus_span"
    assert candidate.input_id == span.span_id
    assert candidate.span_id == span.span_id
    assert candidate.input_revision == span.document_revision
    assert candidate.segment_id is None
    assert candidate.normalization_version == span.normalization_version
    assert candidate.extractor_id == "supplementary"
    assert candidate.extractor_version == "fm-1.0.0"
    assert candidate.schema_version == "e2b-fm-schema-1"
    assert candidate.segmentation_version == "seg-1"
    assert candidate.label_map_digest == _LABEL_MAP_DIGEST
    assert candidate.model_id is None
    assert candidate.model_revision is None
    assert candidate.artifact_digest is None
    assert candidate.runtime_compatibility_id is None


def test_frontmatter_candidate_copies_span_projection() -> None:
    span = _corpus_input(projection={"document_char_start": 0, "document_char_end": 2})
    candidate = frontmatter_declared_candidates(_fm_envelope(), span)[0]
    assert dict(candidate.projection) == dict(span.projection)


def test_frontmatter_candidates_come_only_from_explicit_mentions() -> None:
    # title/aliases contain entity-like text but must never be scanned.
    envelope = _fm_envelope(
        mentions=[],
        title="猫猫今天开会议程很紧张",
        aliases=["猫猫", "今天", "紧张"],
    )
    assert frontmatter_declared_candidates(envelope, _corpus_input()) == []


def test_frontmatter_ignores_title_and_aliases_when_mentions_exist() -> None:
    envelope = _fm_envelope(
        mentions=[_declaration(char_start=0, char_end=2, mention_text="猫猫")],
        title="猫猫公司",
        aliases=["猫猫", "今天"],
    )
    candidates = frontmatter_declared_candidates(envelope, _corpus_input())
    assert len(candidates) == 1
    assert candidates[0].mention_text == "猫猫"
    assert candidates[0].char_start == 0
    assert candidates[0].char_end == 2


def test_frontmatter_duplicate_mention_text_at_distinct_coordinates_stays_distinct() -> None:
    span = _corpus_input(normalized_text="北京和北京")
    candidates = frontmatter_declared_candidates(
        _fm_envelope(
            mentions=[
                _declaration(
                    char_start=0,
                    char_end=2,
                    mention_text="北京",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
                _declaration(
                    char_start=3,
                    char_end=5,
                    mention_text="北京",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
            ]
        ),
        span,
    )
    assert len(candidates) == 2
    assert candidates[0].char_start != candidates[1].char_start
    assert candidates[0].mention_text == candidates[1].mention_text == "北京"


def test_frontmatter_slice_back_invariant_holds_for_every_candidate() -> None:
    candidates = frontmatter_declared_candidates(
        _fm_envelope(
            mentions=[
                _declaration(char_start=0, char_end=2, mention_text="猫猫"),
                _declaration(
                    char_start=9,
                    char_end=11,
                    mention_text="紧张",
                    raw_label="LOC",
                    canonical_label="Location",
                    entity_type="Location",
                ),
            ]
        ),
        _corpus_input(),
    )
    for candidate in candidates:
        assert (
            candidate.normalized_text[candidate.char_start : candidate.char_end]
            == candidate.mention_text
        )


# ---------------------------------------------------------------------------
# Frontmatter fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declaration",
    [
        {"char_start": -1, "char_end": 2},
        {"char_start": 2, "char_end": 1},
        {"char_start": 0, "char_end": 99},  # end beyond len(normalized_text)
        {"char_start": 0, "char_end": 2, "mention_text": "开会"},  # appears at [4,6), not [0,2)
        {"char_start": 0, "char_end": 2, "mention_text": ""},
        {"char_start": "0", "char_end": 2},
        {"char_start": 0, "char_end": 2.0},
        {"char_start": 0, "char_end": 2, "raw_label": ""},
        {"char_start": 0, "char_end": 2, "canonical_label": ""},
        {"char_start": 0, "char_end": 2, "entity_type": ""},
    ],
)
def test_frontmatter_malformed_declaration_fails_closed(
    declaration: dict[str, object],
) -> None:
    with pytest.raises(FrontmatterSourceError):
        frontmatter_declared_candidates(
            _fm_envelope(mentions=[_declaration(**declaration)]), _corpus_input()
        )


@pytest.mark.parametrize(
    "meta",
    [
        {"extractor_id": ""},
        {"extractor_id": "domain-dictionary"},  # != frozen "supplementary"
        {"extractor_id": "frontmatter-supplement"},  # != frozen "supplementary"
        {"extractor_version": ""},
        {"schema_version": ""},
        {"segmentation_version": ""},
        {"label_map_digest": "A" * 64},
        {"label_map_digest": "b" * 63},
    ],
)
def test_frontmatter_envelope_malformed_provenance_fails_closed(
    meta: dict[str, object],
) -> None:
    with pytest.raises(FrontmatterSourceError):
        frontmatter_declared_candidates(_fm_envelope(**meta), _corpus_input())


@pytest.mark.parametrize(
    "envelope",
    [
        {},  # missing all provenance
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
        },  # no mentions key
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
            "mentions": "not-a-list",
        },
        {
            "extractor_id": "x",
            "extractor_version": "y",
            "schema_version": "z",
            "segmentation_version": "s",
            "label_map_digest": "b" * 64,
            "mentions": ["x"],
        },
    ],
)
def test_frontmatter_envelope_missing_or_malformed_mentions_fails_closed(
    envelope: dict[str, object],
) -> None:
    with pytest.raises(FrontmatterSourceError):
        frontmatter_declared_candidates(envelope, _corpus_input())


def test_frontmatter_loader_rejects_query_input() -> None:
    with pytest.raises(FrontmatterSourceError):
        frontmatter_declared_candidates(_fm_envelope(), _query_input())


def test_frontmatter_loader_does_not_mutate_envelope_or_span() -> None:
    envelope = _fm_envelope(mentions=[_declaration(), _declaration(char_start=2, char_end=4, mention_text="今天")])
    span = _corpus_input()
    snapshot = copy.deepcopy(envelope)
    frontmatter_declared_candidates(envelope, span)
    assert envelope == snapshot
    assert span.input_revision == "abc-v2"
    assert span.normalized_text == _NORMALIZED


# ---------------------------------------------------------------------------
# Import boundary: no heavy/persistence/network/model/LLM surface
# ---------------------------------------------------------------------------


def test_supplementary_imports_never_pull_heavy_dependencies() -> None:
    for heavy in ("modelscope", "torch", "jieba"):
        assert heavy not in sys.modules, (
            f"dictionary/frontmatter supplements must not import {heavy}"
        )


def test_supplementary_modules_stay_pure_stdlib_plus_entity_contracts() -> None:
    for module in (dictionary_loader_module, frontmatter_supplement_module):
        for name in _module_imported_names(module):
            assert not any(marker in name for marker in _FORBIDDEN_IMPORT_MARKERS), (
                f"{module.__name__} must not import {name!r}"
            )


def test_supplementary_modules_never_recover_coordinates_via_substring_search() -> None:
    for module in (dictionary_loader_module, frontmatter_supplement_module):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("find", "index", "rfind", "rindex", "search"), (
                    f"{module.__name__} must not locate mention text with {node.func.attr}"
                )
