from __future__ import annotations

import pytest

from api.validation import validate_limit, validate_query, validate_top_k


def test_validate_query_empty() -> None:
    with pytest.raises(Exception):
        validate_query("")


def test_validate_query_too_long() -> None:
    with pytest.raises(Exception):
        validate_query("a" * 501)


def test_validate_top_k_bounds() -> None:
    with pytest.raises(Exception):
        validate_top_k(0)
    with pytest.raises(Exception):
        validate_top_k(101)


def test_validate_limit_bounds() -> None:
    with pytest.raises(Exception):
        validate_limit(0)
    with pytest.raises(Exception):
        validate_limit(201)
