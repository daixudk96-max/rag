"""Frozen E2b raw-corpus entity-layer contracts (pure, dependency-free).

Phase 16-02. Implements the discriminated ``CorpusSpanInput | QueryTextInput``
union, the immutable full-provenance ``MentionCandidate``, and the E2b-namespace
bound deterministic identity helpers.

Reuse discipline
----------------
``canonical_json`` / ``canonical_json_sha256`` are re-exported from the existing
OKF E2a contract module (identical behavior, never copied), and the shared
validation primitives (``_uuid``, ``_digest``, ``_unicode_scalar``,
``_frozen_mapping``) are imported from ``e2a_contract_primitives``. Importing
this module performs zero modelscope/torch/jieba imports and touches no
persistence, merger, adapter, model, network, or database code.

Nullable model provenance
-------------------------
Per the frozen Phase 16 sources (model-selection DTO §3.2, 16-08, 16-07/D8),
``model_id``, ``model_revision``, ``artifact_digest``, and
``runtime_compatibility_id`` are conditionally nullable. ``source == "model"``
candidates require complete, digest-valid model provenance; ``runtime_compatibility_id``
may stay ``None`` until a separately authorized mirror smoke freezes it. Non-model
sources (dictionary/rule/frontmatter) must carry no model provenance at all.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, get_args
from uuid import NAMESPACE_URL, uuid5

from ..okf.e2a_contract_primitives import (
    _digest,
    _frozen_mapping,
    _unicode_scalar,
    _uuid,
)
from ..okf.e2a_contracts import (
    canonical_json,
    canonical_json_sha256,
)

E2B_NAMESPACE = uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2b")

InputKind = Literal["corpus_span", "query_text"]
ConfidenceKind = Literal[
    "frontmatter_declared",
    "dictionary_exact",
    "rule_weight",
    "model_probability",
    "unavailable",
]
MentionSource = Literal["model", "dictionary", "rule", "frontmatter"]

INPUT_KINDS = frozenset(get_args(InputKind))
CONFIDENCE_KINDS = frozenset(get_args(ConfidenceKind))
MENTION_SOURCES = frozenset(get_args(MentionSource))

# Mandatory non-empty provenance fields carried by every MentionCandidate.
# model_id/model_revision/artifact_digest/runtime_compatibility_id are NOT in
# this set: per the frozen Phase 16 sources they are conditionally nullable
# (dictionary/frontmatter/rule supplements carry no model provenance at all;
# runtime compatibility is unresolved/None until a separately-authorized smoke).
_PROVENANCE_FIELD_NAMES = (
    "raw_label",
    "canonical_label",
    "entity_type",
    "extractor_id",
    "extractor_version",
    "schema_version",
    "normalization_version",
    "segmentation_version",
)


_MODEL_PROVENANCE_FIELDS = (
    "model_id",
    "model_revision",
    "artifact_digest",
    "runtime_compatibility_id",
)


def deterministic_id(kind: str, natural_key: str) -> str:
    """Deterministic E2b identity for the given kind and natural key."""
    if (
        type(kind) is not str
        or type(natural_key) is not str
        or not kind
        or not natural_key
    ):
        raise ValueError("deterministic identity requires a kind and natural key")
    return str(uuid5(E2B_NAMESPACE, f"{kind}:{natural_key}"))


def _require_nonempty_scalar(value: object, name: str) -> None:
    """Require a non-empty Unicode scalar string."""
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")
    _unicode_scalar(value, name)


def _require_revision_equality(
    input_revision: object, field_value: object, label: str
) -> None:
    """Enforce FIELD-VALUE revision equality (never a literal kind name)."""
    _require_nonempty_scalar(input_revision, "input_revision")
    _require_nonempty_scalar(field_value, label)
    if input_revision != field_value:
        raise ValueError(f"input_revision must equal the {label} field value")


def _freeze_projection(value: object) -> Mapping[str, object]:
    """Canonicalize a document/sidecar projection into an immutable mapping."""
    return _frozen_mapping(value, "projection")


@dataclass(frozen=True)
class CorpusSpanInput:
    """Immutable corpus span input that may be persisted.

    ``input_revision`` is the same object as the ``document_revision`` FIELD
    VALUE; it is never the literal string ``"document_revision"``.
    """

    document_id: str
    version_id: str
    span_id: str
    document_revision: str
    input_revision: str
    normalized_text: str
    normalization_version: str
    projection: Mapping[str, object]
    input_kind: Literal["corpus_span"] = field(init=False, default="corpus_span")

    def __post_init__(self) -> None:
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")
        _uuid(self.span_id, "span_id")
        _require_revision_equality(
            self.input_revision, self.document_revision, "document_revision"
        )
        _require_nonempty_scalar(self.normalized_text, "normalized_text")
        _require_nonempty_scalar(self.normalization_version, "normalization_version")
        object.__setattr__(self, "projection", _freeze_projection(self.projection))

    @property
    def input_id(self) -> str:
        """Corpus spans are identified by their span id."""
        return self.span_id


@dataclass(frozen=True)
class QueryTextInput:
    """Immutable query-local text input that is request-scoped only.

    ``input_revision`` is the same object as the ``query_revision`` FIELD VALUE;
    it is never the literal string ``"query_revision"``. A query input never
    carries any corpus document/sidecar projection.
    """

    query_id: str
    query_revision: str
    input_revision: str
    normalized_text: str
    normalization_version: str
    input_kind: Literal["query_text"] = field(init=False, default="query_text")

    def __post_init__(self) -> None:
        _uuid(self.query_id, "query_id")
        _require_revision_equality(
            self.input_revision, self.query_revision, "query_revision"
        )
        _require_nonempty_scalar(self.normalized_text, "normalized_text")
        _require_nonempty_scalar(self.normalization_version, "normalization_version")

    @property
    def input_id(self) -> str:
        """Query inputs are identified by their query-local identity."""
        return self.query_id


ExtractionInput = CorpusSpanInput | QueryTextInput


@dataclass(frozen=True)
class MentionCandidate:
    """Immutable extractor candidate over exact normalized-text coordinates.

    ``char_start``/``char_end`` are zero-based, left-closed right-open Python
    Unicode code-point coordinates over ``normalized_text``; the invariant
    ``0 <= char_start < char_end <= len(normalized_text)`` and
    ``normalized_text[char_start:char_end] == mention_text`` is enforced in
    ``__post_init__`` with no substring recovery. Corpus candidates carry a
    document/sidecar projection; query candidates must not.
    """

    input_id: str
    input_kind: InputKind
    input_revision: str
    normalized_text: str
    span_id: str | None
    segment_id: str | None
    char_start: int
    char_end: int
    mention_text: str
    raw_label: str
    canonical_label: str
    entity_type: str
    confidence: float | None
    confidence_kind: ConfidenceKind
    source: MentionSource
    extractor_id: str
    extractor_version: str
    model_id: str | None
    model_revision: str | None
    artifact_digest: str | None
    schema_version: str
    normalization_version: str
    segmentation_version: str
    label_map_digest: str
    runtime_compatibility_id: str | None
    document_id: str | None = None
    version_id: str | None = None
    document_revision: str | None = None
    projection: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _uuid(self.input_id, "input_id")
        if self.input_kind not in INPUT_KINDS:
            raise ValueError("mention input_kind is unsupported")
        _require_nonempty_scalar(self.input_revision, "input_revision")
        _require_nonempty_scalar(self.normalized_text, "normalized_text")
        self._validate_coordinates()
        self._validate_provenance()
        self._validate_model_provenance()
        if self.segment_id is not None:
            _require_nonempty_scalar(self.segment_id, "segment_id")
        if self.input_kind == "corpus_span":
            self._validate_corpus_projection()
        else:
            self._validate_query_absence()

    def _validate_coordinates(self) -> None:
        if type(self.char_start) is not int or type(self.char_end) is not int:
            raise ValueError("mention coordinates must be integers")
        _require_nonempty_scalar(self.mention_text, "mention_text")
        if not (0 <= self.char_start < self.char_end <= len(self.normalized_text)):
            raise ValueError("mention coordinates are out of range")
        if self.normalized_text[self.char_start : self.char_end] != self.mention_text:
            raise ValueError("mention_text does not slice back from normalized_text")

    def _validate_provenance(self) -> None:
        for name in _PROVENANCE_FIELD_NAMES:
            _require_nonempty_scalar(getattr(self, name), name)
        _digest(self.label_map_digest, "label_map_digest")
        if self.confidence_kind not in CONFIDENCE_KINDS:
            raise ValueError("mention confidence_kind is unsupported")
        if self.source not in MENTION_SOURCES:
            raise ValueError("mention source is unsupported")
        if self.confidence is None:
            if self.confidence_kind != "unavailable":
                raise ValueError(
                    "confidence may be None only when confidence_kind is unavailable"
                )
        else:
            if type(self.confidence) is not float or not math.isfinite(self.confidence):
                raise ValueError("confidence must be a finite float")
            if self.confidence_kind == "unavailable":
                raise ValueError("unavailable confidence must be None")

    def _validate_model_provenance(self) -> None:
        """Enforce the frozen nullable model-provenance rules.

        ``source == "model"`` candidates (model-backed extraction) require complete, digest-valid
        model provenance (model_id, model_revision, artifact_digest), while
        ``runtime_compatibility_id`` may remain ``None`` until a separately
        authorized offline-mirror smoke freezes it (16-07/D8). Non-model sources
        (dictionary/rule/frontmatter) must carry no model provenance at all.
        """
        if self.model_id is not None:
            _require_nonempty_scalar(self.model_id, "model_id")
        if self.model_revision is not None:
            _require_nonempty_scalar(self.model_revision, "model_revision")
        if self.artifact_digest is not None:
            _digest(self.artifact_digest, "artifact_digest")
        if self.runtime_compatibility_id is not None:
            _require_nonempty_scalar(
                self.runtime_compatibility_id, "runtime_compatibility_id"
            )
        if self.source == "model":
            if (
                self.model_id is None
                or self.model_revision is None
                or self.artifact_digest is None
            ):
                raise ValueError("model candidates require complete model provenance")
        elif any(getattr(self, name) is not None for name in _MODEL_PROVENANCE_FIELDS):
            raise ValueError("non-model candidates must not carry model provenance")

    def _validate_corpus_projection(self) -> None:
        if self.span_id is None:
            raise ValueError("corpus mention requires span_id")
        _uuid(self.span_id, "span_id")
        if self.input_id != self.span_id:
            raise ValueError("corpus mention input_id must equal span_id")
        if (
            self.document_id is None
            or self.version_id is None
            or self.document_revision is None
        ):
            raise ValueError("corpus mention requires a document/sidecar projection")
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")
        _require_revision_equality(
            self.input_revision, self.document_revision, "document_revision"
        )
        object.__setattr__(self, "projection", _freeze_projection(self.projection))

    def _validate_query_absence(self) -> None:
        if self.span_id is not None:
            raise ValueError("query mention must not carry span_id")
        if (
            self.document_id is not None
            or self.version_id is not None
            or self.document_revision is not None
            or self.projection is not None
        ):
            raise ValueError(
                "query mention must not carry a document/sidecar projection"
            )
        if self.source == "frontmatter":
            raise ValueError("query mention must not carry a frontmatter source")


__all__ = [
    "CONFIDENCE_KINDS",
    "E2B_NAMESPACE",
    "INPUT_KINDS",
    "MENTION_SOURCES",
    "ConfidenceKind",
    "CorpusSpanInput",
    "ExtractionInput",
    "InputKind",
    "MentionCandidate",
    "MentionSource",
    "QueryTextInput",
    "canonical_json",
    "canonical_json_sha256",
    "deterministic_id",
]
