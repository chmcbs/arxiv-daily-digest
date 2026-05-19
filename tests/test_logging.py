"""
Tests structured pipeline logging
"""

import json
import logging

from core.logging import JsonFormatter, configure_logging, get_logger


def test_json_formatter_includes_structured_fields():
    record = logging.LogRecord(
        name="core.pipeline",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Ingestion finished",
        args=(),
        exc_info=None,
    )
    record.event = "pipeline.step.completed"
    record.step = "ingestion"
    record.run_count = 2

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "Ingestion finished"
    assert payload["event"] == "pipeline.step.completed"
    assert payload["step"] == "ingestion"
    assert payload["run_count"] == 2
    assert "timestamp" in payload


def test_configure_logging_is_idempotent(caplog):
    configure_logging(level="INFO")
    logger = get_logger("tests.logging")

    with caplog.at_level(logging.INFO):
        logger.info(
            "Pipeline started",
            extra={"event": "pipeline.started", "step": "setup_schema"},
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].event == "pipeline.started"
