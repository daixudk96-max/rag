"""LightRAG custom-KG backend seam for zero-LLM graph ingestion.

This module is the W6 wave-1 delivery for Phase 17 (see
``.planning/phases/17-graph-recall-multiroute-fusion/17-PLAN-MASTER-2026-09-01.md``):
it wraps the verified LightRAG zero-LLM ingestion contract (``ainsert_custom_kg``
with pre-built entities/relationships/chunks) and the DashScope embedding
endpoint behind small, fully annotated, fail-closed seams.  The ``lightrag``
package is imported lazily inside the default factory only, so this module is
importable (and fully unit-testable with fakes) without LightRAG installed.
No network I/O happens on injected-transport paths, no wall-clock reads, and
the DashScope API key never appears in ``repr``.
"""

from __future__ import annotations

import asyncio
import http.client
import importlib
import json
import math
import sys
import types
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "CustomKgChunk",
    "CustomKgEntity",
    "CustomKgPayload",
    "CustomKgRelation",
    "DashScopeEmbedding",
    "EmbeddingResponse",
    "EmbeddingTransport",
    "IngestReceipt",
    "LightragKgIngestor",
    "LightragLike",
    "LightragQueryClient",
    "LightragRuntimeConfig",
]

_DEFAULT_EMBEDDING_DIMENSIONS = 1024
_CUSTOM_KG_FILE_PATH_DEFAULT = "custom_kg"


def _require_nonempty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class LightragRuntimeConfig:
    """Runtime configuration for the LightRAG backend seam."""

    workspace: str
    embedding_base_url: str
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024

    def __post_init__(self) -> None:
        _require_nonempty_str(self.workspace, "workspace")
        _require_nonempty_str(self.embedding_base_url, "embedding_base_url")
        if not (
            self.embedding_base_url.startswith("http://")
            or self.embedding_base_url.startswith("https://")
        ):
            raise ValueError("embedding_base_url must start with http:// or https://")
        _require_nonempty_str(self.embedding_model, "embedding_model")
        _require_positive_int(self.embedding_dimensions, "embedding_dimensions")


@dataclass(frozen=True)
class CustomKgEntity:
    """One custom-KG entity entry (LightRAG requires ``entity_name``)."""

    entity_name: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.entity_name, "entity_name")


@dataclass(frozen=True)
class CustomKgRelation:
    """One custom-KG relationship entry (all four fields are required)."""

    src_id: str
    tgt_id: str
    description: str
    keywords: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.src_id, "src_id")
        _require_nonempty_str(self.tgt_id, "tgt_id")
        _require_nonempty_str(self.description, "description")
        _require_nonempty_str(self.keywords, "keywords")
        if self.src_id == self.tgt_id:
            # Mirrors the Phase 16 SELF_LOOP discipline.
            raise ValueError("src_id and tgt_id must differ")


@dataclass(frozen=True)
class CustomKgChunk:
    """One custom-KG chunk entry; ``file_path`` defaults to the literal value.

    LightRAG defaults a missing ``file_path`` to the literal string
    ``custom_kg``; this dataclass keeps ``None`` until serialization time so
    the emitted custom-KG body always carries the exact default.
    """

    content: str
    source_id: str
    file_path: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.content, "content")
        _require_nonempty_str(self.source_id, "source_id")
        if self.file_path is not None:
            _require_nonempty_str(self.file_path, "file_path")


@dataclass(frozen=True)
class CustomKgPayload:
    """Typed payload that serializes to the exact ``ainsert_custom_kg`` shape."""

    entities: tuple[CustomKgEntity, ...]
    relations: tuple[CustomKgRelation, ...]
    chunks: tuple[CustomKgChunk, ...]

    def __post_init__(self) -> None:
        for label, value, expected in (
            ("entities", self.entities, CustomKgEntity),
            ("relations", self.relations, CustomKgRelation),
            ("chunks", self.chunks, CustomKgChunk),
        ):
            if not isinstance(value, tuple) or any(
                not isinstance(item, expected) for item in value
            ):
                raise ValueError(f"{label} must be a tuple of {expected.__name__}")

    def to_custom_kg(self) -> dict[str, Any]:
        return {
            "entities": [{"entity_name": e.entity_name} for e in self.entities],
            "relationships": [
                {
                    "src_id": r.src_id,
                    "tgt_id": r.tgt_id,
                    "description": r.description,
                    "keywords": r.keywords,
                }
                for r in self.relations
            ],
            "chunks": [
                {
                    "content": c.content,
                    "source_id": c.source_id,
                    "file_path": (
                        c.file_path
                        if c.file_path is not None
                        else _CUSTOM_KG_FILE_PATH_DEFAULT
                    ),
                }
                for c in self.chunks
            ],
        }


