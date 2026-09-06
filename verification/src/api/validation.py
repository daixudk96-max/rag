from __future__ import annotations

from api.errors import ValidationAppError

QUERY_MAX_LENGTH = 500
TOP_K_MIN = 1
TOP_K_MAX = 100
LIMIT_MAX = 200


def validate_query(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValidationAppError("query 不能为空")
    if len(cleaned) > QUERY_MAX_LENGTH:
        raise ValidationAppError(f"query 长度超过上限 {QUERY_MAX_LENGTH}")
    return cleaned


def validate_top_k(top_k: int) -> int:
    if top_k < TOP_K_MIN:
        raise ValidationAppError("top_k 必须 >= 1")
    if top_k > TOP_K_MAX:
        raise ValidationAppError(f"top_k 不能超过 {TOP_K_MAX}")
    return top_k


def validate_limit(limit: int) -> int:
    if limit < 1:
        raise ValidationAppError("limit 必须 >= 1")
    if limit > LIMIT_MAX:
        raise ValidationAppError(f"limit 不能超过 {LIMIT_MAX}")
    return limit
