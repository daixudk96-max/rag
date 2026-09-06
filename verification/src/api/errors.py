from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    error_type = "internal_error"

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class ValidationAppError(AppError):
    status_code = 422
    error_type = "validation_error"


class DatabaseError(AppError):
    status_code = 500
    error_type = "internal_error"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.error_type, "detail": exc.detail})

    @app.exception_handler(Exception)
    async def _handle_generic_error(_: Request, exc: Exception):
        logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "服务内部错误"})
