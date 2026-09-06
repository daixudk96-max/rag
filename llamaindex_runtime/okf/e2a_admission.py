"""Complete-corpus, bounded and fail-closed E2a admission through raw pairs."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol
from uuid import UUID

from .contracts import (
    ConceptFrontmatterContract,
    EntityFrontmatterContract,
    RelationFrontmatterContract,
    validate_known_frontmatter,
)
from .e2a_frontmatter import (
    load_strict_e2a_frontmatter,
    validate_strict_e2a_raw_frontmatter_bytes,
)
from .e2a_contracts import (
    E2aDesiredState,
    E2aEvidenceObject,
    E2aEvidenceReference,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from .e2a_reconciler import E2aMaterializationInput
from .raw_pair import RawPairSnapshot, read_raw_pair
from .rooted_open import BundleAuthority
from .sidecar import SpanRecord

MAX_E2A_CANDIDATES = 10_000
MAX_E2A_PATH_COMPONENTS = 32
MAX_E2A_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_E2A_SOURCE_BYTES = 256 * 1024 * 1024
MAX_E2A_MANUAL_BYTES = 64 * 1024 * 1024
MAX_E2A_MANUAL_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_E2A_RAW_MARKDOWN_FILE_BYTES = 16 * 1024 * 1024
MAX_E2A_RAW_MARKDOWN_AGGREGATE_BYTES = 256 * 1024 * 1024
MAX_E2A_MANIFEST_READ_BYTES = 16 * 1024
MAX_E2A_SIDECAR_READ_BYTES = 64 * 1024 * 1024
MAX_E2A_DIRECTORY_ENTRIES = 100_000
MAX_E2A_DEPTH = 32
MAX_E2A_SPANS = 1_000_000
_MANUAL_DIRECTORIES = ("entities", "relations", "concepts")
_EXCLUDED_PARTS = frozenset(
    {"templates", "template", "synthesis", "support", "reserved"}
)


_AdmittedPair = tuple[E2aParent, tuple[E2aSpan, ...], dict[str, object]]
_MaterializationMetadata = tuple[str, str, tuple[dict[str, object], ...]]


class E2aCorpusAdmitter:

    def admit_e2a_corpus(self, authority: BundleAuthority) -> E2aDesiredState:
        return _admit_corpus(
            authority, lambda reader, pair: (_admit_pair(reader, pair), None)
        )[0]


def admit_e2a_corpus(authority: BundleAuthority) -> E2aDesiredState:
    return E2aCorpusAdmitter().admit_e2a_corpus(authority)


def admit_e2a_materialization_input(
    authority: BundleAuthority,
) -> E2aMaterializationInput:
    state, metadata = _admit_corpus(
        authority, _admit_pair_with_materialization_metadata
    )
    materialized = tuple(value for value in metadata if value is not None)
    if len(materialized) != len(state.parents):
        raise ValueError("e2a_admission_raw_invalid")
    return E2aMaterializationInput(
        admitted=state,
        span_records=tuple(
            record for _, _, records in materialized for record in records
        ),
        parent_source_checksums={
            version_id: source_checksum
            for version_id, source_checksum, _ in materialized
        },
    )


def admit_e2a_corpus_hash(state: E2aDesiredState) -> str:
    return canonical_json_sha256(state.corpus_manifest)


_LedgerReader = Callable[[tuple[str, ...], int], bytes]


class _RawPairReadAuthority(Protocol):
    def read_manifest(self, parts: tuple[str, ...]) -> bytes: ...

    def read_document(
        self, parts: tuple[str, ...], maximum: int | None = None
    ) -> bytes: ...

    def read_sidecar(self, parts: tuple[str, ...]) -> bytes: ...


def _admit_corpus(
    authority: BundleAuthority,
    admit_pair: Callable[..., tuple[_AdmittedPair, _MaterializationMetadata | None]],
) -> tuple[E2aDesiredState, tuple[_MaterializationMetadata | None, ...]]:
    files = authority.enumerate_regular_files(
        maximum_files=MAX_E2A_CANDIDATES,
        maximum_entries=MAX_E2A_DIRECTORY_ENTRIES,
        maximum_depth=MAX_E2A_DEPTH,
    )
    pairs, facts = _raw_pair_paths(files), _manual_fact_paths(files)
    if not pairs and not facts:
        raise ValueError("e2a_admission_empty")
    budgeted = _BudgetedAuthority(authority)
    admitted_pairs: list[_AdmittedPair] = []
    metadata: list[_MaterializationMetadata | None] = []
    span_count = 0
    for pair in pairs:
        value, pair_metadata = admit_pair(budgeted, pair)
        span_count += len(value[1])
        if span_count > MAX_E2A_SPANS:
            raise ValueError("e2a_admission_resource_limit")
        admitted_pairs.append(value)
        metadata.append(pair_metadata)
    admitted_facts = tuple(
        _admit_fact(budgeted, fact, tuple(admitted_pairs)) for fact in facts
    )
    if (
        authority.enumerate_regular_files(
            maximum_files=MAX_E2A_CANDIDATES,
            maximum_entries=MAX_E2A_DIRECTORY_ENTRIES,
            maximum_depth=MAX_E2A_DEPTH,
        )
        != files
    ):
        raise ValueError("e2a_admission_corpus_unstable")
    return _desired_state(tuple(admitted_pairs), admitted_facts), tuple(metadata)


@dataclass
class _ReadLedger:
    limits: dict[str, int]
    used: dict[str, int]

    def read(
        self,
        bucket: str,
        reader: _LedgerReader,
        parts: tuple[str, ...],
        maximum: int,
    ) -> bytes:
        return self._reserve_and_read(bucket, reader, parts, maximum)

    def read_bounded(
        self,
        bucket: str,
        reader: _LedgerReader,
        parts: tuple[str, ...],
        maximum: int,
        per_file_cap: int,
    ) -> bytes:
        if (
            type(maximum) is not int
            or type(per_file_cap) is not int
            or maximum <= 0
            or per_file_cap <= 0
        ):
            raise ValueError("e2a_admission_resource_limit")
        remaining = self.limits[bucket] - self.used[bucket]
        reservation = min(maximum, remaining)
        effective_maximum = min(reservation, per_file_cap)
        if effective_maximum <= 0:
            raise ValueError("e2a_admission_resource_limit")

        def read_capped(requested_parts: tuple[str, ...], _: int) -> bytes:
            return reader(requested_parts, effective_maximum)

        return self._reserve_and_read(bucket, read_capped, parts, reservation)

    def _reserve_and_read(
        self,
        bucket: str,
        reader: _LedgerReader,
        parts: tuple[str, ...],
        reservation: int,
    ) -> bytes:
        if type(reservation) is not int or reservation <= 0:
            raise ValueError("e2a_admission_resource_limit")
        remaining = self.limits[bucket] - self.used[bucket]
        if remaining < reservation:
            raise ValueError("e2a_admission_resource_limit")
        self.used[bucket] += reservation
        value = reader(parts, reservation)
        if type(value) is not bytes or len(value) > reservation:
            raise ValueError("e2a_admission_resource_limit")
        self.used[bucket] -= reservation - len(value)
        return value


class _BudgetedAuthority:

    def __init__(self, authority: _RawPairReadAuthority) -> None:
        self._authority = authority
        self._ledger = _ReadLedger(
            {
                "manifest": MAX_E2A_MANIFEST_BYTES,
                "markdown": MAX_E2A_RAW_MARKDOWN_AGGREGATE_BYTES,
                "sidecar": MAX_E2A_SOURCE_BYTES,
                "manual": MAX_E2A_MANUAL_BYTES,
            },
            {"manifest": 0, "markdown": 0, "sidecar": 0, "manual": 0},
        )

    def read_manifest(self, parts: tuple[str, ...]) -> bytes:
        return self._ledger.read(
            "manifest", self._read_manifest, parts, MAX_E2A_MANIFEST_READ_BYTES
        )

    def read_document(
        self, parts: tuple[str, ...], maximum: int | None = None
    ) -> bytes:
        bucket = "markdown" if parts and parts[0] == "raw" else "manual"
        per_file_cap = (
            MAX_E2A_RAW_MARKDOWN_FILE_BYTES
            if bucket == "markdown"
            else MAX_E2A_MANUAL_DOCUMENT_BYTES
        )
        caller_maximum = per_file_cap if maximum is None else maximum
        return self._ledger.read_bounded(
            bucket,
            self._read_document,
            parts,
            caller_maximum,
            per_file_cap,
        )

    def read_sidecar(self, parts: tuple[str, ...]) -> bytes:
        return self._ledger.read(
            "sidecar", self._read_sidecar, parts, MAX_E2A_SIDECAR_READ_BYTES
        )

    def _read_manifest(self, parts: tuple[str, ...], _: int) -> bytes:
        return self._authority.read_manifest(parts)

    def _read_document(self, parts: tuple[str, ...], maximum: int) -> bytes:
        return self._authority.read_document(parts, maximum)

    def _read_sidecar(self, parts: tuple[str, ...], _: int) -> bytes:
        return self._authority.read_sidecar(parts)


def _raw_pair_paths(files: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    raw = {
        parts for parts in files if parts and parts[0] == "raw" and not _excluded(parts)
    }
    if any(
        parts[0] == "raw" and not _excluded(parts) and not _raw_name(parts[-1])
        for parts in files
    ):
        raise ValueError("e2a_admission_unsupported_raw")
    pairs = {parts for parts in raw if parts[-1].endswith(".pair.json")}
    markdown = {parts for parts in raw if parts[-1].endswith(".md")}
    sidecars = {parts for parts in raw if parts[-1].endswith(".spans.json")}
    if len(pairs) * 3 != len(raw):
        raise ValueError("e2a_admission_raw_set_invalid")
    for pair in pairs:
        slug = pair[-1].removesuffix(".pair.json")
        if (
            not slug
            or (*pair[:-1], f"{slug}.md") not in markdown
            or (*pair[:-1], f"{slug}.spans.json") not in sidecars
        ):
            raise ValueError("e2a_admission_raw_set_invalid")
    return tuple(sorted(pairs))


def _raw_name(name: str) -> bool:
    return name.endswith((".pair.json", ".md", ".spans.json"))


def _manual_fact_paths(
    files: tuple[tuple[str, ...], ...],
) -> tuple[tuple[Literal["entity", "relation", "concept"], tuple[str, ...]], ...]:
    result: list[tuple[Literal["entity", "relation", "concept"], tuple[str, ...]]] = []
    kinds = {"entities": "entity", "relations": "relation", "concepts": "concept"}
    for parts in files:
        if not parts or parts[0] not in kinds or _excluded(parts):
            continue
        if len(parts) < 2 or not parts[-1].endswith(".md"):
            raise ValueError("e2a_admission_unsupported_manual")
        result.append((kinds[parts[0]], parts))  # type: ignore[arg-type]
    return tuple(sorted(result, key=lambda value: (value[0], "/".join(value[1]))))


def _excluded(parts: tuple[str, ...]) -> bool:
    return (
        any(part.startswith(".") or part.lower() in _EXCLUDED_PARTS for part in parts)
        or parts[-1].upper().startswith("AGENT")
        or parts[-1].lower() in {"index.md", "log.md"}
    )


def _admit_pair(
    authority: _RawPairReadAuthority, pair_path: tuple[str, ...]
) -> _AdmittedPair:
    return _pair_values(pair_path, _read_admitted_raw_pair(authority, pair_path))


def _admit_pair_with_materialization_metadata(
    authority: _RawPairReadAuthority, pair_path: tuple[str, ...]
) -> tuple[_AdmittedPair, _MaterializationMetadata]:
    snapshot = _read_admitted_raw_pair(authority, pair_path)
    values = _pair_values(pair_path, snapshot)
    parent = values[0]
    return values, (
        parent.version_id,
        _source_checksum(snapshot.frontmatter),
        tuple(_materialization_span_record(span) for span in snapshot.sidecar.spans),
    )


def _read_admitted_raw_pair(
    authority: _RawPairReadAuthority, pair_path: tuple[str, ...]
) -> RawPairSnapshot:
    markdown_parts = (*pair_path[:-1], f"{pair_path[-1].removesuffix('.pair.json')}.md")
    snapshot = read_raw_pair(authority, markdown_parts)
    try:
        validate_strict_e2a_raw_frontmatter_bytes(snapshot.markdown_bytes)
    except ValueError:
        raise ValueError("e2a_admission_raw_invalid") from None
    return snapshot


def _source_checksum(frontmatter: object) -> str:
    if not isinstance(frontmatter, Mapping) or frontmatter.get("type") != "raw":
        raise ValueError("e2a_admission_raw_invalid")
    value = frontmatter.get("source_checksum")
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("e2a_admission_raw_invalid")
    return value


def _materialization_span_record(span: SpanRecord) -> dict[str, object]:
    if span.page_no is not None and (type(span.page_no) is not int or span.page_no < 1):
        raise ValueError("e2a_admission_raw_invalid")
    normalized_headings = tuple(
        _normalized_heading(value) for value in span.heading_path
    )
    heading_path = " > ".join(normalized_headings) if normalized_headings else None
    return {
        "span_id": span.span_id,
        "page_no": span.page_no,
        "heading_path": heading_path,
        "semantic_domain": heading_path or "(root)",
    }


def _normalized_heading(value: object) -> str:
    if type(value) is not str:
        raise ValueError("e2a_admission_raw_invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError("e2a_admission_raw_invalid") from None
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized:
        raise ValueError("e2a_admission_raw_invalid")
    return normalized


def _pair_values(
    pair_path: tuple[str, ...], snapshot: RawPairSnapshot
) -> tuple[E2aParent, tuple[E2aSpan, ...], dict[str, object]]:
    sidecar = snapshot.sidecar
    canonical_hash = _snapshot_hash(snapshot)
    path = "/".join(pair_path)
    parent = E2aParent(sidecar.doc_id, sidecar.version_id, path, canonical_hash)
    spans = tuple(
        E2aSpan(
            sidecar.doc_id, sidecar.version_id, span.span_id, span.offset, span.text
        )
        for span in sidecar.spans
    )
    return (
        parent,
        spans,
        {
            "kind": "raw_pair",
            "path": path,
            "identity": f"{sidecar.doc_id}:{sidecar.version_id}",
            "canonical_hash": canonical_hash,
        },
    )


def _snapshot_hash(snapshot: RawPairSnapshot) -> str:
    value = getattr(snapshot.manifest, "canonical_hash", None)
    return (
        value
        if type(value) is str and len(value) == 64
        else hashlib.sha256(
            snapshot.markdown_bytes + b"\0" + snapshot.sidecar_bytes
        ).hexdigest()
    )


def _admit_fact(
    authority: _RawPairReadAuthority,
    candidate: tuple[Literal["entity", "relation", "concept"], tuple[str, ...]],
    pairs: tuple[tuple[E2aParent, tuple[E2aSpan, ...], dict[str, object]], ...],
) -> tuple[
    E2aManualFact,
    E2aOwnershipFact | None,
    tuple[E2aEvidenceReference, ...],
    dict[str, object],
]:
    kind, parts = candidate
    try:
        content = authority.read_document(parts, MAX_E2A_MANUAL_DOCUMENT_BYTES)
        document = content.decode("utf-8", "strict")
        frontmatter, _ = load_strict_e2a_frontmatter(document)
        contract = validate_known_frontmatter(frontmatter)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("e2a_admission_manual_invalid") from None
    if contract is None or contract.type != kind:
        raise ValueError("e2a_admission_manual_type_invalid")
    fact_id, qualifiers, natural_key = _semantic_fact(contract, frontmatter)
    relative_path = "/".join(parts)
    digest = hashlib.sha256(content).hexdigest()
    fact = E2aManualFact(fact_id, kind, relative_path, digest, qualifiers, natural_key)
    if kind == "concept":
        if frontmatter.get("evidence") is not None:
            raise ValueError("e2a_admission_concept_evidence_deferred")
        ownership = None
        links: tuple[E2aEvidenceReference, ...] = ()
    else:
        ownership = E2aOwnershipFact.create(
            relative_path=relative_path,
            fact_kind=kind,
            fact_id=fact_id,
            source_digest=digest,
        )
        links = _evidence_links(frontmatter, fact, ownership, pairs)
    return (
        fact,
        ownership,
        links,
        {
            "kind": kind,
            "path": relative_path,
            "identity": fact_id,
            "source_digest": digest,
        },
    )


def _natural_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("e2a_admission_manual_invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError("e2a_admission_manual_invalid") from None
    normalized = " ".join(unicodedata.normalize("NFC", value).split()).casefold()
    if not normalized:
        raise ValueError("e2a_admission_manual_invalid")
    return normalized


def _canonical_uuid(value: object) -> str:
    if type(value) is not str:
        raise ValueError("e2a_admission_manual_invalid")
    try:
        value.encode("utf-8", "strict")
        parsed = UUID(value)
    except (TypeError, UnicodeEncodeError, ValueError):
        raise ValueError("e2a_admission_manual_invalid") from None
    if str(parsed) != value:
        raise ValueError("e2a_admission_manual_invalid")
    return value


def _semantic_fact(
    contract: object, frontmatter: Mapping[str, Any]
) -> tuple[str, Mapping[str, object], str]:
    if isinstance(contract, EntityFrontmatterContract):
        canonical_entity_id = _canonical_uuid(contract.canonical_entity_id)
        natural_key = canonical_json(
            {
                "title": _natural_string(contract.title),
                "entity_type": _natural_string(contract.entity_type),
            }
        )
        fact_id = deterministic_id("entity", natural_key)
        if canonical_entity_id != fact_id:
            raise ValueError("e2a_admission_entity_id_mismatch")
        return fact_id, {}, natural_key
    if isinstance(contract, RelationFrontmatterContract):
        subject_entity_id = _canonical_uuid(contract.subject_entity_id)
        object_entity_id = _canonical_uuid(contract.object_entity_id)
        natural_key = canonical_json(
            {
                "subject_entity_id": subject_entity_id,
                "predicate": _natural_string(contract.predicate),
                "object_entity_id": object_entity_id,
            }
        )
        values = {
            key: frontmatter[key]
            for key in (
                "negation",
                "condition",
                "direction",
                "confidence",
                "qualifiers",
            )
            if key in frontmatter
        }
        return deterministic_id("relation", natural_key), values, natural_key
    if isinstance(contract, ConceptFrontmatterContract):
        natural_key = _natural_string(contract.title)
        return deterministic_id("concept", natural_key), {}, natural_key
    raise ValueError("e2a_admission_manual_invalid")


def _evidence_links(
    frontmatter: Mapping[str, Any],
    fact: E2aManualFact,
    ownership: E2aOwnershipFact,
    pairs: tuple[tuple[E2aParent, tuple[E2aSpan, ...], dict[str, object]], ...],
) -> tuple[E2aEvidenceReference, ...]:
    supplied = frontmatter.get("evidence")
    if supplied is None:
        return ()
    if type(supplied) is not list:
        raise ValueError("e2a_admission_evidence_invalid")
    spans = {
        (span.document_id, span.version_id, span.span_id)
        for _, group, _ in pairs
        for span in group
    }
    result: list[E2aEvidenceReference] = []
    seen: set[tuple[str, str, str]] = set()
    for item in supplied:
        if type(item) is not dict or set(item) != {
            "document_id",
            "version_id",
            "span_id",
        }:
            raise ValueError("e2a_admission_evidence_invalid")
        try:
            document_id = _canonical_uuid(item["document_id"])
            version_id = _canonical_uuid(item["version_id"])
            span_id = _canonical_uuid(item["span_id"])
            evidence = E2aEvidenceObject.create(
                version_id=version_id,
                entity_id=fact.fact_id if fact.fact_kind == "entity" else None,
                relation_id=fact.fact_id if fact.fact_kind == "relation" else None,
            )
            reference = E2aEvidenceReference(
                document_id,
                version_id,
                span_id,
                fact.fact_id if fact.fact_kind == "entity" else None,
                fact.fact_id if fact.fact_kind == "relation" else None,
                evidence.evidence_id,
                ownership.ownership_id,
                ownership.scope_version_id,
            )
        except (TypeError, UnicodeEncodeError, ValueError):
            raise ValueError("e2a_admission_evidence_invalid") from None
        key = (reference.document_id, reference.version_id, reference.span_id)
        if key in seen:
            raise ValueError("e2a_admission_evidence_invalid")
        if key not in spans:
            raise ValueError("e2a_admission_evidence_unresolved")
        seen.add(key)
        result.append(reference)
    return tuple(result)


def _desired_state(
    admitted_pairs: tuple[
        tuple[E2aParent, tuple[E2aSpan, ...], dict[str, object]], ...
    ],
    admitted_facts: tuple[
        tuple[
            E2aManualFact,
            E2aOwnershipFact | None,
            tuple[E2aEvidenceReference, ...],
            dict[str, object],
        ],
        ...,
    ],
) -> E2aDesiredState:
    parents = tuple(
        sorted(
            (item[0] for item in admitted_pairs),
            key=lambda value: (
                value.relative_path,
                value.document_id,
                value.version_id,
            ),
        )
    )
    spans = tuple(
        sorted(
            (span for _, group, _ in admitted_pairs for span in group),
            key=lambda value: (value.version_id, value.offset, value.span_id),
        )
    )
    facts = _canonical_facts(tuple(item[0] for item in admitted_facts))
    ownership = tuple(
        sorted(
            (item[1] for item in admitted_facts if item[1] is not None),
            key=lambda value: (value.fact_kind, value.relative_path, value.fact_id),
        )
    )
    artifacts = sorted(
        (item[2] for item in admitted_pairs), key=_artifact_order
    ) + sorted((item[3] for item in admitted_facts), key=_artifact_order)
    evidence_links = tuple(
        sorted(
            (link for _, _, links, _ in admitted_facts for link in links),
            key=lambda value: value.evidence_link_id,
        )
    )
    evidence_objects = tuple(
        sorted(
            {
                E2aEvidenceObject.create(
                    version_id=link.version_id,
                    entity_id=link.entity_id,
                    relation_id=link.relation_id,
                )
                for link in evidence_links
            },
            key=lambda value: value.evidence_id,
        )
    )
    manifest = {"schema": "e2a-corpus-v1", "artifacts": artifacts}
    _reject_duplicates(parents, spans, facts, ownership)
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=parents,
        canonical_spans=spans,
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=tuple(fact for fact in facts if fact.fact_kind == "entity"),
        manual_relations=tuple(fact for fact in facts if fact.fact_kind == "relation"),
        manual_concepts=tuple(fact for fact in facts if fact.fact_kind == "concept"),
        evidence_objects=evidence_objects,
        evidence_links=evidence_links,
        ownership_facts=ownership,
        sync_state_rows=(),
        validation_metadata={
            "raw_pair_protocol": "M-D-S-M",
            "derived_materialization": "deferred_wave2",
        },
        provenance_metadata={"authority": "okf", "schema": "e2a"},
    )


def _artifact_order(value: dict[str, object]) -> tuple[str, str, str]:
    return str(value["kind"]), str(value["path"]), str(value["identity"])


def _canonical_facts(
    facts: tuple[E2aManualFact, ...],
) -> tuple[E2aManualFact, ...]:
    """Keep one semantic fact while retaining each source as ownership provenance."""
    canonical: dict[str, E2aManualFact] = {}
    for fact in facts:
        existing = canonical.get(fact.fact_id)
        if existing is None:
            canonical[fact.fact_id] = fact
            continue
        if (
            existing.fact_kind != fact.fact_kind
            or existing.natural_key != fact.natural_key
        ):
            raise ValueError("e2a_admission_natural_key_collision")
        qualifiers_match = (
            _jsonb_qualifiers_equal(existing.qualifiers, fact.qualifiers)
            if fact.fact_kind == "relation"
            else existing.qualifiers == fact.qualifiers
        )
        if not qualifiers_match:
            raise ValueError("e2a_admission_natural_key_collision")
        if fact.fact_kind == "concept":
            raise ValueError("e2a_admission_duplicate_concept_fact")
    return tuple(canonical.values())


def _jsonb_qualifiers_equal(left: object, right: object) -> bool:
    """Compare admitted relation qualifiers with JSONB equality semantics."""
    if left is None or right is None:
        return left is None and right is None
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if type(left) in {int, float} or type(right) in {int, float}:
        return _jsonb_numbers_equal(left, right)
    if type(left) is str or type(right) is str:
        return type(left) is str and type(right) is str and left == right
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return _jsonb_mappings_equal(left, right)
    if type(left) in {list, tuple} or type(right) in {list, tuple}:
        return _jsonb_sequences_equal(left, right)
    return False


def _jsonb_numbers_equal(left: object, right: object) -> bool:
    if type(left) not in {int, float} or type(right) not in {int, float}:
        return False
    if (type(left) is float and not math.isfinite(left)) or (
        type(right) is float and not math.isfinite(right)
    ):
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return False


def _jsonb_mappings_equal(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if any(type(key) is not str for key in left) or any(
        type(key) is not str for key in right
    ):
        return False
    if left.keys() != right.keys():
        return False
    return all(_jsonb_qualifiers_equal(left[key], right[key]) for key in left)


def _jsonb_sequences_equal(left: object, right: object) -> bool:
    if type(left) not in {list, tuple} or type(right) not in {list, tuple}:
        return False
    assert isinstance(left, (list, tuple)) and isinstance(right, (list, tuple))
    return len(left) == len(right) and all(
        _jsonb_qualifiers_equal(left_item, right_item)
        for left_item, right_item in zip(left, right, strict=True)
    )


def _reject_duplicates(
    parents: tuple[E2aParent, ...],
    spans: tuple[E2aSpan, ...],
    facts: tuple[E2aManualFact, ...],
    ownership: tuple[E2aOwnershipFact, ...],
) -> None:
    if len({value.version_id for value in parents}) != len(parents):
        raise ValueError("duplicate parent version")
    parent_keys = {(value.document_id, value.version_id) for value in parents}
    if any((value.document_id, value.version_id) not in parent_keys for value in spans):
        raise ValueError("canonical span does not match an admitted parent")
    if len({value.span_id for value in spans}) != len(spans):
        raise ValueError("duplicate span identity")
    if len({value.fact_id for value in facts}) != len(facts) or len(
        {value.ownership_id for value in ownership}
    ) != len(ownership):
        raise ValueError("duplicate manual fact identity")
    by_key: dict[tuple[str, str], E2aManualFact] = {}
    for fact in facts:
        key = (fact.fact_kind, fact.natural_key)
        existing = by_key.get(key)
        if existing is not None and (
            existing.fact_id != fact.fact_id or existing.qualifiers != fact.qualifiers
        ):
            raise ValueError("e2a_admission_natural_key_collision")
        by_key[key] = fact


__all__ = [
    "E2aCorpusAdmitter",
    "admit_e2a_corpus",
    "admit_e2a_materialization_input",
    "admit_e2a_corpus_hash",
]
