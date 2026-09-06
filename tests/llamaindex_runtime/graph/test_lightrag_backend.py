from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from llamaindex_runtime.graph.lightrag_backend import (
    CustomKgChunk,
    CustomKgEntity,
    CustomKgPayload,
    CustomKgRelation,
    DashScopeEmbedding,
    EmbeddingResponse,
    IngestReceipt,
    LightragKgIngestor,
    LightragQueryClient,
    LightragRuntimeConfig,
)


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.bodies: list[dict[str, Any]] = []
        self._response = response

    def post_embeddings(self, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(dict(body))
        return dict(self._response)


def _resp(dim: int = 4, n: int = 2) -> dict[str, Any]:
    vec = ([0.1, 0.2, 0.3, 0.4] * ((dim + 3) // 4))[:dim]
    return {
        "data": [{"embedding": list(vec), "index": i} for i in range(n)],
        "model": "text-embedding-v4",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }


def _config() -> LightragRuntimeConfig:
    return LightragRuntimeConfig(
        workspace="ws-a", embedding_base_url="https://example.invalid/v1"
    )


class FakeLightRag:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self._next: dict[str, Any] = {"status": "success", "data": {}}

    async def ainsert_custom_kg(
        self, custom_kg: dict[str, Any], full_doc_id: str | None = None
    ) -> dict[str, Any]:
        self.inserted.append(dict(custom_kg))
        return {"status": "success"}

    async def aquery_data(self, param: Any) -> dict[str, Any]:
        self.queries.append(
            {
                "mode": param.mode,
                "hl": tuple(param.hl_keywords),
                "ll": tuple(param.ll_keywords),
                "top_k": param.top_k,
                "chunk_top_k": param.chunk_top_k,
                "only_need_context": param.only_need_context,
            }
        )
        return dict(self._next)


def test_payload_maps_to_exact_lightrag_keys() -> None:
    payload = CustomKgPayload(
        entities=(
            CustomKgEntity(entity_name="华为"),
            CustomKgEntity(entity_name="杭州"),
        ),
        relations=(
            CustomKgRelation(
                src_id="华为",
                tgt_id="杭州",
                description="总部位于",
                keywords="总部位于",
            ),
        ),
        chunks=(CustomKgChunk(content="华为的总部在杭州。", source_id="doc-1"),),
    )
    assert payload.to_custom_kg() == {
        "entities": [{"entity_name": "华为"}, {"entity_name": "杭州"}],
        "relationships": [
            {
                "src_id": "华为",
                "tgt_id": "杭州",
                "description": "总部位于",
                "keywords": "总部位于",
            }
        ],
        "chunks": [
            {
                "content": "华为的总部在杭州。",
                "source_id": "doc-1",
                "file_path": "custom_kg",
            }
        ],
    }


def test_payload_rejects_blank_fields() -> None:
    with pytest.raises(ValueError):
        CustomKgEntity(entity_name="  ")
    with pytest.raises(ValueError):
        CustomKgRelation(src_id="a", tgt_id="a", description="d", keywords="k")
    with pytest.raises(ValueError):
        CustomKgRelation(src_id="a", tgt_id="b", description=" ", keywords="k")
    with pytest.raises(ValueError):
        CustomKgRelation(src_id="a", tgt_id="b", description="d", keywords="")
    with pytest.raises(ValueError):
        CustomKgChunk(content="", source_id="doc-1")
    with pytest.raises(ValueError):
        CustomKgChunk(content="x", source_id="")


def test_dashscope_request_pins_model_input_dimensions() -> None:
    t = RecordingTransport(_resp())
    e = DashScopeEmbedding(
        model="text-embedding-v4",
        base_url="https://example.invalid/v1",
        api_key="secret-key",
        dimensions=4,
        transport=t,
    )
    out = e.embed(("a", "b"))
    assert t.bodies == [
        {"model": "text-embedding-v4", "input": ["a", "b"], "dimensions": 4}
    ]
    assert isinstance(out, EmbeddingResponse)
    assert out.vectors == ((0.1, 0.2, 0.3, 0.4), (0.1, 0.2, 0.3, 0.4))
    assert out.model == "text-embedding-v4"
    assert out.dimensions == 4
    assert out.total_tokens == 5


def test_dashscope_rejects_blank_api_key_and_empty_texts() -> None:
    t = RecordingTransport(_resp())
    with pytest.raises(ValueError):
        DashScopeEmbedding(
            model="text-embedding-v4",
            base_url="http://u",
            api_key=" ",
            dimensions=1,
            transport=t,
        )
    e = DashScopeEmbedding(
        model="text-embedding-v4",
        base_url="http://u",
        api_key="k",
        dimensions=4,
        transport=t,
    )
    with pytest.raises(ValueError):
        e.embed(())


def test_dashscope_rejects_wrong_dimension_vectors() -> None:
    e = DashScopeEmbedding(
        model="m",
        base_url="http://u",
        api_key="k",
        dimensions=8,
        transport=RecordingTransport(_resp(dim=4, n=1)),
    )
    with pytest.raises(ValueError, match="dimension"):
        e.embed(("a",))


def test_dashscope_rejects_malformed_response() -> None:
    e = DashScopeEmbedding(
        model="m",
        base_url="http://u",
        api_key="k",
        dimensions=4,
        transport=RecordingTransport({}),
    )
    with pytest.raises(ValueError):
        e.embed(("a",))


def test_dashscope_repr_never_contains_api_key() -> None:
    e = DashScopeEmbedding(
        model="m",
        base_url="http://u",
        api_key="SUPERSECRET",
        dimensions=4,
        transport=RecordingTransport(_resp()),
    )
    assert "SUPERSECRET" not in repr(e)


def test_ingest_dedupes_within_payload() -> None:
    rag = FakeLightRag()
    ing = LightragKgIngestor(
        config=_config(),
        embedding=None,
        lightrag_factory=lambda cfg, emb: rag,
    )
    payload = CustomKgPayload(
        entities=(
            CustomKgEntity(entity_name="华为"),
            CustomKgEntity(entity_name="华为"),
            CustomKgEntity(entity_name="杭州"),
        ),
        relations=(
            CustomKgRelation(
                src_id="华为", tgt_id="杭州", description="d1", keywords="k"
            ),
            CustomKgRelation(
                src_id="华为", tgt_id="杭州", description="d1", keywords="k"
            ),
        ),
        chunks=(),
    )
    receipt = asyncio.run(ing.ingest(payload))
    assert isinstance(receipt, IngestReceipt)
    assert receipt.inserted_entities == ("华为", "杭州")
    assert receipt.inserted_relations == ("华为->杭州",)
    assert len(rag.inserted) == 1


def test_ingest_rejects_conflicting_duplicates() -> None:
    rag = FakeLightRag()
    ing = LightragKgIngestor(
        config=_config(), embedding=None, lightrag_factory=lambda cfg, emb: rag
    )
    payload = CustomKgPayload(
        entities=(),
        relations=(
            CustomKgRelation(src_id="a", tgt_id="b", description="d1", keywords="k"),
            CustomKgRelation(
                src_id="a", tgt_id="b", description="DIFFERENT", keywords="k"
            ),
        ),
        chunks=(),
    )
    with pytest.raises(ValueError, match="conflict"):
        asyncio.run(ing.ingest(payload))
    assert rag.inserted == []


def test_ingest_skips_known_entities_but_keeps_relations() -> None:
    rag = FakeLightRag()
    ing = LightragKgIngestor(
        config=_config(), embedding=None, lightrag_factory=lambda cfg, emb: rag
    )
    payload = CustomKgPayload(
        entities=(
            CustomKgEntity(entity_name="华为"),
            CustomKgEntity(entity_name="小米"),
        ),
        relations=(
            CustomKgRelation(
                src_id="华为", tgt_id="小米", description="d", keywords="k"
            ),
        ),
        chunks=(),
    )
    receipt = asyncio.run(ing.ingest(payload, known_entity_names=frozenset({"华为"})))
    assert receipt.skipped_entities == ("华为",)
    assert receipt.inserted_entities == ("小米",)
    sent = rag.inserted[0]
    assert sent["entities"] == [{"entity_name": "小米"}]
    assert sent["relationships"][0]["src_id"] == "华为"


def test_default_factory_fails_closed_without_lightrag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "lightrag", None)
    ing = LightragKgIngestor(config=_config(), embedding=None)
    with pytest.raises(RuntimeError, match="lightrag"):
        asyncio.run(
            ing.ingest(
                CustomKgPayload(
                    entities=(CustomKgEntity(entity_name="x"),), relations=(), chunks=()
                )
            )
        )


def test_query_client_forces_zero_llm_params() -> None:
    rag = FakeLightRag()
    client = LightragQueryClient(rag)
    out = client.query_data(
        "华为总部", hl_keywords=("华为",), ll_keywords=("总部",), top_k=7, chunk_top_k=3
    )
    assert out == {"status": "success", "data": {}}
    q = rag.queries[0]
    assert q["mode"] == "naive"
    assert q["only_need_context"] is True
    assert q["hl"] == ("华为",) and q["ll"] == ("总部",)
    assert q["top_k"] == 7 and q["chunk_top_k"] == 3


def test_query_client_rejects_empty_or_keywordless() -> None:
    rag = FakeLightRag()
    client = LightragQueryClient(rag)
    with pytest.raises(ValueError):
        client.query_data("  ", hl_keywords=("x",), ll_keywords=())
    with pytest.raises(ValueError):
        client.query_data("q", hl_keywords=(), ll_keywords=())


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        LightragRuntimeConfig(workspace="  ", embedding_base_url="u")
    with pytest.raises(ValueError):
        LightragRuntimeConfig(
            workspace="w", embedding_base_url="u", embedding_dimensions=0
        )
    with pytest.raises(ValueError):
        LightragRuntimeConfig(workspace="w", embedding_base_url="u", embedding_model="")


def test_dashscope_default_dimensions_are_pinned() -> None:
    t = RecordingTransport(_resp(dim=1024, n=1))
    e = DashScopeEmbedding(model="m", base_url="http://u", api_key="k", transport=t)
    out = e.embed(("a",))
    assert t.bodies == [{"model": "m", "input": ["a"], "dimensions": 1024}]
    assert out.dimensions == 1024
    assert out.vectors[0] == (0.1, 0.2, 0.3, 0.4) * 256


def test_base_url_scheme_rejected() -> None:
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        DashScopeEmbedding(model="m", base_url="ftp://x", api_key="k")
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        LightragRuntimeConfig(workspace="w", embedding_base_url="example.com")


def test_transport_http_exception_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import http.client
    import urllib.request

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise http.client.IncompleteRead(b"", None)

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    e = DashScopeEmbedding(model="m", base_url="http://u", api_key="k", dimensions=4)
    with pytest.raises(ValueError) as excinfo:
        e.embed(("a",))
    assert str(excinfo.value) == (
        "dashscope embedding request failed: "
        + str(http.client.IncompleteRead(b"", None))
    )


def test_total_tokens_bool_rejected() -> None:
    response = _resp(dim=4, n=1)
    response["usage"]["total_tokens"] = True
    e = DashScopeEmbedding(
        model="m",
        base_url="http://u",
        api_key="k",
        dimensions=4,
        transport=RecordingTransport(response),
    )
    with pytest.raises(
        ValueError, match="embedding usage total_tokens must be an integer"
    ):
        e.embed(("a",))


def test_query_data_inside_running_loop_raises() -> None:
    rag = FakeLightRag()
    client = LightragQueryClient(rag)

    async def _call() -> Any:
        return client.query_data("q", hl_keywords=("a",), ll_keywords=())

    with pytest.raises(RuntimeError, match="use aquery_data instead"):
        asyncio.run(_call())


def test_aquery_data_core_matches_sync() -> None:
    rag = FakeLightRag()
    client = LightragQueryClient(rag)
    out = asyncio.run(
        client.aquery_data(
            "q", hl_keywords=("a",), ll_keywords=(), top_k=5, chunk_top_k=5
        )
    )
    assert out == {"status": "success", "data": {}}
    q = rag.queries[0]
    assert q["mode"] == "naive"
    assert q["only_need_context"] is True
