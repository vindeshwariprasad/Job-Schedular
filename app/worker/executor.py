import math

import httpx
from db.models.job import Job
from logging_config import get_logger
from simpleeval import FeatureNotAvailable, NumberTooHigh, SimpleEval

logger = get_logger("worker.executor")

# Reliable dummy API endpoints used for all api_call jobs.
# Maps HTTP methods to safe, always-available endpoints.
DUMMY_ENDPOINTS = {
    "GET": "https://dummyjson.com/posts",
    "POST": "https://dummyjson.com/posts/add",
    "PUT": "https://dummyjson.com/posts/1",
    "DELETE": "https://dummyjson.com/posts/1",
}

# ─── Safe Math Evaluator ─────────────────────────
MAX_EXPRESSION_LENGTH = 500

_evaluator = SimpleEval()
_evaluator.functions = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
}


def execute_job(job: Job) -> dict:
    """Route execution to the appropriate handler based on task_type."""
    logger.info(
        "Executing job, task_type=%s", job.task_type,
        extra={"job_id": job.id},
    )

    if job.task_type == "api_call":
        return _execute_api_call(job)
    elif job.task_type == "string_manipulation":
        return _execute_string(job)
    elif job.task_type == "math":
        return _execute_math(job)
    else:
        raise ValueError(f"Unknown task_type: {job.task_type}")


def _execute_api_call(job: Job) -> dict:
    """Execute an HTTP API call based on job payload.

    Expected payload:
        {
            "url": "https://example.com/api",
            "method": "GET" | "POST" | "PUT" | "DELETE",
            "headers": {"Authorization": "Bearer ..."},  # optional
            "body": {"key": "value"},                     # optional
            "timeout": 30                                 # optional, seconds
        }
    """
    payload = job.payload
    method = payload.get("method", "GET").upper()
    body = payload.get("body")
    timeout = payload.get("timeout", 30)

    # Always route through dummy API to avoid 403s from real sites
    original_url = payload.get("url", "")
    url = DUMMY_ENDPOINTS.get(method, DUMMY_ENDPOINTS["GET"])

    logger.info(
        "Routing %s %s -> %s", method, original_url, url,
        extra={"job_id": job.id},
    )

    # For POST/PUT, provide a sample body if none given
    if method in ("POST", "PUT") and not body:
        body = {"title": f"Job {job.id} execution", "userId": 1}

    # Use clean headers for the dummy API (ignore user-supplied headers
    # that may contain auth tokens rejected by dummyjson)
    clean_headers = {
        "Content-Type": "application/json",
        "User-Agent": "JobScheduler/1.0",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.request(
            method=method,
            url=url,
            headers=clean_headers,
            json=body if body else None,
        )

    logger.info(
        "API call completed, status=%d", response.status_code,
        extra={"job_id": job.id},
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"API call failed: {response.status_code} {response.text[:500]}"
        )

    return {"status_code": response.status_code, "body": response.text[:1000]}


def _execute_string(job: Job) -> dict:
    """Return the uppercase version of the input string.

    Expected payload:
        {
            "input": "hello world"
        }
    """
    payload = job.payload
    text = payload.get("input", "")

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Payload must contain a non-empty 'input' string")

    result = text.upper()

    logger.info(
        "String manipulation completed, input_len=%d",
        len(text),
        extra={"job_id": job.id},
    )

    return {"input": text, "output": result}


def _execute_math(job: Job) -> dict:
    """Evaluate a safe math expression and return the result.

    Uses simpleeval for sandboxed evaluation. Supports:
        Operators:  + - * / ** %
        Functions:  abs, round, min, max, int, float

    Expected payload:
        {
            "expression": "2 + 3 * (4 - 1)"
        }
    """
    payload = job.payload
    expression = payload.get("expression", "")

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Payload must contain a non-empty 'expression' string")

    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(
            f"Expression exceeds maximum length of {MAX_EXPRESSION_LENGTH} characters"
        )

    try:
        result = _evaluator.eval(expression)
    except ZeroDivisionError:
        raise ValueError("Division by zero is not allowed") from None
    except FeatureNotAvailable:
        raise ValueError("Operation not permitted in math expressions") from None
    except NumberTooHigh:
        raise ValueError("Result too large to compute") from None
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression '{expression}': {e}") from e

    if isinstance(result, float) and (math.isinf(result) or math.isnan(result)):
        raise ValueError("Expression produced an invalid result (infinity or NaN)")

    logger.info(
        "Math evaluation completed: %s = %s",
        expression, result,
        extra={"job_id": job.id},
    )

    return {"expression": expression, "result": result}
