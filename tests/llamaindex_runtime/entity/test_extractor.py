"""RED extractor tests for the E2b raw-corpus entity layer (Phase 16-10).

Public contract (authoritative override)
- ``EntityExtractor(adapter, segmenter, merger, resolver, *, extractor_id,
  extractor_version, schema_version)`` with
  ``extract(inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]``.
  The public return is a plain ``list`` -- never a tuple and never a public
  wrapper DTO.
- ``build_entity_extractor(rag_entity_extractor, *, factory) ->
  EntityExtractor | None`` is a LAZY registry gate: it consumes a
  config-validated switch value (``RuntimeSettings.rag_entity_extractor``;
  ``VALID_ENTITY_EXTRACTORS == {"off"}``). ``off`` returns ``None``
  without calling ``factory`` (proven by a raising spy), so the default-off
  path builds nothing and pulls in no heavy dependency. Any other value
  fails closed (the former ``raner`` path was retired with RaNER in Phase 19).

Seam shapes: pre-bound / pre-configured injected callables (no invented params)
-----------------------------------------------------------------------------
The frozen constructor is only ``(adapter, segmenter, merger, resolver,
extractor_id, extractor_version, schema_version)``. Everything the real raw
APIs would need (``segment_text`` max_tokens/tokenizer/segmentation_version,
``merge_mentions`` merger_version, ``resolve_candidates``
entities/aliases/priority_version, ``adapter.extract_segment``
model/tokenizer/model provenance) is therefore PRE-BOUND inside the injected
callables. ``EntityExtractor`` performs orchestration only and never invents
version/authority/model parameters:

- ``segmenter(input_) -> tuple[SegmentLike, ...]`` is a pre-configured union
  dispatcher. The corpus branch may wrap ``functools.partial(segment_text,
  ...)``; the query branch generates request-scoped query segments. It is
  called with the input only.
- ``adapter(input_) -> CompositionWrapper`` is a pre-configured per-input
  factory (mirroring per-parent adapter construction). The
  wrapper delegates model extraction to an adapter-shaped
  ``extract_segment(segment, *, extractor_id, extractor_version,
  schema_version)`` with model/tokenizer/model provenance pre-bound; the
  extractor passes ONLY the frozen provenance. Supplements belong to the
  wrapper/composition (not to the adapter itself) and are corpus-only.
- ``merger(candidates) -> .selected`` and ``resolver(selected) ->
  .resolved/.pending`` are pre-bound callables; the extractor calls them with
  the candidate sequence only and never supplies merger_version /
  entities / aliases / priority_version.

Frozen D2 / plan boundaries
- Corpus and query share the SAME union segmenter dispatcher, adapter factory,
  merge, and resolve orchestration in one mixed ``extract()``.
- Frontmatter/dictionary supplements are ALWAYS corpus-only: the supplement
  seam never runs for a query input and query results never carry a
  ``frontmatter`` source. Query supplementation (if any) must be a
  request-scoped pure seam, never a misinvocation of the corpus-only loaders.
- Query candidates are request-scoped with hard-zero durable persistence
  surface; ``EntityExtractor`` exposes no persistence surface.
- Zero generative-LLM baseline (R-OKF-04): module boundary proven by static
  source guards (no LLM/import reference, no heavy imports) plus an import
  guard (no modelscope/torch/jieba/sentencepiece in ``sys.modules``). Pipeline
  behavior is exercised only through injected pure fakes.

RED only: ``llamaindex_runtime/entity/extractor.py`` does not exist yet, so
collection fails with ModuleNotFoundError. No production file is touched.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

# The genuine RED: collection fails because extractor.py does not exist yet.
from llamaindex_runtime.entity.extractor import EntityExtractor, build_entity_extractor
import llamaindex_runtime.entity.extractor as extractor

from llamaindex_runtime.config import RuntimeSettings
from llamaindex_runtime.entity.contracts import (
    CorpusSpanInput,
    MentionCandidate,
    QueryTextInput,
)

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_QUERY_ID = str(UUID(int=10))
_CORPUS_NORMALIZED = "猫猫今天开会"
_QUERY_NORMALIZED = "猫猫是什么"
_CORPUS_REVISION = "abc-v2"
_QUERY_REVISION = "query-v7"
_EXTRACTOR_ID = "raner-test"
_EXTRACTOR_VERSION = "9.9.9"
_SCHEMA_VERSION = "e2b-schema-test"
_MISSING = "<not-propagated>"
_MODEL_ID = "iic/raner-test"
_MODEL_REVISION = "rev-1"
_ARTIFACT_DIGEST = "a" * 64
_LABEL_MAP_DIGEST = "b" * 64

_NO_PERSISTENCE_NAMES = (
    "save",
    "write",
    "insert",
    "upsert",
    "delete",
    "commit",
    "rollback",
    "repository",
    "connection",
    "cursor",
    "execute",
    "persist",
    "materialize",
)
_DURABLE_STORE_NAMES = (
    "entity_mentions",
    "entity_aliases",
    "entity_merge_log",
    "node_entity_links",
    "chunk_entity_links",
)

# Zero-LLM / zero-heavy module-boundary guard tokens (test_raner_adapter.py).
_HEAVY_IMPORTS = (
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
)
_LLM_REFS = (
    "import openai",
    "from openai",
    "import anthropic",
    "from anthropic",
    "from llamaindex_runtime.llm",
    "import llamaindex_runtime.llm",
    "FunctionAgent",
    "get_llm(",
)


def _corpus_input(**overrides: object) -> CorpusSpanInput:
    base: dict[str, object] = {
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "span_id": _SPAN_ID,
        "document_revision": _CORPUS_REVISION,
        "input_revision": _CORPUS_REVISION,
        "normalized_text": _CORPUS_NORMALIZED,
        "normalization_version": "norm-1",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return CorpusSpanInput(**base)  # type: ignore[arg-type]


def _query_input(**overrides: object) -> QueryTextInput:
    base: dict[str, object] = {
        "query_id": _QUERY_ID,
        "query_revision": _QUERY_REVISION,
        "input_revision": _QUERY_REVISION,
        "normalized_text": _QUERY_NORMALIZED,
        "normalization_version": "norm-1",
    }
    base.update(overrides)
    return QueryTextInput(**base)  # type: ignore[arg-type]


def _model_candidate(input_: object, prov: dict[str, str]) -> MentionCandidate:
    """Variant-specific model candidate (corpus carries projection, query not)."""
    is_corpus = isinstance(input_, CorpusSpanInput)
    if not is_corpus and not isinstance(input_, QueryTextInput):
        raise AssertionError("non-ExtractionInput reached the candidate builder")
    normalized = input_.normalized_text  # type: ignore[union-attr]
    return MentionCandidate(
        input_id=input_.input_id,  # type: ignore[union-attr]
        input_kind=input_.input_kind,  # type: ignore[union-attr]
        input_revision=input_.input_revision,  # type: ignore[union-attr]
        normalized_text=normalized,
        span_id=input_.span_id if is_corpus else None,  # type: ignore[union-attr]
        segment_id="seg-1" if is_corpus else None,
        char_start=0,
        char_end=2,
        mention_text=normalized[0:2],
        raw_label="PER",
        canonical_label="Person",
        entity_type="Person",
        confidence=None,
        confidence_kind="unavailable",
        source="model",
        extractor_id=prov.get("extractor_id", _MISSING),
        extractor_version=prov.get("extractor_version", _MISSING),
        model_id=_MODEL_ID,
        model_revision=_MODEL_REVISION,
        artifact_digest=_ARTIFACT_DIGEST,
        schema_version=prov.get("schema_version", _MISSING),
        normalization_version=input_.normalization_version,  # type: ignore[union-attr]
        segmentation_version="seg-1",
        label_map_digest=_LABEL_MAP_DIGEST,
        runtime_compatibility_id=None,
        document_id=input_.document_id if is_corpus else None,  # type: ignore[union-attr]
        version_id=input_.version_id if is_corpus else None,  # type: ignore[union-attr]
        document_revision=input_.document_revision if is_corpus else None,  # type: ignore[union-attr]
        projection=input_.projection if is_corpus else None,  # type: ignore[union-attr]
    )


def _supplement_candidate(span: CorpusSpanInput) -> MentionCandidate:
    """Dictionary-source corpus candidate with all model fields None."""
    return MentionCandidate(
        input_id=span.span_id,
        input_kind="corpus_span",
        input_revision=span.input_revision,
        normalized_text=span.normalized_text,
        span_id=span.span_id,
        segment_id=None,
        char_start=2,
        char_end=4,
        mention_text=span.normalized_text[2:4],
        raw_label="DATE",
        canonical_label="Date",
        entity_type="Date",
        confidence=1.0,
        confidence_kind="dictionary_exact",
        source="dictionary",
        extractor_id="supplementary",
        extractor_version="1.0.0",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        schema_version="e2b-schema-1",
        normalization_version=span.normalization_version,
        segmentation_version="seg-1",
        label_map_digest=_LABEL_MAP_DIGEST,
        runtime_compatibility_id=None,
        document_id=span.document_id,
        version_id=span.version_id,
        document_revision=span.document_revision,
        projection=span.projection,
    )


def _settings(*, rag_entity_extractor: str) -> RuntimeSettings:
    return RuntimeSettings(
        database_url="postgresql://red-test-local",
        rag_entity_extractor=rag_entity_extractor,
    )


# ---------------------------------------------------------------------------
# Pre-bound fake seams: the extractor supplies ONLY orchestration inputs
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, parent_id: str, start: int, end: int, text: str) -> None:
        self.parent_span_id = parent_id
        self.start = start
        self.end = end
        self.text = text


class _FakeSegmenter:
    """Pre-configured union dispatcher; called as ``segmenter(input_)``.

    Mirrors a dispatcher whose corpus branch may wrap ``segment_text`` with
    pre-bound tokenizer/max_tokens/segmentation_version and whose query branch
    generates request-scoped query segments. The extractor must NOT pass any
    segmentation configuration.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.inputs_seen: list[object] = []

    def __call__(self, input_: object) -> tuple[_FakeSegment, ...]:
        self.calls += 1
        self.inputs_seen.append(input_)
        if isinstance(input_, CorpusSpanInput):
            parent_id = input_.span_id
        elif isinstance(input_, QueryTextInput):
            parent_id = input_.query_id
        else:
            raise AssertionError("segmenter seam received a non-ExtractionInput")
        text = input_.normalized_text  # type: ignore[union-attr]
        return (_FakeSegment(parent_id, 0, len(text), text),)


