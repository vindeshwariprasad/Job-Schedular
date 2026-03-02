"""Tests for the job executor: api_call, string_manipulation, and math task types."""

from unittest.mock import patch, MagicMock
import pytest

from worker.executor import execute_job, _execute_api_call, _execute_string, _execute_math


def _make_job(task_type="api_call", payload=None):
    """Create a mock Job object."""
    job = MagicMock()
    job.id = 1
    job.task_type = task_type
    job.payload = payload or {}
    return job


class TestExecuteJobRouting:

    def test_routes_api_call(self):
        """api_call task_type should route to _execute_api_call."""
        job = _make_job("api_call", {"url": "https://example.com"})
        with patch("worker.executor._execute_api_call", return_value={"ok": True}) as mock:
            execute_job(job)
            mock.assert_called_once_with(job)

    def test_routes_string_manipulation(self):
        """string_manipulation task_type should route to _execute_string."""
        job = _make_job("string_manipulation", {"input": "hello"})
        with patch("worker.executor._execute_string", return_value={"ok": True}) as mock:
            execute_job(job)
            mock.assert_called_once_with(job)

    def test_routes_math(self):
        """math task_type should route to _execute_math."""
        job = _make_job("math", {"expression": "1+1"})
        with patch("worker.executor._execute_math", return_value={"ok": True}) as mock:
            execute_job(job)
            mock.assert_called_once_with(job)

    def test_unknown_type_raises(self):
        """Unknown task_type should raise ValueError."""
        job = _make_job("email", {})
        with pytest.raises(ValueError, match="Unknown task_type"):
            execute_job(job)


class TestApiCallExecutor:

    def test_successful_get(self):
        """A 200 response should return status_code and body."""
        job = _make_job("api_call", {"url": "https://example.com", "method": "GET"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": "ok"}'

        with patch("worker.executor.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                request=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            result = _execute_api_call(job)

        assert result["status_code"] == 200

    def test_4xx_raises(self):
        """A 4xx response should raise RuntimeError."""
        job = _make_job("api_call", {"url": "https://example.com"})
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("worker.executor.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                request=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(RuntimeError, match="API call failed: 404"):
                _execute_api_call(job)


class TestStringExecutor:

    def test_valid_string(self):
        """A valid string input should return its uppercase version."""
        job = _make_job("string_manipulation", {"input": "hello world"})
        result = _execute_string(job)
        assert result["input"] == "hello world"
        assert result["output"] == "HELLO WORLD"

    def test_empty_input_raises(self):
        """Empty or missing input should raise ValueError."""
        job = _make_job("string_manipulation", {"input": ""})
        with pytest.raises(ValueError, match="non-empty"):
            _execute_string(job)

    def test_missing_input_raises(self):
        """Missing input key should raise ValueError."""
        job = _make_job("string_manipulation", {})
        with pytest.raises(ValueError, match="non-empty"):
            _execute_string(job)


class TestMathExecutor:

    def test_valid_expression(self):
        """A valid math expression should return the correct result."""
        job = _make_job("math", {"expression": "2 + 3 * 4"})
        result = _execute_math(job)
        assert result["expression"] == "2 + 3 * 4"
        assert result["result"] == 14

    def test_parentheses(self):
        """Parentheses should be handled correctly."""
        job = _make_job("math", {"expression": "(2 + 3) * 4"})
        result = _execute_math(job)
        assert result["result"] == 20

    def test_division(self):
        """Division should work."""
        job = _make_job("math", {"expression": "10 / 4"})
        result = _execute_math(job)
        assert result["result"] == 2.5

    def test_invalid_expression_raises(self):
        """Expressions with letters or unsafe characters should be rejected."""
        job = _make_job("math", {"expression": "rm -rf /"})
        with pytest.raises(ValueError, match="Invalid math expression"):
            _execute_math(job)

    def test_empty_expression_raises(self):
        """Empty expression should raise ValueError."""
        job = _make_job("math", {"expression": ""})
        with pytest.raises(ValueError, match="non-empty"):
            _execute_math(job)

    def test_import_blocked(self):
        """Expressions with import attempts should be rejected."""
        job = _make_job("math", {"expression": "__import__('os')"})
        with pytest.raises(ValueError, match="Invalid math expression"):
            _execute_math(job)