class EmbeddingTransport(Protocol):
    """Transport seam so embedding calls are testable without network."""

    def post_embeddings(self, body: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class EmbeddingResponse:
    """Normalized embedding response (vectors are tuples of floats)."""

    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimensions: int
    total_tokens: int


@dataclass(frozen=True)
class DashScopeEmbedding:
    """DashScope OpenAI-compatible embedding client.

    The request body is pinned to exactly ``{"model", "input", "dimensions"}``;
    every returned embedding vector must have exactly ``dimensions``
    components.  ``transport`` allows injecting a fake for offline tests; the
    default transport posts to ``<base_url>/embeddings`` with a Bearer header.
    """

    model: str
    base_url: str = field(kw_only=True)
    api_key: str = field(kw_only=True, repr=False)
    dimensions: int = field(kw_only=True, default=_DEFAULT_EMBEDDING_DIMENSIONS)
    transport: EmbeddingTransport | None = field(kw_only=True, default=None)
    timeout_s: float = field(kw_only=True, default=30.0)

    def __post_init__(self) -> None:
        _require_nonempty_str(self.model, "model")
        _require_nonempty_str(self.base_url, "base_url")
        if not (
            self.base_url.startswith("http://") or self.base_url.startswith("https://")
        ):
            raise ValueError("embedding_base_url must start with http:// or https://")
        _require_nonempty_str(self.api_key, "api_key")
        _require_positive_int(self.dimensions, "dimensions")
        if isinstance(self.timeout_s, bool) or not isinstance(
            self.timeout_s, (int, float)
        ):
            raise ValueError("timeout_s must be a positive finite number")
        if not math.isfinite(float(self.timeout_s)) or self.timeout_s <= 0:
            raise ValueError("timeout_s must be a positive finite number")

    def __repr__(self) -> str:
        return (
            "DashScopeEmbedding("
            f"model={self.model!r}, base_url={self.base_url!r}, "
            f"dimensions={self.dimensions}, timeout_s={self.timeout_s}, "
            "api_key=<redacted>)"
        )

    def _default_transport(self) -> EmbeddingTransport:
        client = self

        class _UrllibTransport:
            def post_embeddings(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
                url = client.base_url.rstrip("/") + "/embeddings"
                payload = json.dumps(dict(body)).encode("utf-8")
                request = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {client.api_key}",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(
                        request, timeout=client.timeout_s
                    ) as raw:
                        return json.loads(raw.read().decode("utf-8"))
                except (
                    urllib.error.URLError,
                    http.client.HTTPException,
                    OSError,
                ) as exc:
                    raise ValueError(
                        f"dashscope embedding request failed: {exc}"
                    ) from exc
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ValueError(
                        f"dashscope embedding response was not JSON: {exc}"
                    ) from exc

        return _UrllibTransport()

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if isinstance(texts, (str, bytes)):
            raise ValueError("texts must be a sequence of strings, not a bare string")
        items = list(texts)
        if not items:
            raise ValueError("texts must not be empty")
        if any(not isinstance(item, str) for item in items):
            raise ValueError("every text must be a string")
        body: dict[str, Any] = {
            "model": self.model,
            "input": items,
            "dimensions": self.dimensions,
        }
        transport: EmbeddingTransport = (
            self.transport if self.transport is not None else self._default_transport()
        )
        response = transport.post_embeddings(body)
        if not isinstance(response, Mapping):
            raise ValueError("embedding response must be a mapping")
        data = response.get("data")
        if not isinstance(data, list) or len(data) != len(items):
            raise ValueError(
                "embedding response data must be a list with one entry per text"
            )
        vectors: list[tuple[float, ...]] = []
        for entry in data:
            if not isinstance(entry, Mapping):
                raise ValueError("embedding response entries must be mappings")
            embedding = entry.get("embedding")
            if not isinstance(embedding, (list, tuple)):
                raise ValueError(
                    "embedding response entry must contain an embedding list"
                )
            if len(embedding) != self.dimensions:
                raise ValueError(
                    f"embedding vector dimension mismatch: expected {self.dimensions}, "
                    f"got {len(embedding)}"
                )
            components: list[float] = []
            for component in embedding:
                if isinstance(component, bool) or not isinstance(
                    component, (int, float)
                ):
                    raise ValueError(
                        "embedding vectors must contain numeric components"
                    )
                components.append(float(component))
            vectors.append(tuple(components))
        raw_model = response.get("model")
        model = raw_model if isinstance(raw_model, str) and raw_model else self.model
        usage = response.get("usage")
        total_tokens = 0
        if isinstance(usage, Mapping) and usage.get("total_tokens") is not None:
            raw_total = usage["total_tokens"]
            if isinstance(raw_total, bool) or not isinstance(raw_total, int):
                raise ValueError("embedding usage total_tokens must be an integer")
            total_tokens = raw_total
        return EmbeddingResponse(
            vectors=tuple(vectors),
            model=model,
            dimensions=self.dimensions,
            total_tokens=total_tokens,
        )


@dataclass(frozen=True)
class IngestReceipt:
    """What one ``LightragKgIngestor.ingest`` call actually sent."""

    inserted_entities: tuple[str, ...]
    skipped_entities: tuple[str, ...]
    inserted_relations: tuple[str, ...]
    skipped_relations: tuple[str, ...]
    inserted_chunks: tuple[str, ...]


class LightragLike(Protocol):
    """Minimal structural seam for the parts of LightRAG we call."""

    async def ainsert_custom_kg(
        self, custom_kg: Mapping[str, Any], full_doc_id: str | None = None
    ) -> Any: ...

    async def aquery_data(self, param: Any) -> Any: ...


def _default_lightrag_factory(
    config: LightragRuntimeConfig, embedding: Any | None
) -> Any:
    """Lazily import ``lightrag`` and construct a bare ``LightRag``.

    Deliberately minimal: full environment wiring (embedding binding, PG
    backend, workspace) is the Phase 17 integration wave; inject
    ``lightrag_factory`` for anything non-default.  Fail-closed when the
    package is missing.
    """

    install_hint = "install it with pip install lightrag-hku"
    try:
        module = importlib.import_module("lightrag")
    except ImportError as exc:
        raise RuntimeError(
            f"lightrag is required for the default factory; {install_hint}"
        ) from exc
    # Defensive guard: unreachable right after a successful import; kept on
    # purpose so the fail-closed contract survives future refactors.
    if sys.modules.get("lightrag") is None:
        raise RuntimeError(
            f"lightrag is required for the default factory; {install_hint}"
        )
    rag_cls = getattr(module, "LightRag", None)
    if rag_cls is None:
        raise RuntimeError(f"lightrag package does not expose LightRag; {install_hint}")
    return rag_cls()


class LightragKgIngestor:
    """Zero-LLM custom-KG ingester with payload-local dedupe."""

    def __init__(
        self,
        *,
        config: LightragRuntimeConfig,
        embedding: Any | None = None,
        lightrag_factory: Callable[[LightragRuntimeConfig, Any], Any] | None = None,
    ) -> None:
        self._config = config
        self._embedding = embedding
        self._lightrag_factory = lightrag_factory
        self._rag: Any | None = None

    def _ensure_rag(self) -> Any:
        if self._rag is None:
            factory = (
                self._lightrag_factory
                if self._lightrag_factory is not None
                else _default_lightrag_factory
            )
            self._rag = factory(self._config, self._embedding)
        return self._rag

    async def ingest(
        self,
        payload: CustomKgPayload,
        *,
        known_entity_names: frozenset[str] = frozenset(),
    ) -> IngestReceipt:
        """Insert a payload.

        Relations referencing known (pre-existing) entities are still
        inserted by design (they are forwarded verbatim).
        """
        if not isinstance(payload, CustomKgPayload):
            raise ValueError("payload must be a CustomKgPayload")
        if isinstance(known_entity_names, (str, bytes)):
            raise ValueError("known_entity_names must be a collection of names")
        known = frozenset(known_entity_names)
        seen_entities: set[str] = set()
        kept_entities: list[CustomKgEntity] = []
        inserted_entities: list[str] = []
        skipped_entities: list[str] = []
        for entity in payload.entities:
            name = entity.entity_name
            if name in seen_entities:
                continue
            seen_entities.add(name)
            if name in known:
                skipped_entities.append(name)
                continue
            kept_entities.append(entity)
            inserted_entities.append(name)
        seen_pairs: dict[tuple[str, str], tuple[str, str]] = {}
        kept_relations: list[CustomKgRelation] = []
        inserted_relations: list[str] = []
        for relation in payload.relations:
            pair = (relation.src_id, relation.tgt_id)
            content = (relation.description, relation.keywords)
            if pair in seen_pairs:
                if seen_pairs[pair] != content:
                    raise ValueError(
                        f"conflicting duplicate relationship for "
                        f"{relation.src_id}->{relation.tgt_id}"
                    )
                continue
            seen_pairs[pair] = content
            kept_relations.append(relation)
            inserted_relations.append(f"{relation.src_id}->{relation.tgt_id}")
        rag = self._ensure_rag()
        custom_kg: dict[str, Any] = {
            "entities": [{"entity_name": e.entity_name} for e in kept_entities],
            "relationships": [
                {
                    "src_id": r.src_id,
                    "tgt_id": r.tgt_id,
                    "description": r.description,
                    "keywords": r.keywords,
                }
                for r in kept_relations
            ],
            "chunks": [
                {
                    "content": c.content,
                    "source_id": c.source_id,
                    "file_path": (
                        c.file_path
                        if c.file_path is not None
                        else _CUSTOM_KG_FILE_PATH_DEFAULT
                    ),
                }
                for c in payload.chunks
            ],
        }
        await rag.ainsert_custom_kg(custom_kg)
        return IngestReceipt(
            inserted_entities=tuple(inserted_entities),
            skipped_entities=tuple(skipped_entities),
            inserted_relations=tuple(inserted_relations),
            skipped_relations=(),
            inserted_chunks=tuple(chunk.source_id for chunk in payload.chunks),
        )


def _default_param_factory(**kwargs: Any) -> Any:
    return types.SimpleNamespace(**kwargs)


def _clean_keywords(value: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence of strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} entries must be strings")
        stripped = item.strip()
        if stripped:
            cleaned.append(stripped)
    return tuple(cleaned)


class LightragQueryClient:
    """Zero-LLM query client: pre-supplied keywords skip LightRAG LLM steps."""

    def __init__(
        self, rag: Any, *, param_factory: Callable[..., Any] | None = None
    ) -> None:
        self._rag = rag
        self._param_factory = (
            param_factory if param_factory is not None else _default_param_factory
        )

    async def aquery_data(
        self,
        query: str,
        *,
        hl_keywords: Sequence[str],
        ll_keywords: Sequence[str],
        top_k: int = 10,
        chunk_top_k: int = 10,
    ) -> Any:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-blank string")
        hl = _clean_keywords(hl_keywords, "hl_keywords")
        ll = _clean_keywords(ll_keywords, "ll_keywords")
        if not hl and not ll:
            raise ValueError(
                "at least one of hl_keywords/ll_keywords must be non-empty"
            )
        _require_positive_int(top_k, "top_k")
        _require_positive_int(chunk_top_k, "chunk_top_k")
        param = self._param_factory(
            query=query,
            mode="naive",
            only_need_context=True,
            hl_keywords=hl,
            ll_keywords=ll,
            top_k=top_k,
            chunk_top_k=chunk_top_k,
        )
        return await self._rag.aquery_data(param)

    def query_data(
        self,
        query: str,
        *,
        hl_keywords: Sequence[str],
        ll_keywords: Sequence[str],
        top_k: int = 10,
        chunk_top_k: int = 10,
    ) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.aquery_data(
                    query,
                    hl_keywords=hl_keywords,
                    ll_keywords=ll_keywords,
                    top_k=top_k,
                    chunk_top_k=chunk_top_k,
                )
            )
        raise RuntimeError(
            "LightragQueryClient.query_data is sync-only and cannot run inside an "
            "event loop; use aquery_data instead"
        )