class _SpanPipeline:
    """Per-input composition wrapper (mirrors ``RaNERAdapter(parent)`` usage).

    Model/tokenizer/model provenance are PRE-BOUND; ``extract_segment`` accepts
    only the frozen extractor provenance so the extractor can never invent
    model parameters. ``supplement`` is corpus-only and belongs to the
    wrapper/composition, not to ``RaNERAdapter`` itself.
    """

    def __init__(self, input_: object) -> None:
        self.input_ = input_
        self.extract_segment_calls = 0
        self.supplement_calls = 0
        self.seen_provenance: list[dict[str, str]] = []

    def extract_segment(
        self,
        segment: object,
        *,
        extractor_id: str,
        extractor_version: str,
        schema_version: str,
    ) -> list[MentionCandidate]:
        self.extract_segment_calls += 1
        self.seen_provenance.append(
            {
                "extractor_id": extractor_id,
                "extractor_version": extractor_version,
                "schema_version": schema_version,
            }
        )
        return [
            _model_candidate(
                self.input_,
                {
                    "extractor_id": extractor_id,
                    "extractor_version": extractor_version,
                    "schema_version": schema_version,
                },
            )
        ]

    def supplement(self) -> list[MentionCandidate]:
        self.supplement_calls += 1
        if not isinstance(self.input_, CorpusSpanInput):
            raise AssertionError(
                "corpus-only supplement seam must never run for a query input"
            )
        return [_supplement_candidate(self.input_)]


