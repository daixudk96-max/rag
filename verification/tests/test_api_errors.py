from __future__ import annotations

from fastapi.testclient import TestClient

from api.routes import app


def test_query_empty_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/query", json={"query": ""})
    assert response.status_code == 422


def test_query_hybrid_topk_invalid_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/query/hybrid", json={"query": "abc", "top_k": 200})
    assert response.status_code == 422
