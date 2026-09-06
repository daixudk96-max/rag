"""Structured logging helpers for JSON-formatted logs."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import TextIO


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.name,
        }
        for attr in ("request_method", "request_path", "response_status", "duration_ms", "route"):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", stream: TextIO | None = None) -> logging.Logger:
    """Configure a logger with JSON formatting.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        stream: Output stream (defaults to sys.stderr).

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("rag")
    logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def get_request_logger(name: str = "rag.request") -> logging.Logger:
    """Get a logger instance by name.

    Args:
        name: Logger name (defaults to 'rag.request').

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)