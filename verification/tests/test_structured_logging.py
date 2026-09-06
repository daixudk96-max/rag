from __future__ import annotations

import io
import logging

from api.logging_config import setup_logging


def test_setup_logging_json_format() -> None:
    stream = io.StringIO()
    logger = setup_logging(stream=stream)
    logger.info("hello")
    output = stream.getvalue()
    assert '"message": "hello"' in output
    assert '"level": "INFO"' in output
