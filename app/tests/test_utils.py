"""Tests for utility functions: generate_execution_id."""

import uuid

from utils.execution import generate_execution_id


class TestGenerateExecutionId:

    def test_returns_string(self):
        result = generate_execution_id()
        assert isinstance(result, str)

    def test_returns_valid_uuid(self):
        result = generate_execution_id()
        # Should not raise
        parsed = uuid.UUID(result)
        assert str(parsed) == result

    def test_returns_uuid4_format(self):
        result = generate_execution_id()
        assert len(result) == 36
        parts = result.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_unique_ids(self):
        ids = {generate_execution_id() for _ in range(100)}
        assert len(ids) == 100

    def test_version_4(self):
        result = generate_execution_id()
        parsed = uuid.UUID(result)
        assert parsed.version == 4
