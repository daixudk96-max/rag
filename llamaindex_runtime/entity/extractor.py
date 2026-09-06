"""E2b EntityExtractor composition (Phase 16-10).

Pure orchestration over pre-bound injected seams. This module imports only
the standard library plus ``.contracts``; it never imports config, a
model/tokenizer package, a database/network layer, or any generative
assistant, and it performs zero generative-LLM work (R-OKF-04).

Public contract
---------------
- ``EntityExtractor(adapter, segmenter, merger, resolver, *, extractor_id,
  extractor_version, schema_version)`` with
  ``extract(inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]``.
  The public return is a plain ``list`` -- never a tuple and never a public
  wrapper DTO.
- ``build_entity_extractor(rag_entity_extractor, *, factory) ->
  EntityExtractor | None`` is a lazy registry gate. ``off`` returns ``None``
  without calling ``factory``; any other value fails closed (the former
  ``raner`` path was retired with RaNER in Phase 19).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .contracts import (
    CorpusSpanInput,
    ExtractionInput,
    MentionCandidate,
    QueryTextInput,
)


def _require_nonempty(value: object, name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _validate_inputs(inputs: object) -> None:
    """Fail fast on a non-Sequence, empty, or mixed-non-ExtractionInput input."""
    if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes, bytearray)):
        raise ValueError("inputs must be a Sequence of ExtractionInput")
    if len(inputs) == 0:  # type: ignore[arg-type]
        raise ValueError("at least one ExtractionInput is required")
    for index, entry in enumerate(inputs):  # type: ignore[arg-type]
        if not isinstance(entry, (CorpusSpanInput, QueryTextInput)):
            raise ValueError(
                f"inputs[{index}] must be a CorpusSpanInput or QueryTextInput"
            )


class EntityExtractor:
    """Frozen-ish composition that dispatches corpus and query inputs.

    The injected seams are pre-bound / pre-configured so the extractor never
    invents model, tokenizer, segmentation, merger, or resolution parameters:

    - ``adapter(input_)`` is a per-input factory mirroring per-parent
      adapter construction; the returned composition exposes
      ``extract_segment(segment, *, extractor_id, extractor_version,
      schema_version)`` and (corpus-only) ``supplement()``.
    - ``segmenter(input_)`` is a pre-bound union dispatcher returning segments.
    - ``merger(candidates)`` and ``resolver(selected)`` are pre-bound callables
      exposing ``.selected`` and ``.resolved/.pending`` respectively.

    Query inputs flow through the same adapter/segmenter/merge/resolve
    orchestration; corpus-only supplements never run for a query input.
    """

    def __init__(
        self,
        adapter: Callable[[ExtractionInput], Any],
        segmenter: Callable[[ExtractionInput], Sequence[Any]],
        merger: Callable[[Sequence[MentionCandidate]], Any],
        resolver: Callable[[Sequence[MentionCandidate]], Any],
        *,
        extractor_id: str,
        extractor_version: str,
        schema_version: str,
    ) -> None:
        _require_nonempty(extractor_id, "extractor_id")
        _require_nonempty(extractor_version, "extractor_version")
        _require_nonempty(schema_version, "schema_version")
        self._adapter = adapter
        self._segmenter = segmenter
        self._merger = merger
        self._resolver = resolver
        self._extractor_id = extractor_id
        self._extractor_version = extractor_version
        self._schema_version = schema_version

    def extract(self, inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]:
        """Prevalidate, then run the shared deterministic pipeline."""
        _validate_inputs(inputs)

        candidates: list[MentionCandidate] = []
        for entry in inputs:
            composition = self._adapter(entry)
            for segment in self._segmenter(entry):
                candidates.extend(
                    composition.extract_segment(
                        segment,
                        extractor_id=self._extractor_id,
                        extractor_version=self._extractor_version,
                        schema_version=self._schema_version,
                    )
                )
            if isinstance(entry, CorpusSpanInput):
                candidates.extend(composition.supplement())

        merged = self._merger(candidates)
        resolution = self._resolver(merged.selected)

        return [
            decision.candidate
            for decision in (*resolution.resolved, *resolution.pending)
        ]


def build_entity_extractor(
    rag_entity_extractor: str,
    *,
    factory: Callable[[], EntityExtractor],
) -> EntityExtractor | None:
    """Registry gate: 'off' builds nothing; anything else fails closed."""
    if rag_entity_extractor == "off":
        return None
    raise ValueError(f"unsupported rag_entity_extractor: {rag_entity_extractor!r}")


__all__ = ["EntityExtractor", "build_entity_extractor"]