class _AdapterCompositionFactory:
    """Pre-configured ``adapter(input_)`` factory (per-parent composition)."""

    def __init__(self) -> None:
        self.factory_calls = 0
        self.pipelines: list[_SpanPipeline] = []
        self.inputs_seen: list[object] = []

    def __call__(self, input_: object) -> _SpanPipeline:
        self.factory_calls += 1
        self.inputs_seen.append(input_)
        pipeline = _SpanPipeline(input_)
        self.pipelines.append(pipeline)
        return pipeline


class _FakeMerged:
    """Mirrors ``MergedMentions``: exposes only the ``selected`` surface."""

    def __init__(self, selected: list[MentionCandidate]) -> None:
        self.selected: tuple[MentionCandidate, ...] = tuple(selected)


class _FakeMerger:
    """Pre-bound callable; called as ``merger(candidates)`` (no version arg)."""

    def __init__(self) -> None:
        self.calls = 0
        self.candidate_inputs: list[list[MentionCandidate]] = []

    def __call__(self, candidates: object) -> _FakeMerged:
        self.calls += 1
        candidate_list = (
            list(candidates) if not isinstance(candidates, list) else candidates
        )
        self.candidate_inputs.append(list(candidate_list))
        return _FakeMerged(candidate_list)


class _FakeDecision:
    """Mirrors ``ResolutionDecision``: candidate + entity_id."""

    def __init__(self, candidate: MentionCandidate) -> None:
        self.candidate = candidate
        self.entity_id: str | None = None


