"""Tests for structured logging helpers."""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone

from llamaindex_runtime import JsonFormatter, get_request_logger, setup_logging


def test_json_formatter_outputs_valid_json() -> None:
    """JsonFormatter should output valid JSON with required fields."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "timestamp" in parsed
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test message"
    assert parsed["module"] == "test.module"


def test_json_formatter_uses_record_created_timestamp() -> None:
    """JsonFormatter should derive timestamp from the LogRecord creation time."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    record.created = 1_700_000_000.0

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["timestamp"] == datetime.fromtimestamp(
        record.created, tz=timezone.utc
    ).isoformat()


def test_json_formatter_includes_request_attributes() -> None:
    """JsonFormatter should include optional request attributes when present."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Request completed",
        args=(),
        exc_info=None,
    )
    record.request_method = "GET"
    record.request_path = "/api/query"
    record.response_status = 200
    record.duration_ms = 42.5
    record.route = "query_endpoint"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["request_method"] == "GET"
    assert parsed["request_path"] == "/api/query"
    assert parsed["response_status"] == 200
    assert parsed["duration_ms"] == 42.5
    assert parsed["route"] == "query_endpoint"


def test_json_formatter_stringifies_non_serializable_attributes() -> None:
    """JsonFormatter should stringify non-JSON-serializable request attributes."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Request completed",
        args=(),
        exc_info=None,
    )

    class CustomValue:
        def __str__(self) -> str:
            return "custom-value"

    record.route = CustomValue()

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["route"] == "custom-value"


def test_json_formatter_handles_unicode() -> None:
    """JsonFormatter should handle unicode characters correctly."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test 中文 emoji 🎉",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["message"] == "Test 中文 emoji 🎉"


def test_setup_logging_returns_configured_logger() -> None:
    """setup_logging should return a configured logger with JsonFormatter."""
    stream = io.StringIO()
    logger = setup_logging(level="DEBUG", stream=stream)

    assert logger.name == "rag"
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)
    assert logger.propagate is False


def test_setup_logging_writes_json_to_stream() -> None:
    """setup_logging should write JSON-formatted logs to the stream."""
    stream = io.StringIO()
    logger = setup_logging(level="INFO", stream=stream)

    logger.info("Test log message")

    output = stream.getvalue()
    parsed = json.loads(output.strip())

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test log message"


def test_setup_logging_clears_existing_handlers() -> None:
    """setup_logging should clear existing handlers on the logger."""
    logger = logging.getLogger("rag")
    logger.addHandler(logging.StreamHandler())
    logger.addHandler(logging.StreamHandler())

    stream = io.StringIO()
    setup_logging(level="INFO", stream=stream)

    assert len(logger.handlers) == 1


def test_get_request_logger_returns_logger_by_name() -> None:
    """get_request_logger should return a logger with the specified name."""
    logger = get_request_logger("custom.request")
    assert logger.name == "custom.request"


def test_get_request_logger_defaults_to_rag_request() -> None:
    """get_request_logger should default to 'rag.request' if no name provided."""
    logger = get_request_logger()
    assert logger.name == "rag.request"