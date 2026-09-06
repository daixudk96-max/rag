"""Pure stdlib UIE -> entity-layer adapter (Phase 17-W2, review-fixed).

Turns raw UIE extraction output (mappings in the fake-JSON wire shape) into
contract-valid, full-provenance corpus MentionCandidate values and gated
relation triples, with every failure recorded instead of repaired. Frozen
semantics:

- normalize_source_text is the v1 policy: Unicode NFKC normalization plus
  stripping of leading/trailing whitespace. The policy is idempotent, and
  both mapping entry points only accept a normalized_text that is already in
  this canonical form (NFKC-normalized, end-stripped, non-empty), so
  declared offsets always refer to the exact canonical text. Zero-width
  characters (ZWSP U+200B, BOM U+FEFF) survive NFKC and are not removed --
  a known v1 limitation tracked for W4.
- Offsets are authoritative and never recovered: a declared
  (char_start, char_end) must slice back to mention_text exactly. A mention
  whose declared offsets do not slice back is rejected even when its text
  occurs elsewhere; membership checks only verify declared spans and
  anchoring and never locate or recover positions in the text.
- span_id identity is uuid5 over (document_id, version_id, mention_text,
  char_start, char_end, sha256(normalized_text)) under a module-bound
  namespace, so reruns over identical inputs are idempotent (byte-identical
  UUIDs) while two different texts of one document/version can never
  collide on one span id; corpus candidates carry input_id == span_id per
  the frozen contract.
- The canonical type table is explicitly frozen to the OKF canonical set of
  the frozen label_map v1 (renming->Person, diming->Location,
  gongsiming->Organization, chanpinming->Product); unknown or missing
  labels are rejected, never guessed.
- RelationSchema is a frozen dataclass with a two-sided gate {relation:
  (allowed_subject_types, allowed_object_types)} and to_dict/from_dict for
  single-run lifecycle files; DEFAULT_RELATION_SCHEMA pins the frozen v2
  schema (所在地/所属公司/任职于/发布/总部位于/使用/通话/前往).
- Relation triples additionally require the subject and object text to
  exactly equal the mention_text of an accepted candidate of the same call
  (mention-membership gating), reject self loops, duplicate
  (subject, relation, object, source) combinations and too-short texts, and
  enforce that subject/object text are exact substrings of the mandatory
  source sentence, which itself must be anchored in normalized_text.
- Per-entity and per-relation data failures become recorded rejections with
  a frozen reason enum; call-level contract violations (non-canonical or nil
  document/version ids, non-canonical text, wrong schema type,
  non-sequence inputs) raise UieMappingError immediately.

This module imports only the standard library plus .contracts; it never
loads a model, never touches the network, and never performs I/O.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from .contracts import MentionCandidate

__all__ = [
    "CANONICAL_ENTITY_TYPES",
    "DEFAULT_RELATION_SCHEMA",
    "DEFAULT_RELATION_SCHEMA_VERSION",
    "EXTRACTOR_ID",
    "EXTRACTOR_VERSION",
    "INPUT_REVISION",
    "LABEL_MAP_DIGEST",
    "MODEL_ID",
    "MODEL_REVISION",
    "NORMALIZATION_POLICY",
    "NORMALIZATION_VERSION",
    "RejectionReason",
    "RelationMappingResult",
    "RelationSchema",
    "RelationTriple",
    "SCHEMA_VERSION",
    "SEGMENTATION_VERSION",
    "UIE_TYPE_TO_CANONICAL",
    "UieMappingError",
    "UieMappingResult",
    "UieRejection",
    "map_entity_mentions",
    "map_relation_triples",
    "normalize_source_text",
]

EXTRACTOR_ID: Final[str] = "pp-uie-0.5b"
EXTRACTOR_VERSION: Final[str] = "0.5.0"
MODEL_ID: Final[str] = "PP-UIE-0.5B"
MODEL_REVISION: Final[str] = "aistudio-offline"
SCHEMA_VERSION: Final[str] = "v1"
NORMALIZATION_VERSION: Final[str] = "v1"
SEGMENTATION_VERSION: Final[str] = "v1"
NORMALIZATION_POLICY: Final[str] = "nfkc_strip_v1"
# Every corpus candidate needs a revision; the adapter has no revision input,
# so it stamps the frozen adapter revision into input_revision and
# document_revision (they must be equal per the MentionCandidate contract).
INPUT_REVISION: Final[str] = "uie-adapter-v1"
DEFAULT_RELATION_SCHEMA_VERSION: Final[str] = "uie-relation-schema-v2"

# Adjudication A1: canonical values are the OKF canonical set of the frozen
# llamaindex_runtime/entity/label_map.py RAINER_RAW_TO_CANONICAL v1 that
# resolution and coref_rules match on with exact entity_type equality.
UIE_TYPE_TO_CANONICAL: Final[Mapping[str, str]] = MappingProxyType(
    {
        "人名": "Person",
        "地名": "Location",
        "公司名": "Organization",
        "产品名": "Product",
    }
)
CANONICAL_ENTITY_TYPES: Final[frozenset[str]] = frozenset(
    UIE_TYPE_TO_CANONICAL.values()
)

# Adjudication A3: the digest covers the sorted (key, value) pairs so any
# value drift (not just key drift) changes the digest.
LABEL_MAP_DIGEST: Final[str] = hashlib.sha256(
    json.dumps(sorted(UIE_TYPE_TO_CANONICAL.items()), ensure_ascii=False).encode(
        "utf-8"
    ),
).hexdigest()

_NIL_UUID: Final[uuid.UUID] = uuid.UUID(int=0)

_SPAN_ID_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://gitnexus.local/llamaindex_runtime/entity/uie_adapter/span_id/v1",
)


class UieMappingError(ValueError):
    """Raised for call-level contract violations in UIE adapter mapping."""


class RejectionReason(StrEnum):
    """Frozen fail-closed rejection taxonomy for UIE adapter mappings."""

    MISSING_TEXT = "missing_text"
    MISSING_OFFSET = "missing_offset"
    OUT_OF_RANGE = "out_of_range"
    NOT_EXACT_SLICE = "not_exact_slice"
    UNKNOWN_ENTITY_TYPE = "unknown_entity_type"
    DUPLICATE_SPAN = "duplicate_span"
    MISSING_SOURCE_TEXT = "missing_source_text"
    SOURCE_NOT_IN_NORMALIZED_TEXT = "source_not_in_normalized_text"
    RELATION_NOT_IN_SCHEMA = "relation_not_in_schema"
    SUBJECT_TYPE_NOT_ALLOWED = "subject_type_not_allowed"
    OBJECT_TYPE_NOT_ALLOWED = "object_type_not_allowed"
    SUBJECT_NOT_IN_SOURCE = "subject_not_in_source"
    OBJECT_NOT_IN_SOURCE = "object_not_in_source"
    SUBJECT_NOT_A_MENTION = "subject_not_a_mention"
    OBJECT_NOT_A_MENTION = "object_not_a_mention"
    SELF_LOOP = "self_loop"
    DUPLICATE_RELATION = "duplicate_relation"
    TOO_SHORT = "too_short"
    NOT_A_MAPPING = "not_a_mapping"
    INVALID_CONFIDENCE = "invalid_confidence"
    # Unreachable via public API; defense-in-depth against contract
    # evolution of the MentionCandidate/RelationTriple constructors.
    INVALID_CANDIDATE = "invalid_candidate"


@dataclass(frozen=True)
class UieRejection:
    """One recorded fail-closed rejection from a UIE adapter mapping call."""

    index: int
    reason: RejectionReason
    text: str
    detail: str


def normalize_source_text(text: str) -> str:
    """Normalize raw source text with the frozen v1 policy.

    v1 policy: Unicode NFKC normalization followed by stripping of leading
    and trailing whitespace. The policy is idempotent -- applying it to its
    own output returns the same string -- so callers may pre-normalize
    document text once and the adapter guards re-validate that form.
    Zero-width characters (ZWSP U+200B, BOM U+FEFF) survive NFKC and are
    not removed; that is a known v1 limitation tracked for W4.
    """
    if type(text) is not str:
        raise UieMappingError("text must be a string")
    try:
        text.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise UieMappingError("text must be a Unicode scalar string") from None
    return unicodedata.normalize("NFKC", text).strip()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_canonical_uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise UieMappingError(f"{name} must be a canonical UUID string")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise UieMappingError(f"{name} must be a canonical UUID string") from None
    if str(parsed) != value:
        raise UieMappingError(f"{name} must be a canonical UUID string")
    if parsed == _NIL_UUID:
        raise UieMappingError(f"{name} must not be the nil UUID")
    return value


def _require_normalized_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise UieMappingError("normalized_text must be a non-empty string")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise UieMappingError(
            "normalized_text must be a Unicode scalar string"
        ) from None
    if unicodedata.normalize("NFKC", value).strip() != value:
        raise UieMappingError(
            "normalized_text must already be in v1 canonical form "
            "(NFKC + end-stripped, non-empty)"
        )
    return value


def _validated_confidence(value: object) -> float | None:
    """Return the validated probability, or None when invalid.

    Never raises: bools, non-numeric values, NaN/inf, out-of-range numbers
    and overflowing ints all yield None so the caller records an
    INVALID_CONFIDENCE rejection instead of silently degrading to a missing
    confidence.
    """
    try:
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float)):
            return None
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not math.isfinite(number) or not (0.0 <= number <= 1.0):
        return None
    return number


def _text_of(value: object) -> str:
    return value if isinstance(value, str) else ""


def _candidate_mention_text(candidate: object) -> str | None:
    """Read mention_text off an accepted candidate; None when unusable."""
    text = getattr(candidate, "mention_text", None)
    if isinstance(text, str) and text:
        return text
    return None


def _rejection(
    index: int, reason: RejectionReason, text: str, detail: str
) -> UieRejection:
    return UieRejection(index=index, reason=reason, text=text, detail=detail)


def _deterministic_span_id(
    *,
    document_id: str,
    version_id: str,
    mention_text: str,
    char_start: int,
    char_end: int,
    normalized_text_digest: str,
) -> str:
    """Deterministic span id; identical inputs rebuild identical UUIDs."""
    natural_key = json.dumps(
        [
            document_id,
            version_id,
            mention_text,
            char_start,
            char_end,
            normalized_text_digest,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_SPAN_ID_NAMESPACE, natural_key))


@dataclass(frozen=True)
class RelationSchema:
    """Frozen relation schema with a two-sided subject/object type gate.

    The gate maps each relation to (allowed subject types, allowed object
    types) over the canonical vocabulary. hash() raises TypeError by design
    because the gate mapping is unhashable; never store schemas in
    dicts/sets.
    """

    relations: tuple[str, ...]
    gate: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]]
    version: str = DEFAULT_RELATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.version) is not str or not self.version:
            raise UieMappingError("relation schema version must be a non-empty string")
        if type(self.relations) is not tuple or any(
            type(relation) is not str or not relation for relation in self.relations
        ):
            raise UieMappingError("relation schema relations must be non-empty strings")
        if len(set(self.relations)) != len(self.relations):
            raise UieMappingError("relation schema relations must be unique")
        if not isinstance(self.gate, Mapping):
            raise UieMappingError("relation schema gate must be a mapping")
        frozen_gate: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
        for relation, allowed in self.gate.items():
            if type(relation) is not str or relation not in self.relations:
                raise UieMappingError(
                    "relation schema gate keys must be schema relations"
                )
            if type(allowed) is not tuple or len(allowed) != 2:
                raise UieMappingError(
                    "relation schema gate values must be (subjects, objects) pairs"
                )
            subjects, objects = allowed
            for side_name, side in (("subject", subjects), ("object", objects)):
                if (
                    type(side) is not tuple
                    or not side
                    or any(
                        type(entity_type) is not str
                        or entity_type not in CANONICAL_ENTITY_TYPES
                        for entity_type in side
                    )
                ):
                    raise UieMappingError(
                        f"relation schema gate {side_name} types must be "
                        "non-empty canonical entity types"
                    )
            frozen_gate[relation] = (subjects, objects)
        object.__setattr__(self, "gate", MappingProxyType(frozen_gate))

    def to_dict(self) -> dict[str, object]:
        """JSON-able snapshot for a single-run lifecycle file."""
        return {
            "version": self.version,
            "relations": list(self.relations),
            "gate": {
                relation: [list(subjects), list(objects)]
                for relation, (subjects, objects) in self.gate.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RelationSchema:
        """Rebuild a schema from a to_dict payload; fails closed."""
        if not isinstance(data, Mapping):
            raise UieMappingError("relation schema payload must be a mapping")
        relations = data.get("relations")
        if not isinstance(relations, (list, tuple)):
            raise UieMappingError(
                "relation schema payload requires a relations sequence"
            )
        gate = data.get("gate")
        if not isinstance(gate, Mapping):
            raise UieMappingError("relation schema payload requires a gate mapping")
        normalized_gate: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
        for relation, allowed in gate.items():
            if not isinstance(allowed, (list, tuple)) or len(allowed) != 2:
                raise UieMappingError(
                    "relation schema payload gate values must be "
                    "(subjects, objects) pairs"
                )
            subjects, objects = allowed
            if not isinstance(subjects, (list, tuple)) or not isinstance(
                objects, (list, tuple)
            ):
                raise UieMappingError(
                    "relation schema payload gate sides must be sequences"
                )
            normalized_gate[relation] = (tuple(subjects), tuple(objects))
        version = data.get("version", DEFAULT_RELATION_SCHEMA_VERSION)
        if not isinstance(version, str) or not version:
            raise UieMappingError(
                "relation schema payload version must be a non-empty string"
            )
        return cls(relations=tuple(relations), gate=normalized_gate, version=version)


DEFAULT_RELATION_SCHEMA: Final[RelationSchema] = RelationSchema(
    relations=(
        "所在地",
        "所属公司",
        "任职于",
        "发布",
        "总部位于",
        "使用",
        "通话",
        "前往",
    ),
    gate={
        "所在地": (("Person",), ("Location",)),
        "所属公司": (("Person", "Product"), ("Organization",)),
        "任职于": (("Person",), ("Organization",)),
        "发布": (("Organization",), ("Product",)),
        "总部位于": (("Organization",), ("Location",)),
        "使用": (("Person",), ("Product",)),
        "通话": (("Person",), ("Person",)),
        "前往": (("Person",), ("Location",)),
    },
)


@dataclass(frozen=True)
class RelationTriple:
    """Frozen relation triple anchored to its mandatory source sentence."""

    subject_text: str
    subject_type: str
    relation: str
    object_text: str
    object_type: str
    source_text: str
    document_id: str
    version_id: str

    def __post_init__(self) -> None:
        for name in (
            "subject_text",
            "subject_type",
            "relation",
            "object_text",
            "object_type",
            "source_text",
        ):
            value = getattr(self, name)
            if type(value) is not str or not value:
                raise ValueError(f"relation triple {name} must be a non-empty string")
        if self.subject_type not in CANONICAL_ENTITY_TYPES:
            raise ValueError(
                "relation triple subject_type must be a canonical entity type"
            )
        if self.object_type not in CANONICAL_ENTITY_TYPES:
            raise ValueError(
                "relation triple object_type must be a canonical entity type"
            )
        if self.subject_text not in self.source_text:
            raise ValueError(
                "relation triple subject_text must be a substring of source_text"
            )
        if self.object_text not in self.source_text:
            raise ValueError(
                "relation triple object_text must be a substring of source_text"
            )
        _require_canonical_uuid(self.document_id, "relation triple document_id")
        _require_canonical_uuid(self.version_id, "relation triple version_id")


@dataclass(frozen=True)
class UieMappingResult:
    """Immutable entity mapping outcome: accepted candidates + rejections."""

    candidates: tuple[MentionCandidate, ...]
    rejected: tuple[UieRejection, ...]


@dataclass(frozen=True)
class RelationMappingResult:
    """Immutable relation mapping outcome: triples + rejections."""

    triples: tuple[RelationTriple, ...]
    rejected: tuple[UieRejection, ...]


def _map_one_entity(
    index: int,
    raw: object,
    *,
    document_id: str,
    version_id: str,
    normalized_text: str,
    normalized_text_digest: str,
    seen_spans: set[tuple[str, int, int]],
) -> MentionCandidate | UieRejection:
    """Map one raw UIE entity; return a candidate or a recorded rejection."""
    if not isinstance(raw, Mapping):
        return _rejection(
            index,
            RejectionReason.NOT_A_MAPPING,
            "",
            "entity entry must be a mapping",
        )
    mention_text = raw.get("text")
    if type(mention_text) is not str or not mention_text:
        return _rejection(
            index,
            RejectionReason.MISSING_TEXT,
            _text_of(mention_text),
            "entity text must be a non-empty string",
        )
    if len(mention_text) < 2 or mention_text.isspace():
        return _rejection(
            index,
            RejectionReason.TOO_SHORT,
            mention_text,
            "mention text must be at least two characters and not all whitespace",
        )
    char_start = raw.get("char_start")
    char_end = raw.get("char_end")
    if type(char_start) is not int or type(char_end) is not int:
        return _rejection(
            index,
            RejectionReason.MISSING_OFFSET,
            mention_text,
            "entity offsets must be integer char_start/char_end",
        )
    if not (0 <= char_start < char_end <= len(normalized_text)):
        return _rejection(
            index,
            RejectionReason.OUT_OF_RANGE,
            mention_text,
            "entity offsets are out of range of normalized_text",
        )
    if normalized_text[char_start:char_end] != mention_text:
        return _rejection(
            index,
            RejectionReason.NOT_EXACT_SLICE,
            mention_text,
            "declared offsets do not slice back to the mention text exactly",
        )
    raw_label = raw.get("label")
    canonical_label = (
        UIE_TYPE_TO_CANONICAL.get(raw_label) if type(raw_label) is str else None
    )
    if canonical_label is None:
        return _rejection(
            index,
            RejectionReason.UNKNOWN_ENTITY_TYPE,
            mention_text,
            f"unknown UIE label {raw_label!r}",
        )
    if "confidence" in raw:
        confidence = _validated_confidence(raw.get("confidence"))
        if confidence is None:
            return _rejection(
                index,
                RejectionReason.INVALID_CONFIDENCE,
                mention_text,
                "confidence must be a finite number in [0, 1] when present",
            )
    else:
        confidence = None
    span_key = (mention_text, char_start, char_end)
    if span_key in seen_spans:
        return _rejection(
            index,
            RejectionReason.DUPLICATE_SPAN,
            mention_text,
            "duplicate span at the same offsets in one document/version",
        )
    span_id = _deterministic_span_id(
        document_id=document_id,
        version_id=version_id,
        mention_text=mention_text,
        char_start=char_start,
        char_end=char_end,
        normalized_text_digest=normalized_text_digest,
    )
    try:
        candidate = MentionCandidate(
            input_id=span_id,
            input_kind="corpus_span",
            input_revision=INPUT_REVISION,
            normalized_text=normalized_text,
            span_id=span_id,
            segment_id=None,
            char_start=char_start,
            char_end=char_end,
            mention_text=mention_text,
            raw_label=raw_label,
            canonical_label=canonical_label,
            entity_type=canonical_label,
            confidence=confidence,
            confidence_kind=(
                "model_probability" if confidence is not None else "unavailable"
            ),
            source="model",
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            artifact_digest=_sha256_hex(mention_text),
            schema_version=SCHEMA_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            segmentation_version=SEGMENTATION_VERSION,
            label_map_digest=LABEL_MAP_DIGEST,
            runtime_compatibility_id=None,
            document_id=document_id,
            version_id=version_id,
            document_revision=INPUT_REVISION,
            projection={"normalization_policy": NORMALIZATION_POLICY},
        )
    except (ValueError, TypeError) as error:
        # Unreachable via public API; defense-in-depth against contract
        # evolution of the MentionCandidate constructor.
        return _rejection(
            index,
            RejectionReason.INVALID_CANDIDATE,
            mention_text,
            str(error),
        )
    seen_spans.add(span_key)
    return candidate


def map_entity_mentions(
    uie_entities: Sequence[object],
    *,
    document_id: str,
    version_id: str,
    normalized_text: str,
) -> UieMappingResult:
    """Map raw UIE entity mentions into corpus MentionCandidate values.

    Frozen contract (pinned by the Phase 17-W2 tests):

    1. document_id/version_id must be canonical non-nil UUID strings and
       normalized_text must already be in v1 canonical form (NFKC +
       end-stripped, non-empty); uie_entities must be a list/tuple; any
       violation raises UieMappingError.
    2. A candidate is built only when the declared (char_start, char_end)
       slices back to mention_text exactly; offsets are never guessed,
       never recovered, and never reordered.
    3. span_id is deterministic uuid5 over (document_id, version_id,
       mention_text, char_start, char_end, normalized-text digest), so
       reruns are idempotent and input_id == span_id.
    4. The UIE label must resolve through the frozen canonical type table;
       unknown or missing labels are rejected. Mentions shorter than two
       characters or all whitespace are rejected (TOO_SHORT).
    5. A present confidence field must be a finite number in [0, 1]
       (INVALID_CONFIDENCE otherwise); an absent field is legal and maps to
       confidence None with kind "unavailable".
    6. Duplicate spans (same text at the same offsets inside one call) are
       rejected so downstream coref scoping can never see a duplicate id.
    7. Every per-entity failure is recorded as a UieRejection; nothing is
       ever silently dropped.
    """
    _require_canonical_uuid(document_id, "document_id")
    _require_canonical_uuid(version_id, "version_id")
    _require_normalized_text(normalized_text)
    if not isinstance(uie_entities, (list, tuple)):
        raise UieMappingError("uie_entities must be a list or tuple of mappings")
    normalized_text_digest = _sha256_hex(normalized_text)
    candidates: list[MentionCandidate] = []
    rejected: list[UieRejection] = []
    seen_spans: set[tuple[str, int, int]] = set()
    for index, raw in enumerate(uie_entities):
        outcome = _map_one_entity(
            index,
            raw,
            document_id=document_id,
            version_id=version_id,
            normalized_text=normalized_text,
            normalized_text_digest=normalized_text_digest,
            seen_spans=seen_spans,
        )
        if isinstance(outcome, UieRejection):
            rejected.append(outcome)
        else:
            candidates.append(outcome)
    return UieMappingResult(candidates=tuple(candidates), rejected=tuple(rejected))


def _map_one_relation(
    index: int,
    raw: object,
    *,
    schema: RelationSchema,
    document_id: str,
    version_id: str,
    normalized_text: str,
    accepted_mentions: frozenset[str],
    seen_relations: set[tuple[str, str, str, str]],
) -> RelationTriple | UieRejection:
    """Map one raw UIE relation; return a triple or a recorded rejection."""
    if not isinstance(raw, Mapping):
        return _rejection(
            index,
            RejectionReason.NOT_A_MAPPING,
            "",
            "relation entry must be a mapping",
        )
    subject_text = raw.get("subject_text")
    object_text = raw.get("object_text")
    source_text = raw.get("source_text")
    if type(source_text) is not str or not source_text:
        return _rejection(
            index,
            RejectionReason.MISSING_SOURCE_TEXT,
            _text_of(subject_text),
            "relation source_text must be a non-empty string",
        )
    if source_text not in normalized_text:
        return _rejection(
            index,
            RejectionReason.SOURCE_NOT_IN_NORMALIZED_TEXT,
            _text_of(subject_text),
            "relation source_text is not anchored in normalized_text",
        )
    if type(subject_text) is not str or not subject_text:
        return _rejection(
            index,
            RejectionReason.MISSING_TEXT,
            _text_of(subject_text),
            "relation subject_text must be a non-empty string",
        )
    if len(subject_text) < 2 or subject_text.isspace():
        return _rejection(
            index,
            RejectionReason.TOO_SHORT,
            subject_text,
            "subject_text must be at least two characters and not all whitespace",
        )
    if type(object_text) is not str or not object_text:
        return _rejection(
            index,
            RejectionReason.MISSING_TEXT,
            _text_of(object_text),
            "relation object_text must be a non-empty string",
        )
    if len(object_text) < 2 or object_text.isspace():
        return _rejection(
            index,
            RejectionReason.TOO_SHORT,
            object_text,
            "object_text must be at least two characters and not all whitespace",
        )
    raw_subject_type = raw.get("subject_type")
    subject_type = (
        UIE_TYPE_TO_CANONICAL.get(raw_subject_type)
        if type(raw_subject_type) is str
        else None
    )
    if subject_type is None:
        return _rejection(
            index,
            RejectionReason.UNKNOWN_ENTITY_TYPE,
            subject_text,
            f"unknown UIE subject_type {raw_subject_type!r}",
        )
    raw_object_type = raw.get("object_type")
    object_type = (
        UIE_TYPE_TO_CANONICAL.get(raw_object_type)
        if type(raw_object_type) is str
        else None
    )
    if object_type is None:
        return _rejection(
            index,
            RejectionReason.UNKNOWN_ENTITY_TYPE,
            object_text,
            f"unknown UIE object_type {raw_object_type!r}",
        )
    relation = raw.get("relation")
    if type(relation) is not str or not relation or relation not in schema.relations:
        return _rejection(
            index,
            RejectionReason.RELATION_NOT_IN_SCHEMA,
            subject_text,
            f"relation {relation!r} is not part of schema {schema.version!r}",
        )
    allowed_subjects, allowed_objects = schema.gate.get(relation, ((), ()))
    if subject_type not in allowed_subjects:
        return _rejection(
            index,
            RejectionReason.SUBJECT_TYPE_NOT_ALLOWED,
            subject_text,
            f"relation {relation!r} is not allowed for canonical subject type "
            f"{subject_type!r}",
        )
    if object_type not in allowed_objects:
        return _rejection(
            index,
            RejectionReason.OBJECT_TYPE_NOT_ALLOWED,
            object_text,
            f"relation {relation!r} is not allowed for canonical object type "
            f"{object_type!r}",
        )
    if subject_text not in source_text:
        return _rejection(
            index,
            RejectionReason.SUBJECT_NOT_IN_SOURCE,
            subject_text,
            "subject_text must be an exact substring of source_text",
        )
    if object_text not in source_text:
        return _rejection(
            index,
            RejectionReason.OBJECT_NOT_IN_SOURCE,
            object_text,
            "object_text must be an exact substring of source_text",
        )
    if subject_text not in accepted_mentions:
        return _rejection(
            index,
            RejectionReason.SUBJECT_NOT_A_MENTION,
            subject_text,
            "subject_text must exactly equal the mention_text of an accepted "
            "candidate of the same call",
        )
    if object_text not in accepted_mentions:
        return _rejection(
            index,
            RejectionReason.OBJECT_NOT_A_MENTION,
            object_text,
            "object_text must exactly equal the mention_text of an accepted "
            "candidate of the same call",
        )
    if subject_text == object_text:
        return _rejection(
            index,
            RejectionReason.SELF_LOOP,
            subject_text,
            "relation subject and object text must differ",
        )
    relation_key = (subject_text, relation, object_text, source_text)
    if relation_key in seen_relations:
        return _rejection(
            index,
            RejectionReason.DUPLICATE_RELATION,
            subject_text,
            "duplicate (subject, relation, object, source) inside one call",
        )
    try:
        triple = RelationTriple(
            subject_text=subject_text,
            subject_type=subject_type,
            relation=relation,
            object_text=object_text,
            object_type=object_type,
            source_text=source_text,
            document_id=document_id,
            version_id=version_id,
        )
    except (ValueError, TypeError) as error:
        # Unreachable via public API; defense-in-depth against contract
        # evolution of the RelationTriple constructor.
        return _rejection(
            index,
            RejectionReason.INVALID_CANDIDATE,
            subject_text,
            str(error),
        )
    seen_relations.add(relation_key)
    return triple


def map_relation_triples(
    uie_relations: Sequence[object],
    schema: RelationSchema,
    *,
    document_id: str,
    version_id: str,
    normalized_text: str,
    candidates: Sequence[MentionCandidate],
) -> RelationMappingResult:
    """Map raw UIE relations into gated frozen RelationTriple values.

    Frozen contract (pinned by the Phase 17-W2 tests):

    1. schema must be a RelationSchema; document_id/version_id must be
       canonical non-nil UUID strings; normalized_text must already be in v1
       canonical form; uie_relations and candidates must be list/tuple; any
       violation raises UieMappingError.
    2. candidates are the accepted candidates of the same call; the subject
       and object text must exactly equal the mention_text of one of them
       (mention-membership gating blocks arbitrary relation-side
       substrings). The gate only reads mention_text.
    3. Each relation carries a mandatory non-empty source_text that must be
       an exact substring of normalized_text (the source sentence is
       anchored to the document text).
    4. Subject/object UIE types resolve through the frozen canonical type
       table; unknown types are rejected.
    5. The relation must exist in the schema AND its canonical subject and
       object types must both be allowed by the two-sided gate.
    6. Subject and object text must be exact substrings of the source
       sentence; positions are never guessed (membership checks only
       verify, they never locate).
    7. Self loops, duplicate (subject, relation, object, source)
       combinations and too-short texts are rejected.
    8. Every per-relation failure is recorded as a UieRejection.
    """
    if type(schema) is not RelationSchema:
        raise UieMappingError("schema must be a RelationSchema")
    _require_canonical_uuid(document_id, "document_id")
    _require_canonical_uuid(version_id, "version_id")
    _require_normalized_text(normalized_text)
    if not isinstance(uie_relations, (list, tuple)):
        raise UieMappingError("uie_relations must be a list or tuple of mappings")
    if not isinstance(candidates, (list, tuple)):
        raise UieMappingError(
            "candidates must be a list or tuple of accepted candidates"
        )
    accepted: set[str] = set()
    for candidate in candidates:
        text = _candidate_mention_text(candidate)
        if text is not None:
            accepted.add(text)
    accepted_mentions: frozenset[str] = frozenset(accepted)
    triples: list[RelationTriple] = []
    rejected: list[UieRejection] = []
    seen_relations: set[tuple[str, str, str, str]] = set()
    for index, raw in enumerate(uie_relations):
        outcome = _map_one_relation(
            index,
            raw,
            schema=schema,
            document_id=document_id,
            version_id=version_id,
            normalized_text=normalized_text,
            accepted_mentions=accepted_mentions,
            seen_relations=seen_relations,
        )
        if isinstance(outcome, UieRejection):
            rejected.append(outcome)
        else:
            triples.append(outcome)
    return RelationMappingResult(triples=tuple(triples), rejected=tuple(rejected))