class _FakeResolution:
    """Mirrors ``ResolutionResult``: exposes only resolved/pending decisions."""

    def __init__(self, decisions: list[_FakeDecision]) -> None:
        self.resolved: tuple[_FakeDecision, ...] = tuple(
            decision for decision in decisions if decision.entity_id is not None
        )
        self.pending: tuple[_FakeDecision, ...] = tuple(
            decision for decision in decisions if decision.entity_id is None
        )


class _FakeResolver:
    """Pre-bound callable; called as ``resolver(selected)`` (no authority args)."""

    def __init__(self) -> None:
        self.calls = 0
        self.candidate_inputs: list[list[MentionCandidate]] = []

    def __call__(self, selected: object) -> _FakeResolution:
        self.calls += 1
        candidate_list = list(selected)  # type: ignore[arg-type]
        self.candidate_inputs.append(candidate_list)
        return _FakeResolution(
            [_FakeDecision(candidate) for candidate in candidate_list]
        )


class _FactorySpy:
    """Counting factory used by the lazy build gate."""

    def __init__(
        self, make: Callable[[], EntityExtractor | None] | None = None
    ) -> None:
        self.make = make if make is not None else (lambda: None)
        self.calls = 0

    def __call__(self) -> EntityExtractor | None:
        self.calls += 1
        return self.make()


def _make_seams() -> (
    tuple[_AdapterCompositionFactory, _FakeSegmenter, _FakeMerger, _FakeResolver]
):
    return (
        _AdapterCompositionFactory(),
        _FakeSegmenter(),
        _FakeMerger(),
        _FakeResolver(),
    )


def _build_extractor(
    adapter: _AdapterCompositionFactory,
    segmenter: _FakeSegmenter,
    merger: _FakeMerger,
    resolver: _FakeResolver,
) -> EntityExtractor:
    return EntityExtractor(
        adapter,
        segmenter,
        merger,
        resolver,
        extractor_id=_EXTRACTOR_ID,
        extractor_version=_EXTRACTOR_VERSION,
        schema_version=_SCHEMA_VERSION,
    )


