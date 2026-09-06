"""Shared live-gate bridge for the Phase 17 acceptance runner and demo (single owner; extracted from the duplicated FIX-11..16 blocks)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import stat
import sys
import tempfile
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "_AqueryDataAdapter",
    "_LoopBoundRag",
    "_SyncIngestAdapter",
    "_as_embedding_array",
    "_normalize_chunk_source_ids",
    "_pg_lightrag_factory",
    "_start_rag_loop",
    "_stub_llm_model_func",
]


def _stub_llm_model_func(*args: Any, **kwargs: Any) -> str:
    """Fail closed if any LightRAG path reaches the (unused) LLM seam."""
    raise RuntimeError(
        "llm_model_func is a deliberate stub; "
        "LightRAG keyword short-circuit must prevent LLM calls"
    )


def _as_embedding_array(rows: Sequence[Sequence[float]]) -> Any:
    """Return embedding rows as a 2-D float32 numpy array.

    LightRAG's EmbeddingFunc.__call__ (lightrag/utils.py) reads result.size
    on the wrapped function's return value, and PGVectorStorage's flush
    concatenates batch results with np.concatenate
    (lightrag/kg/postgres_impl.py).  A nested Python list crashes the flush
    with AttributeError: 'list' object has no attribute 'size'.
    """
    import numpy as np

    return np.asarray([list(row) for row in rows], dtype=np.float32)


def _reject_reparse_dir(path: str) -> None:
    """Fail closed when an existing path is a Windows reparse point."""
    if sys.platform == "win32" and os.path.lexists(path):
        st = os.lstat(path)
        if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("PHASE17_LIGHTRAG_WORKDIR must not be a reparse point")


def _pg_lightrag_factory(config: Any, embedding: Any) -> Any:
    """Build a live PG-backed LightRAG for the Phase 17 runners (W7-LIVE).

    Shared by the acceptance runner and the demo: binds the DashScope
    embedding seam through lightrag's EmbeddingFunc, pins the four PG
    storages plus a zero-LLM construction, and takes the working dir from
    PHASE17_LIGHTRAG_WORKDIR with a tempdir fallback.  LightRAG requires
    a non-None llm_model_func, so a fail-closed stub is bound instead.
    The working dir is a deterministic per-workspace path (tempdir fallback
    or PHASE17_LIGHTRAG_WORKDIR); it is reused idempotently across
    invocations and never cleaned by the bridge.
    """
    try:
        import lightrag  # type: ignore[import-not-found]
        from lightrag.utils import EmbeddingFunc  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "lightrag is required for the live PG backend; "
            "install it with pip install lightrag-hku"
        ) from exc

    async def _embed(texts: list[str]) -> Any:
        vectors = embedding.embed(list(texts)).vectors
        return _as_embedding_array([list(v) for v in vectors])

    ef = EmbeddingFunc(
        embedding_dim=config.embedding_dimensions,
        func=_embed,
        model_name=config.embedding_model,
    )
    working_dir = os.environ.get("PHASE17_LIGHTRAG_WORKDIR") or os.path.join(
        tempfile.gettempdir(), f"phase17-lightrag-wd-{config.workspace}"
    )
    if not Path(working_dir).is_absolute():
        raise ValueError("PHASE17_LIGHTRAG_WORKDIR must be an absolute path")
    _reject_reparse_dir(working_dir)
    os.makedirs(working_dir, exist_ok=True)
    return lightrag.LightRAG(
        working_dir=working_dir,
        kv_storage="PGKVStorage",
        vector_storage="PGVectorStorage",
        graph_storage="PGTableGraphStorage",
        doc_status_storage="PGDocStatusStorage",
        workspace=config.workspace,
        embedding_func=ef,
        llm_model_func=_stub_llm_model_func,
        llm_model_name="stub-fail-closed-no-llm",
        vector_db_storage_cls_kwargs={"cosine_better_than_threshold": 0.2},
    )


def _start_rag_loop() -> tuple[threading.Thread, asyncio.AbstractEventLoop]:
    """Start a daemon thread running a persistent event loop.

    asyncpg pools bind to the loop that created them, so every rag
    coroutine (queries and ingests) must execute on this single loop.

    Daemon by design: the worker thread lives for the process lifetime, no
    stop handle exists by design, and process exit reclaims it.
    """
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return thread, loop


class _LoopBoundRag:
    """Proxy that executes rag coroutines on the persistent loop.

    graph_channel fetch wraps each call in asyncio.run, which spins
    a fresh per-call loop; run_coroutine_threadsafe + wrap_future
    keeps the real coroutine on the pool-owning loop.
    """

    def __init__(self, inner: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._inner = inner
        self._loop = loop

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self._inner, name)
        if not asyncio.iscoroutinefunction(attr):
            return attr

        async def bridged(*args: Any, **kwargs: Any) -> Any:
            fut = asyncio.run_coroutine_threadsafe(attr(*args, **kwargs), self._loop)
            return await asyncio.wrap_future(fut)

        return bridged


class _AqueryDataAdapter:
    """Translate the frozen LightragQueryClient call convention to LightRAG 1.5.6.

    LightragQueryClient.aquery_data(param) passes a SimpleNamespace as the single
    positional argument, but LightRAG 1.5.6's real signature is
    aquery_data(query: str, param: QueryParam) (venv lightrag.py:3701-3705;
    :3838 calls query.strip()).  Only the aquery_data attribute is translated;
    every other attribute passes through to the loop-bound rag unchanged.

    Recall bounding is governed by the worker timeout: the frozen query_data
    awaits this future and adds no additional timer of its own.
    """

    def __init__(self, loop_rag: Any, rag: Any, loop: Any) -> None:
        self._loop_rag = loop_rag
        self._rag = rag
        self._loop = loop

    def __getattr__(self, name: str) -> Any:
        if name == "aquery_data":
            return self._adapted_aquery_data
        return getattr(self._loop_rag, name)

    def _adapted_aquery_data(self, param: Any) -> Any:
        async def _call() -> Any:
            from lightrag.base import QueryParam  # type: ignore[import-not-found]

            real_param = QueryParam(
                mode=param.mode,
                only_need_context=True,
                top_k=param.top_k,
                chunk_top_k=param.chunk_top_k,
                hl_keywords=list(param.hl_keywords or []),
                ll_keywords=list(param.ll_keywords or []),
            )
            future = asyncio.run_coroutine_threadsafe(
                self._rag.aquery_data(param.query, real_param), self._loop
            )
            response = await asyncio.wrap_future(future)
            return _normalize_chunk_source_ids(response)

        return _call()


def _normalize_chunk_source_ids(response: Any) -> Any:
    """Map LightRAG 1.5.6 chunk entries onto the frozen channel contract.

    aquery_data chunk entries carry chunk_id / file_path / reference_id but no
    source_id (venv lightrag/utils.py convert_to_user_format), while the frozen
    LightragGraphChannel requires a non-empty source_id per chunk and drops
    entries without one.  Derive source_id from chunk_id (stable per-chunk
    identity), falling back to file_path then reference_id.  Entries that
    already carry a non-empty source_id pass through untouched; entries with
    nothing derivable are left as-is so the channel keeps skipping them.
    """
    if not isinstance(response, Mapping):
        return response
    data = response.get("data")
    if not isinstance(data, Mapping):
        return response
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return response
    normalized: list[Any] = []
    changed = False
    for chunk in chunks:
        if isinstance(chunk, Mapping) and not (
            isinstance(chunk.get("source_id"), str)
            and chunk.get("source_id").strip()  # type: ignore[union-attr]
        ):
            derived = ""
            for key in ("chunk_id", "file_path", "reference_id"):
                value = chunk.get(key)
                if isinstance(value, str) and value.strip():
                    derived = value
                    break
            if derived:
                patched = dict(chunk)
                patched["source_id"] = derived
                normalized.append(patched)
                changed = True
                continue
        normalized.append(chunk)
    if not changed:
        return response
    merged = dict(response)
    merged_data = dict(data)
    merged_data["chunks"] = normalized
    merged["data"] = merged_data
    return merged


class _SyncIngestAdapter:
    """Expose the frozen async ingest as a blocking synchronous call."""

    def __init__(self, inner: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._inner = inner
        self._loop = loop

    def ingest(
        self, payload: Any, *, known_entity_names: frozenset[str] = frozenset()
    ) -> Any:
        fut = asyncio.run_coroutine_threadsafe(
            self._inner.ingest(payload, known_entity_names=known_entity_names),
            self._loop,
        )
        try:
            return fut.result(timeout=600.0)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            raise
