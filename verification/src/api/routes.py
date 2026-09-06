from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from api.errors import DatabaseError, ValidationAppError, register_error_handlers
from api.logging_config import get_request_logger, setup_logging
from api.validation import validate_limit, validate_query, validate_top_k
from hit_distribution.analyzer import analyze_hit_distribution
from hit_distribution.collector import collect_vector_hits_with_nodes
from hybrid_path.orchestrator import hybrid_query
from keyword_path.search import search_by_keyword
from query_classifier import classify_query
from registry.connection import close_pool, get_connection, init_pool
from unified_output import from_keyword_result, from_vector_result, to_dict
from vector_path.search import search_by_vector_query


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(lifespan=lifespan)
setup_logging()
register_error_handlers(app)
logger = get_request_logger()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request_complete",
        extra={
            "request_method": request.method,
            "request_path": request.url.path,
            "response_status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


class QueryRequest(BaseModel):
    query: str


class HybridQueryRequest(BaseModel):
    query: str
    version_id: uuid.UUID | None = None
    top_k: int = 10


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/query/keyword")
def keyword_query(
    q: str = Query(..., description="查询词"),
    version_id: str | None = Query(None, description="版本 ID（可选）"),
    limit: int = Query(50, description="返回结果上限"),
) -> dict:
    clean_q = validate_query(q)
    safe_limit = validate_limit(limit)
    parsed_version_id = uuid.UUID(version_id) if version_id else None
    try:
        with get_connection(autocommit=True) as conn:
            return search_by_keyword(conn, clean_q, version_id=parsed_version_id, limit=safe_limit)
    except Exception as exc:
        raise DatabaseError("database operation failed") from exc


@app.get("/query/vector")
def vector_query(
    q: str = Query(..., description="查询词"),
    version_id: str | None = Query(None, description="版本 ID（可选）"),
    top_k: int = Query(10, description="返回结果上限"),
) -> dict:
    clean_q = validate_query(q)
    safe_top_k = validate_top_k(top_k)
    parsed_version_id = uuid.UUID(version_id) if version_id else None
    try:
        with get_connection(autocommit=True) as conn:
            return search_by_vector_query(conn, clean_q, version_id=parsed_version_id, top_k=safe_top_k)
    except Exception as exc:
        raise DatabaseError("database operation failed") from exc


@app.post("/query")
def unified_query(payload: QueryRequest) -> dict:
    clean_q = validate_query(payload.query)
    route = classify_query(clean_q)
    try:
        with get_connection(autocommit=True) as conn:
            if route == "keyword":
                return to_dict(from_keyword_result(search_by_keyword(conn, clean_q)))
            return to_dict(from_vector_result(search_by_vector_query(conn, clean_q)))
    except Exception as exc:
        raise DatabaseError("database operation failed") from exc


@app.get("/query/analyze")
def analyze_query(
    q: str = Query(..., description="查询词"),
    version_id: uuid.UUID | None = Query(None, description="版本 ID（可选）"),
    top_k: int = Query(10, description="向量检索返回数"),
) -> dict:
    clean_q = validate_query(q)
    safe_top_k = validate_top_k(top_k)
    try:
        with get_connection(autocommit=True) as conn:
            hits, tree_parent_map, tree_level_map, tree_heading_map, total_hit_count = collect_vector_hits_with_nodes(
                conn, clean_q, version_id=version_id, top_k=safe_top_k
            )
            if not hits:
                return {"decision": "no_hits", "hit_count": total_hit_count, "cv": None, "entropy": None}
            result = analyze_hit_distribution(hits, tree_parent_map, tree_level_map, tree_heading_map)
            return {
                "cv": result.cv,
                "entropy": result.entropy,
                "decision": result.decision.decision,
                "reason": result.decision.reason,
                "hit_count": result.hit_count,
                "suggested_node_ids": [str(node_id) for node_id in result.decision.suggested_node_ids],
            }
    except Exception as exc:
        raise DatabaseError("database operation failed") from exc


@app.post("/query/hybrid")
def hybrid_query_endpoint(payload: HybridQueryRequest) -> dict:
    clean_q = validate_query(payload.query)
    safe_top_k = validate_top_k(payload.top_k)
    try:
        with get_connection(autocommit=True) as conn:
            result = hybrid_query(conn, clean_q, version_id=payload.version_id, top_k=safe_top_k)
            return {
                "query": result.query,
                "paths_used": [
                    {"path_name": item.path_name, "hit_count": item.hit_count, "available": item.available}
                    for item in result.paths_used
                ],
                "total_hits": result.total_hits,
                "decision": result.decision,
                "expanded_count": result.expanded_count,
                "evidence": result.evidence,
            }
    except Exception as exc:
        raise DatabaseError("database operation failed") from exc