class _FakeHarness:
    """Holds pre-bound seams plus the EntityExtractor built over them."""

    def __init__(self) -> None:
        self.adapter, self.segmenter, self.merger, self.resolver = _make_seams()
        self.extractor = _build_extractor(
            self.adapter, self.segmenter, self.merger, self.resolver
        )


def _signature(
    candidates: list[MentionCandidate],
) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (c.input_kind, c.input_revision, c.source, c.mention_text) for c in candidates
    )


def _assert_no_persistence_surface(value: object) -> None:
    for name in (*_NO_PERSISTENCE_NAMES, *_DURABLE_STORE_NAMES):
        assert not hasattr(value, name), f"{type(value).__name__} exposes {name}"


def _input_kind(value: object) -> str:
    if isinstance(value, CorpusSpanInput):
        return "corpus_span"
    if isinstance(value, QueryTextInput):
        return "query_text"
    raise AssertionError("unexpected non-ExtractionInput")


# ---------------------------------------------------------------------------
# Lazy build gate (registry + RAG_ENTITY_EXTRACTOR dispatch)
# ---------------------------------------------------------------------------


def test_valid_entity_extractors_are_reused_from_config() -> None:
    assert RuntimeSettings.VALID_ENTITY_EXTRACTORS == frozenset({"off"})


def test_build_off_returns_none_and_never_calls_factory() -> None:
    class _NeverFactory:
        def __call__(self) -> EntityExtractor:
            raise AssertionError(
                "factory must never run when rag_entity_extractor is 'off'"
            )

    result = build_entity_extractor(
        _settings(rag_entity_extractor="off").rag_entity_extractor,
        factory=_NeverFactory(),
    )

    assert result is None
    # The lazy gate built nothing and pulled in no heavy dependency.
    for name in ("modelscope", "torch", "jieba", "sentencepiece"):
        assert name not in sys.modules


def test_build_retired_raner_value_fails_closed() -> None:
    # RaNER was retired in Phase 19; the value must fail closed and the
    # factory must never run.
    class _NeverFactory:
        def __call__(self) -> EntityExtractor:
            raise AssertionError("factory must never run for a retired value")

    with pytest.raises(ValueError, match="unsupported rag_entity_extractor"):
        build_entity_extractor(
            "raner",
            factory=_NeverFactory(),
        )


# ---------------------------------------------------------------------------
# Mixed dispatch: one plain list, preserved identity/revision
# ---------------------------------------------------------------------------


def test_extract_mixed_sequence_returns_one_plain_list_with_preserved_kinds() -> None:
    harness = _FakeHarness()
    corpus = _corpus_input()
    query = _query_input()

    result = harness.extractor.extract([corpus, query])

    assert type(result) is list
    assert not isinstance(result, tuple)
    assert all(type(candidate) is MentionCandidate for candidate in result)

    corpus_candidates = [c for c in result if c.input_kind == "corpus_span"]
    query_candidates = [c for c in result if c.input_kind == "query_text"]
    assert len(corpus_candidates) == 2  # model + dictionary supplement
    assert len(query_candidates) == 1

    for candidate in corpus_candidates:
        assert candidate.input_revision == _CORPUS_REVISION
        assert candidate.input_revision == candidate.document_revision
        assert candidate.input_id == _SPAN_ID
        assert candidate.span_id == _SPAN_ID
        assert candidate.document_id == _DOCUMENT_ID
        assert candidate.version_id == _VERSION_ID
        assert candidate.projection is not None

    for candidate in query_candidates:
        assert candidate.input_revision == _QUERY_REVISION
        assert candidate.input_id == _QUERY_ID
        assert candidate.span_id is None
        assert candidate.segment_id is None
        assert candidate.document_id is None
        assert candidate.version_id is None
        assert candidate.document_revision is None
        assert candidate.projection is None


def test_extract_mixed_sequence_is_deterministic() -> None:
    harness = _FakeHarness()
    inputs = [_corpus_input(), _query_input()]

    assert _signature(harness.extractor.extract(inputs)) == _signature(
        harness.extractor.extract(inputs)
    )


