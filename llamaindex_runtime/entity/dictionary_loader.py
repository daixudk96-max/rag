"""Dictionary-exact supplementary candidate loader (Phase 16-08).

``load_dictionary_candidates(dictionary, span)`` turns an explicit domain
dictionary envelope into immutable ``MentionCandidate`` values tagged
``source="dictionary"`` / ``confidence_kind="dictionary_exact"`` with a
``confidence == 1.0`` marker that is NEVER a calibrated probability. Candidates
carry full corpus provenance copied from the ``CorpusSpanInput`` and the
schema/segmentation/label-map/extractor provenance from the source envelope.

Coordinate discipline
---------------------
Entry coordinates are explicit zero-based half-open Python Unicode code-point
offsets that are span-local. The loader validates the exact parent slice-back
``normalized_text[char_start:char_end] == mention_text`` and NEVER locates text
with find/index/search or substring recovery. Input order is preserved and
duplicate surface text at distinct explicit coordinates stays distinct.

Fail-closed contract
--------------------
- The input must be a ``CorpusSpanInput``; a query input (or anything else)
  raises ``DictionarySourceError``.
- The envelope must be a plain mapping carrying ``extractor_id ==
  "supplementary"`` plus non-empty ``extractor_version`` / ``schema_version`` /
  ``segmentation_version`` and a 64-character lowercase-hex
  ``label_map_digest``.
- Occurrences live under the required ``entries`` list; every entry is a
  mapping with explicit ``char_start`` / ``char_end`` / ``mention_text`` /
  ``raw_label`` / ``canonical_label`` / ``entity_type``.

This module imports only the standard library plus ``.contracts``; it performs
zero heavy/model/network/database/generative-LLM work and never mutates its
inputs. A dictionary-only pipeline never satisfies C1 acceptance on its own.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import CorpusSpanInput, MentionCandidate

_LOWER_HEX = "0123456789abcdef"


class DictionarySourceError(ValueError):
    """Fail-closed typed error for malformed dictionary source input."""


def _validate_provenance(envelope: Mapping[str, object]) -> dict[str, object]:
    if envelope.get("extractor_id") != "supplementary":
        raise DictionarySourceError(
            "dictionary extractor_id must be exactly 'supplementary'"
        )
    extractor_version = envelope.get("extractor_version")
    if type(extractor_version) is not str or not extractor_version:
        raise DictionarySourceError(
            "dictionary extractor_version must be a non-empty string"
        )
    schema_version = envelope.get("schema_version")
    if type(schema_version) is not str or not schema_version:
        raise DictionarySourceError(
            "dictionary schema_version must be a non-empty string"
        )
    segmentation_version = envelope.get("segmentation_version")
    if type(segmentation_version) is not str or not segmentation_version:
        raise DictionarySourceError(
            "dictionary segmentation_version must be a non-empty string"
        )
    label_map_digest = envelope.get("label_map_digest")
    if (
        type(label_map_digest) is not str
        or len(label_map_digest) != 64
        or any(character not in _LOWER_HEX for character in label_map_digest)
    ):
        raise DictionarySourceError(
            "dictionary label_map_digest must be 64 lowercase hex characters"
        )
    return {
        "extractor_version": extractor_version,
        "schema_version": schema_version,
        "segmentation_version": segmentation_version,
        "label_map_digest": label_map_digest,
    }


def _build_candidate(
    entry: object,
    span: CorpusSpanInput,
    normalized_text: str,
    provenance: Mapping[str, object],
    index: int,
) -> MentionCandidate:
    if not isinstance(entry, Mapping):
        raise DictionarySourceError(f"dictionary entries[{index}] must be a mapping")
    char_start = entry.get("char_start")
    char_end = entry.get("char_end")
    if type(char_start) is not int or type(char_end) is not int:
        raise DictionarySourceError(
            f"dictionary entries[{index}] coordinates must be integers"
        )
    mention_text = entry.get("mention_text")
    raw_label = entry.get("raw_label")
    canonical_label = entry.get("canonical_label")
    entity_type = entry.get("entity_type")
    for value, name in (
        (mention_text, "mention_text"),
        (raw_label, "raw_label"),
        (canonical_label, "canonical_label"),
        (entity_type, "entity_type"),
    ):
        if type(value) is not str or not value:
            raise DictionarySourceError(
                f"dictionary entries[{index}].{name} must be a non-empty string"
            )
    if not (0 <= char_start < char_end <= len(normalized_text)):
        raise DictionarySourceError(
            f"dictionary entries[{index}] coordinates are out of range"
        )
    if normalized_text[char_start:char_end] != mention_text:
        raise DictionarySourceError(
            f"dictionary entries[{index}] mention_text does not slice back from normalized_text"
        )
    return MentionCandidate(
        input_id=span.span_id,
        input_kind="corpus_span",
        input_revision=span.input_revision,
        normalized_text=normalized_text,
        span_id=span.span_id,
        segment_id=None,
        char_start=char_start,
        char_end=char_end,
        mention_text=mention_text,
        raw_label=raw_label,
        canonical_label=canonical_label,
        entity_type=entity_type,
        confidence=1.0,
        confidence_kind="dictionary_exact",
        source="dictionary",
        extractor_id="supplementary",
        extractor_version=provenance["extractor_version"],
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        schema_version=provenance["schema_version"],
        normalization_version=span.normalization_version,
        segmentation_version=provenance["segmentation_version"],
        label_map_digest=provenance["label_map_digest"],
        runtime_compatibility_id=None,
        document_id=span.document_id,
        version_id=span.version_id,
        document_revision=span.document_revision,
        projection=span.projection,
    )


def load_dictionary_candidates(
    dictionary: object, span: object
) -> list[MentionCandidate]:
    """Build dictionary-exact candidates from an explicit domain dictionary."""
    if not isinstance(span, CorpusSpanInput):
        raise DictionarySourceError("dictionary loader requires a CorpusSpanInput")
    if not isinstance(dictionary, Mapping):
        raise DictionarySourceError("dictionary must be a mapping")
    provenance = _validate_provenance(dictionary)
    entries = dictionary.get("entries")
    if type(entries) is not list:
        raise DictionarySourceError("dictionary entries must be a list")
    normalized_text = span.normalized_text
    candidates: list[MentionCandidate] = []
    for index, entry in enumerate(entries):
        candidates.append(
            _build_candidate(entry, span, normalized_text, provenance, index)
        )
    return candidates


__all__ = ["DictionarySourceError", "load_dictionary_candidates"]
