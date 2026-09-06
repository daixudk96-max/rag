"""Private graph validation helpers for immutable E2a contracts.

This module intentionally depends only on contract primitives.  Public E2a DTOs
remain defined by :mod:`e2a_contracts`, which supplies deterministic identity
functions to these helpers without creating a reverse import.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from .e2a_contract_primitives import _digest, _path, _uuid


class _Parent(Protocol):
    @property
    def document_id(self) -> str: ...

    @property
    def version_id(self) -> str: ...

    @property
    def relative_path(self) -> str: ...

    @property
    def canonical_hash(self) -> str: ...


class _Span(Protocol):
    @property
    def document_id(self) -> str: ...

    @property
    def version_id(self) -> str: ...

    @property
    def span_id(self) -> str: ...


class _Fact(Protocol):
    @property
    def fact_id(self) -> str: ...

    @property
    def fact_kind(self) -> str: ...

    @property
    def relative_path(self) -> str: ...

    @property
    def source_digest(self) -> str: ...


class _Ownership(Protocol):
    @property
    def ownership_id(self) -> str: ...

    @property
    def relative_path(self) -> str: ...

    @property
    def fact_kind(self) -> str: ...

    @property
    def fact_id(self) -> str: ...

    @property
    def source_digest(self) -> str: ...

    @property
    def document_id(self) -> str | None: ...

    @property
    def version_id(self) -> str | None: ...

    @property
    def scope_version_id(self) -> str: ...


class _EvidenceObject(Protocol):
    @property
    def evidence_id(self) -> str: ...

    @property
    def version_id(self) -> str: ...

    @property
    def entity_id(self) -> str | None: ...

    @property
    def relation_id(self) -> str | None: ...


class _EvidenceLink(Protocol):
    @property
    def document_id(self) -> str: ...

    @property
    def version_id(self) -> str: ...

    @property
    def span_id(self) -> str | None: ...

    @property
    def entity_id(self) -> str | None: ...

    @property
    def relation_id(self) -> str | None: ...

    @property
    def evidence_id(self) -> str: ...

    @property
    def ownership_id(self) -> str: ...

    @property
    def ownership_scope_version_id(self) -> str: ...

    @property
    def source_kind(self) -> Literal["manual_okf"]: ...

    @property
    def confidence(self) -> None: ...

    @property
    def target_kind(self) -> Literal["entity", "relation"]: ...

    @property
    def target_id(self) -> str: ...

    @property
    def manual_entity_id(self) -> str | None: ...

    @property
    def manual_relation_id(self) -> str | None: ...

    @property
    def evidence_link_id(self) -> str: ...


@dataclass(frozen=True)
class _Artifacts:
    raw_pairs: frozenset[tuple[str, str, str, str]]
    manual: frozenset[tuple[str, str, str, str]]
    concepts: frozenset[tuple[str, str, str, str]]


def _evidence_target(
    entity_id: str | None, relation_id: str | None
) -> tuple[Literal["entity", "relation"], str]:
    if (entity_id is None) == (relation_id is None):
        raise ValueError(
            "manual evidence requires exactly one entity or relation target"
        )
    if entity_id is not None:
        _uuid(entity_id, "entity_id")
        return "entity", entity_id
    if relation_id is None:
        raise ValueError(
            "manual evidence requires exactly one entity or relation target"
        )
    _uuid(relation_id, "relation_id")
    return "relation", relation_id


def _manual_evidence_link_id(
    *,
    evidence_id: str,
    ownership_id: str,
    ownership_scope_version_id: str,
    span_id: str,
    target_id: str,
    target_kind: Literal["entity", "relation"],
    version_id: str,
    canonical_json: Callable[[object], str],
    deterministic_id: Callable[[str, str], str],
) -> str:
    return deterministic_id(
        "manual_evidence_link",
        canonical_json(
            {
                "evidence_id": evidence_id,
                "ownership_id": ownership_id,
                "ownership_scope_version_id": ownership_scope_version_id,
                "source_kind": "manual_okf",
                "span_id": span_id,
                "target_id": target_id,
                "target_kind": target_kind,
                "version_id": version_id,
            }
        ),
    )


def _validate_ownership_fields(
    relative_path: object,
    fact_kind: object,
    fact_id: object,
    source_digest: object,
    document_id: object,
    version_id: object,
) -> None:
    _path(relative_path)
    _uuid(fact_id, "fact_id")
    _digest(source_digest, "source_digest")
    if type(fact_kind) is not str or fact_kind not in {"entity", "relation"}:
        raise ValueError("ownership fact kind is unsupported")
    if (document_id is None) != (version_id is None):
        raise ValueError("ownership scope requires document and version together")
    if document_id is not None:
        _uuid(document_id, "document_id")
        _uuid(version_id, "version_id")


def _artifacts(manifest: Mapping[str, object]) -> _Artifacts:
    value = manifest.get("artifacts")
    if value is None:
        return _Artifacts(frozenset(), frozenset(), frozenset())
    artifacts: Iterable[object]
    artifact_count: int
    if type(value) is tuple:
        artifacts = value
        artifact_count = len(value)
    elif type(value) is list:
        artifacts = value
        artifact_count = len(value)
    else:
        raise ValueError("corpus manifest artifacts are invalid")
    raw_pairs: set[tuple[str, str, str, str]] = set()
    manual: set[tuple[str, str, str, str]] = set()
    concepts: set[tuple[str, str, str, str]] = set()
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ValueError("corpus manifest artifacts are invalid")
        kind = item.get("kind")
        path = item.get("path")
        identity = item.get("identity")
        if not all(type(value) is str for value in (kind, path, identity)):
            raise ValueError("corpus manifest artifacts are invalid")
        if kind == "raw_pair":
            if set(item) != {"kind", "path", "identity", "canonical_hash"}:
                raise ValueError("corpus manifest artifacts are invalid")
            digest = item.get("canonical_hash")
            _path(path)
            _digest(digest, "canonical_hash")
            raw_pair: tuple[str, str, str, str] = cast(
                tuple[str, str, str, str], (path, kind, identity, digest)
            )
            raw_pairs.add(raw_pair)
        elif kind in {"entity", "relation", "concept"}:
            if set(item) != {"kind", "path", "identity", "source_digest"}:
                raise ValueError("corpus manifest artifacts are invalid")
            digest = item.get("source_digest")
            _path(path)
            _uuid(identity, "artifact identity")
            _digest(digest, "artifact source digest")
            target: tuple[str, str, str, str] = cast(
                tuple[str, str, str, str], (path, kind, identity, digest)
            )
            (concepts if kind == "concept" else manual).add(target)
        else:
            raise ValueError("corpus manifest artifacts are invalid")
    if artifact_count != len(raw_pairs) + len(manual) + len(concepts):
        raise ValueError("duplicate corpus artifact")
    return _Artifacts(frozenset(raw_pairs), frozenset(manual), frozenset(concepts))


def _validate_ownership_graph(
    manifest: Mapping[str, object],
    parents: tuple[_Parent, ...],
    facts: tuple[_Fact, ...],
    ownership: tuple[_Ownership, ...],
) -> None:
    artifacts = _artifacts(manifest)
    expected_raw_pairs = {
        (
            parent.relative_path,
            "raw_pair",
            f"{parent.document_id}:{parent.version_id}",
            parent.canonical_hash,
        )
        for parent in parents
    }
    if (
        len(expected_raw_pairs) != len(parents)
        or artifacts.raw_pairs != expected_raw_pairs
    ):
        raise ValueError("raw-pair artifact does not match exactly one parent")

    facts_by_id = {fact.fact_id: fact for fact in facts}
    parent_keys = {(parent.document_id, parent.version_id) for parent in parents}
    owner_tuples: list[tuple[str, str, str, str]] = []
    owners_by_fact: dict[str, int] = {}
    for owner in ownership:
        fact = facts_by_id.get(owner.fact_id)
        if fact is None or fact.fact_kind not in {"entity", "relation"}:
            raise ValueError("ownership requires an admitted entity or relation")
        if owner.fact_kind != fact.fact_kind:
            raise ValueError("ownership kind does not match admitted manual fact")
        artifact = (
            owner.relative_path,
            owner.fact_kind,
            owner.fact_id,
            owner.source_digest,
        )
        if artifact not in artifacts.manual:
            raise ValueError("ownership does not match admitted manual provenance")
        owner_tuples.append(artifact)
        owners_by_fact[owner.fact_id] = owners_by_fact.get(owner.fact_id, 0) + 1
        if (
            owner.document_id is not None
            and (
                owner.document_id,
                owner.version_id,
            )
            not in parent_keys
        ):
            raise ValueError("ownership scope does not match an admitted parent")

    for fact in facts:
        if fact.fact_kind in {"entity", "relation"} and not owners_by_fact.get(
            fact.fact_id
        ):
            raise ValueError("manual fact requires an admitted ownership")
    if len(set(owner_tuples)) != len(owner_tuples):
        raise ValueError("duplicate ownership provenance")
    if set(owner_tuples) != artifacts.manual:
        raise ValueError("manual artifact does not have exactly one ownership")
    if any(
        (fact.relative_path, fact.fact_kind, fact.fact_id, fact.source_digest)
        not in artifacts.manual
        for fact in facts
        if fact.fact_kind in {"entity", "relation"}
    ):
        raise ValueError("manual fact representative provenance is not admitted")

    concepts = tuple(fact for fact in facts if fact.fact_kind == "concept")
    expected_concepts = {
        (fact.relative_path, fact.fact_kind, fact.fact_id, fact.source_digest)
        for fact in concepts
    }
    if (
        len(expected_concepts) != len(concepts)
        or artifacts.concepts != expected_concepts
    ):
        raise ValueError("concept artifact does not match exactly one concept fact")


def _validate_evidence_graph(
    *,
    parents: tuple[_Parent, ...],
    spans: tuple[_Span, ...],
    facts: tuple[_Fact, ...],
    ownership: tuple[_Ownership, ...],
    objects: tuple[_EvidenceObject, ...],
    links: tuple[_EvidenceLink, ...],
    canonical_json: Callable[[object], str],
    deterministic_id: Callable[[str, str], str],
    global_scope_version_id: str,
) -> None:
    object_ids = [value.evidence_id for value in objects]
    target_versions = [
        (value.version_id, value.entity_id, value.relation_id) for value in objects
    ]
    link_ids = [value.evidence_link_id for value in links]
    link_graph = [
        (
            value.evidence_id,
            value.document_id,
            value.version_id,
            value.span_id,
            value.entity_id,
            value.relation_id,
            value.ownership_id,
            value.ownership_scope_version_id,
            value.source_kind,
        )
        for value in links
    ]
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("duplicate evidence object identity")
    if len(set(target_versions)) != len(target_versions):
        raise ValueError("duplicate evidence target version identity")
    if len(set(link_ids)) != len(link_ids):
        raise ValueError("duplicate evidence link identity")
    if len(set(link_graph)) != len(link_graph):
        raise ValueError("duplicate evidence link graph identity")

    facts_by_id = {value.fact_id: value for value in facts}
    owners_by_id = {value.ownership_id: value for value in ownership}
    parent_keys = {(value.document_id, value.version_id) for value in parents}
    parent_versions = {value.version_id for value in parents}
    object_by_id = {value.evidence_id: value for value in objects}
    span_keys = {
        (value.document_id, value.version_id, value.span_id) for value in spans
    }
    for evidence in objects:
        target_kind, target_id = _evidence_target(
            evidence.entity_id, evidence.relation_id
        )
        fact = facts_by_id.get(target_id)
        if fact is None or fact.fact_kind != target_kind:
            raise ValueError("evidence object requires an admitted manual target")
        if evidence.version_id not in parent_versions:
            raise ValueError("evidence object requires an admitted parent version")

    for link in links:
        target_kind, target_id = _evidence_target(link.entity_id, link.relation_id)
        span_id = link.span_id
        if span_id is None:
            raise ValueError("evidence link requires a span")
        expected_id = _manual_evidence_link_id(
            evidence_id=link.evidence_id,
            ownership_id=link.ownership_id,
            ownership_scope_version_id=link.ownership_scope_version_id,
            span_id=span_id,
            target_id=target_id,
            target_kind=target_kind,
            version_id=link.version_id,
            canonical_json=canonical_json,
            deterministic_id=deterministic_id,
        )
        if link.evidence_link_id != expected_id:
            raise ValueError("evidence link identity does not match graph")
        if (
            link.source_kind != "manual_okf"
            or link.confidence is not None
            or link.target_kind != target_kind
            or link.target_id != target_id
            or link.manual_entity_id != link.entity_id
            or link.manual_relation_id != link.relation_id
        ):
            raise ValueError("evidence link projection does not match graph")
        linked_evidence = object_by_id.get(link.evidence_id)
        if linked_evidence is None:
            raise ValueError("evidence link requires an admitted evidence object")
        if (
            linked_evidence.version_id != link.version_id
            or linked_evidence.entity_id != link.entity_id
            or linked_evidence.relation_id != link.relation_id
        ):
            raise ValueError(
                "evidence link does not match its admitted evidence object"
            )
        if (link.document_id, link.version_id, link.span_id) not in span_keys:
            raise ValueError("evidence link does not match an admitted canonical span")
        if (link.document_id, link.version_id) not in parent_keys:
            raise ValueError("evidence link does not match an admitted parent")
        owner = owners_by_id.get(link.ownership_id)
        if owner is None:
            raise ValueError("evidence link requires an admitted ownership")
        if owner.fact_kind != target_kind or owner.fact_id != target_id:
            raise ValueError("evidence link target does not match ownership")
        if link.ownership_scope_version_id != owner.scope_version_id:
            raise ValueError("evidence link scope does not match ownership")
        if owner.scope_version_id != global_scope_version_id and (
            owner.scope_version_id != link.version_id
            or owner.document_id != link.document_id
            or owner.version_id != link.version_id
        ):
            raise ValueError("evidence link scope does not match its parent version")

    linked_evidence_ids = {value.evidence_id for value in links}
    if any(value.evidence_id not in linked_evidence_ids for value in objects):
        raise ValueError("evidence object requires a span-backed link")