# ---------------------------------------------------------------------------
# Shared orchestration: corpus and query through the same pre-bound seams
# ---------------------------------------------------------------------------


def test_shared_segmenter_adapter_merge_resolve_process_corpus_and_query() -> None:
    harness = _FakeHarness()
    harness.extractor.extract([_corpus_input(), _query_input()])

    # The SAME union segmenter dispatcher saw both kinds.
    segmenter_kinds = {_input_kind(seen) for seen in harness.segmenter.inputs_seen}
    assert segmenter_kinds == {"corpus_span", "query_text"}

    # The adapter factory (mirroring per-parent adapter construction) bound
    # one per-input composition wrapper for BOTH variants.
    assert harness.adapter.factory_calls == 2
    assert len(harness.adapter.pipelines) == 2

    # Merger and resolver each received candidates of both kinds in the SAME
    # deterministic orchestration (D2 / plan 16-10).
    merged_kinds = {
        c.input_kind for call in harness.merger.candidate_inputs for c in call
    }
    resolved_kinds = {
        c.input_kind for call in harness.resolver.candidate_inputs for c in call
    }
    assert merged_kinds == {"corpus_span", "query_text"}
    assert resolved_kinds == {"corpus_span", "query_text"}


def test_adapter_extract_segment_produces_variant_specific_candidates() -> None:
    harness = _FakeHarness()
    harness.extractor.extract([_corpus_input(), _query_input()])

    corpus_pipelines = [
        p for p in harness.adapter.pipelines if isinstance(p.input_, CorpusSpanInput)
    ]
    query_pipelines = [
        p for p in harness.adapter.pipelines if isinstance(p.input_, QueryTextInput)
    ]
    assert len(corpus_pipelines) == 1
    assert len(query_pipelines) == 1
    assert corpus_pipelines[0].extract_segment_calls == 1
    assert query_pipelines[0].extract_segment_calls == 1


def test_supplement_seam_is_corpus_only_frontmatter_never_for_query() -> None:
    harness = _FakeHarness()
    result = harness.extractor.extract([_corpus_input(), _query_input()])

    corpus_pipelines = [
        p for p in harness.adapter.pipelines if isinstance(p.input_, CorpusSpanInput)
    ]
    query_pipelines = [
        p for p in harness.adapter.pipelines if isinstance(p.input_, QueryTextInput)
    ]
    assert corpus_pipelines and query_pipelines
    for pipeline in corpus_pipelines:
        assert pipeline.supplement_calls >= 1
    # D2: supplements are ALWAYS corpus-only; query never misinvokes the
    # corpus-only loaders and never yields a frontmatter source.
    for pipeline in query_pipelines:
        assert pipeline.supplement_calls == 0

    assert not any(
        c.source == "frontmatter" and c.input_kind == "query_text" for c in result
    )
    assert any(c.source == "dictionary" for c in result)


# ---------------------------------------------------------------------------
# Fixed extractor provenance and source-specific provenance
# ---------------------------------------------------------------------------


def test_fixed_provenance_passed_to_adapter_seam_and_landing_on_model_candidates() -> (
    None
):
    harness = _FakeHarness()
    result = harness.extractor.extract([_corpus_input(), _query_input()])

    for pipeline in harness.adapter.pipelines:
        assert pipeline.extract_segment_calls >= 1
        for prov in pipeline.seen_provenance:
            assert prov == {
                "extractor_id": _EXTRACTOR_ID,
                "extractor_version": _EXTRACTOR_VERSION,
                "schema_version": _SCHEMA_VERSION,
            }

    model_candidates = [c for c in result if c.source == "model"]
    assert len(model_candidates) == 2
    for candidate in model_candidates:
        assert candidate.extractor_id == _EXTRACTOR_ID
        assert candidate.extractor_version == _EXTRACTOR_VERSION
        assert candidate.schema_version == _SCHEMA_VERSION


