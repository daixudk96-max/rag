"""Pure E2a materialization input and desired-state building."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast
from uuid import UUID

from .e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json,
    deterministic_id,
)


def _get_tree_generator() -> type:
    """Get TreeGenerator class at runtime for monkeypatch compatibility.

    Tests monkeypatch e2a_reconciler.TreeGenerator, so we must access it
    at runtime, not at import time.
    """
    from .e2a_reconciler import TreeGenerator

    return TreeGenerator


_PERSISTED_TREE_NODE_FIELDS = (
    "node_id",
    "version_id",
    "parent_node_id",
    "node_type",
    "level_no",
    "title",
    "heading_path",
    "page_start",
    "page_end",
    "summary_text",
)
_TREE_NODE_FIELDS = frozenset(_PERSISTED_TREE_NODE_FIELDS)
_TREE_LINK_FIELDS = frozenset({"node_id", "span_id", "ordinal_no"})


@dataclass(frozen=True)
class E2aMaterializationInput:
    """An immutable boundary between admission and pure materialization."""

    admitted: E2aDesiredState
    span_records: tuple[Mapping[str, object], ...]
    parent_source_checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        if type(self.span_records) not in {tuple, list}:
            raise ValueError("materialization input span records must be a tuple")
        if not isinstance(self.parent_source_checksums, Mapping):
            raise ValueError("materialization input source checksums must be a mapping")
        object.__setattr__(
            self,
            "span_records",
            tuple(_freeze_record(record) for record in self.span_records),
        )
        frozen_checksums: dict[str, str] = {}
        for key, checksum in self.parent_source_checksums.items():
            if type(key) is not str:
                raise ValueError(
                    "materialization input mapping key must be an exact str"
                )
            try:
                key.encode("utf-8", "strict")
            except UnicodeEncodeError:
                raise ValueError(
                    "materialization input mapping key must be valid UTF-8"
                ) from None
            frozen_checksums[key] = checksum
        object.__setattr__(
            self,
            "parent_source_checksums",
            MappingProxyType(frozen_checksums),
        )


@dataclass(frozen=True)
class E2aDesiredStateBuilder:
    """Derive deterministic chunks and trees without database capability."""

    embed_text: Callable[[str], object]

    def __post_init__(self) -> None:
        if not callable(self.embed_text):
            raise TypeError("embed_text must be callable")

    def build(self, source: object) -> E2aDesiredState:
        if type(source) is not E2aMaterializationInput:
            raise TypeError("materialization input must be E2aMaterializationInput")
        if type(source.admitted) is not E2aDesiredState:
            raise ValueError("materialization input admitted state is invalid")
        parents = tuple(
            sorted(
                source.admitted.parents,
                key=lambda parent: (
                    parent.relative_path,
                    parent.document_id,
                    parent.version_id,
                ),
            )
        )
        source_checksums = _validate_source_checksums(source, parents)
        spans = tuple(
            sorted(
                source.admitted.canonical_spans,
                key=lambda span: (span.version_id, span.offset, span.span_id),
            )
        )
        records = _validate_span_records(source.span_records, spans)
        nodes, node_links = self._derive_tree(parents, spans, records)
        _validate_tree_span_ownership(spans, nodes, node_links)
        chunks, chunk_links = self._derive_chunks(spans, records, node_links)
        sync_rows = _sync_rows(
            source.admitted.sync_state_rows, parents, source_checksums
        )
        provenance = {
            **source.admitted.provenance_metadata,
            "parent_source_checksums": source_checksums,
        }
        return E2aDesiredState(
            corpus_manifest=source.admitted.corpus_manifest,
            corpus_manifest_sha256=source.admitted.corpus_manifest_sha256,
            parents=parents,
            canonical_spans=spans,
            vector_chunks=chunks,
            vector_chunk_span_links=chunk_links,
            tree_nodes=nodes,
            tree_node_span_links=node_links,
            manual_entities=source.admitted.manual_entities,
            manual_relations=source.admitted.manual_relations,
            manual_concepts=source.admitted.manual_concepts,
            evidence_objects=source.admitted.evidence_objects,
            evidence_links=source.admitted.evidence_links,
            ownership_facts=source.admitted.ownership_facts,
            sync_state_rows=sync_rows,
            validation_metadata=source.admitted.validation_metadata,
            provenance_metadata=provenance,
        )

    def _derive_tree(
        self,
        parents: tuple[E2aParent, ...],
        spans: tuple[E2aSpan, ...],
        records: Mapping[str, Mapping[str, object]],
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        spans_by_version: dict[str, list[dict[str, object]]] = {
            parent.version_id: [] for parent in parents
        }
        for span in spans:
            record = records[span.span_id]
            spans_by_version[span.version_id].append(
                {
                    "span_id": UUID(span.span_id),
                    "version_id": UUID(span.version_id),
                    "start_offset": span.offset,
                    "page_no": record["page_no"],
                    "heading_path": record["heading_path"],
                    "semantic_domain": record["semantic_domain"],
                    "raw_text": span.text,
                }
            )
        nodes: list[object] = []
        links: list[object] = []
        generator = _get_tree_generator()()
        for parent in parents:
            generator_spans = sorted(
                spans_by_version[parent.version_id],
                key=lambda value: (
                    cast(int, value["start_offset"]),
                    str(value["span_id"]),
                ),
            )
            tree = generator.generate_tree(
                generator_spans, version_id=UUID(parent.version_id)
            )
            nodes.extend(_project_tree_node(row) for row in tree["nodes"])
            links.extend(_project_tree_link(row) for row in tree["node_spans"])
        return (
            tuple(sorted(nodes, key=_tree_node_sort_key)),
            tuple(sorted(links, key=_tree_link_sort_key)),
        )

    def _derive_chunks(
        self,
        spans: tuple[E2aSpan, ...],
        records: Mapping[str, Mapping[str, object]],
        node_links: tuple[object, ...],
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        node_by_span = {
            str(row["span_id"]): str(row["node_id"])
            for value in node_links
            if isinstance(value, Mapping)
            for row in (value,)
        }
        chunks: list[dict[str, object]] = []
        links: list[dict[str, object]] = []
        orders: dict[str, int] = {}
        for span in spans:
            order = orders.get(span.version_id, 0)
            orders[span.version_id] = order + 1
            record = records[span.span_id]
            chunk_id = deterministic_id(
                "vector_chunk",
                canonical_json(
                    {"span_id": span.span_id, "version_id": span.version_id}
                ),
            )
            node_id = node_by_span.get(span.span_id)
            if node_id is None:
                raise ValueError("tree derivation did not cover canonical span")
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "version_id": span.version_id,
                    "chunk_type": "canonical_span",
                    "chunk_order": order,
                    "token_count": len(span.text.split()),
                    "text_preview": span.text,
                    "page_no": record["page_no"],
                    "heading_path": record["heading_path"],
                    "node_id": node_id,
                    "embedding": _embedding(self.embed_text(span.text)),
                }
            )
            links.append(
                {"chunk_id": chunk_id, "span_id": span.span_id, "ordinal_no": 0}
            )
        ordered_chunks = tuple(sorted(chunks, key=lambda row: str(row["chunk_id"])))
        ordered_links = tuple(
            sorted(links, key=lambda row: (str(row["chunk_id"]), row["ordinal_no"]))
        )
        return ordered_chunks, ordered_links


def _freeze_record(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("materialization input span record must be a mapping")
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise ValueError("materialization input mapping key must be an exact str")
        try:
            key.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise ValueError(
                "materialization input mapping key must be valid UTF-8"
            ) from None
        frozen[key] = _freeze_value(item)
    return MappingProxyType(frozen)


def _freeze_value(value: object) -> object:
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(
                    "materialization input mapping key must be an exact str"
                )
            try:
                key.encode("utf-8", "strict")
            except UnicodeEncodeError:
                raise ValueError(
                    "materialization input mapping key must be valid UTF-8"
                ) from None
            frozen[key] = _freeze_value(item)
        return MappingProxyType(frozen)
    if type(value) is tuple:
        values: Iterable[object] = value
    elif type(value) is list:
        values = value
    else:
        raise ValueError("materialization input contains an unsupported value")
    return tuple(_freeze_value(item) for item in values)


def _validate_source_checksums(
    source: E2aMaterializationInput, parents: tuple[E2aParent, ...]
) -> dict[str, str]:
    expected = {parent.version_id for parent in parents}
    supplied = source.parent_source_checksums
    if set(supplied) != expected or len(supplied) != len(parents):
        raise ValueError("one source checksum is required for every parent")
    result: dict[str, str] = {}
    for version_id, checksum in supplied.items():
        if type(version_id) is not str or type(checksum) is not str:
            raise ValueError("source checksum is invalid")
        if len(checksum) != 64 or any(
            char not in "0123456789abcdef" for char in checksum
        ):
            raise ValueError("source checksum is invalid")
        result[version_id] = checksum
    return dict(sorted(result.items()))


def _validate_span_records(
    records: tuple[Mapping[str, object], ...], spans: tuple[E2aSpan, ...]
) -> Mapping[str, Mapping[str, object]]:
    known = {span.span_id: span for span in spans}
    validated: dict[str, Mapping[str, object]] = {}
    required = {"span_id", "heading_path", "page_no", "semantic_domain"}
    optional = {"document_id", "version_id"}
    for record in records:
        if (
            not isinstance(record, Mapping)
            or not required <= set(record)
            or set(record) - required - optional
        ):
            raise ValueError("span record metadata is invalid")
        span_id = record["span_id"]
        if type(span_id) is not str or span_id not in known or span_id in validated:
            raise ValueError("span record is unknown or duplicated")
        span = known[span_id]
        if (
            record.get("document_id", span.document_id) != span.document_id
            or record.get("version_id", span.version_id) != span.version_id
        ):
            raise ValueError("span record crosses an admitted parent")
        raw_page_no = record["page_no"]
        page_no: int | None
        if raw_page_no is None:
            page_no = None
        elif (
            isinstance(raw_page_no, int)
            and type(raw_page_no) is not bool
            and raw_page_no >= 1
        ):
            page_no = raw_page_no
        else:
            raise ValueError("span record page metadata is invalid")
        heading_path = _metadata_text(record["heading_path"], "heading", nullable=True)
        semantic_domain = _metadata_text(record["semantic_domain"], "semantic domain")
        if semantic_domain is None:
            raise ValueError("span record semantic domain metadata is invalid")
        validated[span_id] = MappingProxyType(
            {
                "span_id": span_id,
                "page_no": page_no,
                "heading_path": heading_path,
                "semantic_domain": semantic_domain.casefold(),
            }
        )
    if set(validated) != set(known):
        raise ValueError("span record is missing for an admitted canonical span")
    return MappingProxyType(validated)


def _metadata_text(value: object, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str:
        raise ValueError(f"span record {name} metadata is invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError(f"span record {name} metadata is invalid") from None
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized:
        raise ValueError(f"span record {name} metadata is invalid")
    return normalized


def _embedding(value: object) -> tuple[float, ...]:
    try:
        values: tuple[object, ...] = tuple(cast(Iterable[object], value))
    except TypeError:
        raise ValueError("embedding must be a finite 16-dimensional vector") from None
    if len(values) != 16:
        raise ValueError("embedding must be a finite 16-dimensional vector")
    converted: list[float] = []
    for item in values:
        if type(item) is int:
            numeric_item: int | float = cast(int, item)
        elif type(item) is float:
            numeric_item = cast(float, item)
        else:
            raise ValueError("embedding must be finite")
        numeric_value = float(numeric_item)
        if not math.isfinite(numeric_value):
            raise ValueError("embedding must be finite")
        converted.append(numeric_value)
    return tuple(converted)


def _project_tree_node(row: object) -> Mapping[str, object]:
    if not isinstance(row, Mapping):
        raise ValueError("tree generator node is invalid")
    fields = frozenset(row)
    unexpected = fields - _TREE_NODE_FIELDS - {"cluster_id"}
    if unexpected or not _TREE_NODE_FIELDS <= fields:
        raise ValueError("tree generator node has unsupported fields")
    return _json_row({field: row[field] for field in _PERSISTED_TREE_NODE_FIELDS})


def _project_tree_link(row: object) -> Mapping[str, object]:
    if not isinstance(row, Mapping) or frozenset(row) != _TREE_LINK_FIELDS:
        raise ValueError("tree generator span link is invalid")
    return _json_row(row)


def _tree_node_sort_key(value: object) -> tuple[int, str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("tree generator node is invalid")
    level_no = value["level_no"]
    if type(level_no) is not int:
        raise ValueError("tree generator node is invalid")
    return level_no, str(value["heading_path"]), str(value["node_id"])


def _tree_link_sort_key(value: object) -> tuple[str, int, str]:
    if not isinstance(value, Mapping):
        raise ValueError("tree generator span link is invalid")
    ordinal_no = value["ordinal_no"]
    if type(ordinal_no) is not int:
        raise ValueError("tree generator span link is invalid")
    return str(value["node_id"]), ordinal_no, str(value["span_id"])


def _validate_tree_span_ownership(
    spans: tuple[E2aSpan, ...], nodes: tuple[object, ...], links: tuple[object, ...]
) -> None:
    span_versions = {span.span_id: span.version_id for span in spans}
    node_versions: dict[str, str] = {}
    for value in nodes:
        if not isinstance(value, Mapping):
            raise ValueError("tree generator node is invalid")
        node_id, version_id = value["node_id"], value["version_id"]
        if type(node_id) is not str or type(version_id) is not str:
            raise ValueError("tree generator node is invalid")
        if node_id in node_versions:
            raise ValueError("tree generator emitted duplicate node identity")
        node_versions[node_id] = version_id
    owner_by_span: dict[str, str] = {}
    for value in links:
        if not isinstance(value, Mapping):
            raise ValueError("tree generator span link is invalid")
        node_id, span_id, ordinal_no = (
            value["node_id"],
            value["span_id"],
            value["ordinal_no"],
        )
        if (
            type(node_id) is not str
            or type(span_id) is not str
            or type(ordinal_no) is not int
            or ordinal_no < 0
            or node_versions.get(node_id) != span_versions.get(span_id)
        ):
            raise ValueError("tree generator span link is invalid")
        if span_id in owner_by_span:
            raise ValueError("canonical span has multiple tree node owners")
        owner_by_span[span_id] = node_id
    if set(owner_by_span) != set(span_versions):
        raise ValueError("tree derivation did not cover canonical span")


def _json_row(row: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in row.items()
        }
    )


def _sync_rows(
    existing: tuple[object, ...],
    parents: tuple[E2aParent, ...],
    checksums: Mapping[str, str],
) -> tuple[object, ...]:
    retained = [value for value in existing if isinstance(value, Mapping)]
    generated = [
        {
            "okf_file_path": parent.relative_path,
            "doc_id": parent.document_id,
            "version_id": parent.version_id,
            "source_checksum": checksums[parent.version_id],
            "canonical_hash": parent.canonical_hash,
            "status": "materialized",
            "materialization_owner": "e2a",
        }
        for parent in parents
    ]
    by_path = {
        str(value.get("okf_file_path")): value
        for value in retained
        if type(value.get("okf_file_path")) is str
    }
    by_path.update({str(value["okf_file_path"]): value for value in generated})
    return tuple(by_path[path] for path in sorted(by_path))


__all__ = ["E2aDesiredStateBuilder", "E2aMaterializationInput"]
