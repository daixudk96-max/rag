from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.routes import app


@patch("api.routes.close_pool")
@patch("api.routes.init_pool")
def test_lifespan_calls_pool_hooks(mock_init_pool, mock_close_pool) -> None:
    with TestClient(app):
        pass
    mock_init_pool.assert_called_once()
    mock_close_pool.assert_called_once()