def test_model_candidates_carry_complete_model_provenance() -> None:
    harness = _FakeHarness()
    result = harness.extractor.extract([_corpus_input(), _query_input()])

    model_candidates = [c for c in result if c.source == "model"]
    assert len(model_candidates) == 2
    for candidate in model_candidates:
        assert candidate.model_id is not None
        assert candidate.model_revision is not None
        assert candidate.artifact_digest is not None


def test_non_model_candidates_carry_no_model_provenance() -> None:
    harness = _FakeHarness()
    result = harness.extractor.extract([_corpus_input(), _query_input()])

    non_model_candidates = [c for c in result if c.source != "model"]
    assert len(non_model_candidates) == 1
    for candidate in non_model_candidates:
        assert candidate.model_id is None
        assert candidate.model_revision is None
        assert candidate.artifact_digest is None
        assert candidate.runtime_compatibility_id is None


# ---------------------------------------------------------------------------
# Input validation: fail before any pipeline work
# ---------------------------------------------------------------------------


def test_empty_inputs_fail_before_any_pipeline_call() -> None:
    harness = _FakeHarness()

    with pytest.raises(ValueError):
        harness.extractor.extract([])

    assert harness.adapter.factory_calls == 0
    assert harness.segmenter.calls == 0
    assert harness.merger.calls == 0
    assert harness.resolver.calls == 0


def test_non_extraction_input_entry_fails_before_any_pipeline_call() -> None:
    harness = _FakeHarness()

    with pytest.raises(ValueError):
        harness.extractor.extract([_corpus_input(), "not-an-input", _query_input()])

    assert harness.adapter.factory_calls == 0
    assert harness.segmenter.calls == 0
    assert harness.merger.calls == 0
    assert harness.resolver.calls == 0


def test_non_extraction_input_types_fail_before_any_pipeline_call() -> None:
    for bad in (None, 42, b"bytes", {"not": "an input"}, object()):
        harness = _FakeHarness()
        with pytest.raises(ValueError):
            harness.extractor.extract([_corpus_input(), bad])
        assert harness.adapter.factory_calls == 0
        assert harness.resolver.calls == 0


# ---------------------------------------------------------------------------
# Query request-scoping: hard-zero durable persistence surface
# ---------------------------------------------------------------------------


def test_query_candidates_are_request_scoped_with_zero_persistence_surface() -> None:
    harness = _FakeHarness()
    result = harness.extractor.extract([_corpus_input(), _query_input()])

    query_candidates = [c for c in result if c.input_kind == "query_text"]
    assert len(query_candidates) == 1
    query_candidate = query_candidates[0]
    assert query_candidate.input_revision == _QUERY_REVISION
    _assert_no_persistence_surface(query_candidate)


def test_extractor_exposes_no_persistence_surface() -> None:
    harness = _FakeHarness()

    _assert_no_persistence_surface(harness.extractor)
    for name in (*_NO_PERSISTENCE_NAMES, *_DURABLE_STORE_NAMES):
        assert not hasattr(harness.extractor, name)


# ---------------------------------------------------------------------------
# Zero generative-LLM baseline: module-boundary guards (R-OKF-04)
# ---------------------------------------------------------------------------


def test_extractor_source_imports_no_heavy_dependencies() -> None:
    source = Path(extractor.__file__).read_text(encoding="utf-8")
    for forbidden in _HEAVY_IMPORTS:
        assert forbidden not in source, f"forbidden heavy import: {forbidden}"


def test_extractor_source_never_imports_or_invokes_generative_llm() -> None:
    source = Path(extractor.__file__).read_text(encoding="utf-8")
    for forbidden in _LLM_REFS:
        assert forbidden not in source, f"forbidden LLM reference: {forbidden}"


def test_importing_extractor_imports_no_heavy_dependencies() -> None:
    import llamaindex_runtime.entity.extractor  # noqa: F401

    for name in ("modelscope", "torch", "jieba", "sentencepiece"):
        assert name not in sys.modules, f"extractor must not import {name}"
