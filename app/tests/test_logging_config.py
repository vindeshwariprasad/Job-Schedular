"""Comprehensive tests for logging configuration: JSONFormatter and get_logger."""

import json
import logging

from logging_config import JSONFormatter, get_logger


class TestJSONFormatter:

    def _make_record(self, message="Test message", level="INFO", **kwargs):
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            name="test",
            level=getattr(logging, level),
            fn="test.py",
            lno=1,
            msg=message,
            args=(),
            exc_info=None,
        )
        for key, value in kwargs.items():
            setattr(record, key, value)
        return record

    def test_formats_as_json(self):
        formatter = JSONFormatter()
        record = self._make_record("Hello")
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["message"] == "Hello"

    def test_includes_timestamp(self):
        formatter = JSONFormatter()
        record = self._make_record("Test")
        result = json.loads(formatter.format(record))
        assert "timestamp" in result

    def test_includes_level(self):
        formatter = JSONFormatter()
        record = self._make_record("Test", level="WARNING")
        result = json.loads(formatter.format(record))
        assert result["level"] == "WARNING"

    def test_includes_logger_name(self):
        formatter = JSONFormatter()
        record = self._make_record("Test")
        result = json.loads(formatter.format(record))
        assert result["logger"] == "test"

    def test_includes_execution_id(self):
        formatter = JSONFormatter()
        record = self._make_record("Test", execution_id="exec-001")
        result = json.loads(formatter.format(record))
        assert result["execution_id"] == "exec-001"

    def test_includes_job_id(self):
        formatter = JSONFormatter()
        record = self._make_record("Test", job_id=42)
        result = json.loads(formatter.format(record))
        assert result["job_id"] == 42

    def test_includes_schedule_id(self):
        formatter = JSONFormatter()
        record = self._make_record("Test", schedule_id=7)
        result = json.loads(formatter.format(record))
        assert result["schedule_id"] == 7

    def test_excludes_missing_correlation_fields(self):
        formatter = JSONFormatter()
        record = self._make_record("Test")
        result = json.loads(formatter.format(record))
        assert "execution_id" not in result
        assert "job_id" not in result
        assert "schedule_id" not in result

    def test_includes_exception(self):
        formatter = JSONFormatter()
        logger = logging.getLogger("test_exc")
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            record = logger.makeRecord(
                name="test_exc",
                level=logging.ERROR,
                fn="test.py",
                lno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        result = json.loads(formatter.format(record))
        assert "exception" in result
        assert "ValueError" in result["exception"]

    def test_no_exception_when_none(self):
        formatter = JSONFormatter()
        record = self._make_record("Test")
        result = json.loads(formatter.format(record))
        assert "exception" not in result


class TestGetLogger:

    def test_returns_logger(self):
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        logger = get_logger("my_module")
        assert logger.name == "my_module"

    def test_logger_has_handler(self):
        logger = get_logger("handler_test")
        assert len(logger.handlers) > 0

    def test_handler_uses_json_formatter(self):
        logger = get_logger("formatter_test")
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    def test_logger_level_is_info(self):
        logger = get_logger("level_test")
        assert logger.level == logging.INFO

    def test_logger_no_propagation(self):
        logger = get_logger("propagation_test")
        assert logger.propagate is False

    def test_same_logger_returned(self):
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        assert logger1 is logger2

    def test_does_not_add_duplicate_handlers(self):
        name = "no_dup_handlers"
        get_logger(name)
        get_logger(name)
        logger = logging.getLogger(name)
        assert len(logger.handlers) == 1
