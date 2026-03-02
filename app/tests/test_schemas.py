"""Comprehensive tests for Pydantic schema validation: auth, job, schedule schemas."""

import pytest
from pydantic import ValidationError

from schemas.auth import UserRegister, UserLogin, UserResponse, Token
from schemas.job import JobCreate, JobResponse, ALLOWED_TASK_TYPES, ALLOWED_METHODS
from schemas.schedule import ScheduleCreate, ScheduleResponse


# ── UserRegister Schema ───────────────────────────

class TestUserRegisterSchema:

    def test_valid_registration(self):
        user = UserRegister(username="john", email="john@example.com", password="TestPass1")
        assert user.username == "john"
        assert user.email == "john@example.com"
        assert user.password == "TestPass1"

    def test_password_min_length(self):
        with pytest.raises(ValidationError, match="at least 8 characters"):
            UserRegister(username="john", email="john@example.com", password="Short1")

    def test_password_max_length(self):
        long_pw = "A" * 129 + "a1"
        with pytest.raises(ValidationError, match="at most 128 characters"):
            UserRegister(username="john", email="john@example.com", password=long_pw)

    def test_password_requires_uppercase(self):
        with pytest.raises(ValidationError, match="uppercase"):
            UserRegister(username="john", email="john@example.com", password="alllower1")

    def test_password_requires_lowercase(self):
        with pytest.raises(ValidationError, match="lowercase"):
            UserRegister(username="john", email="john@example.com", password="ALLUPPER1")

    def test_password_requires_digit(self):
        with pytest.raises(ValidationError, match="digit"):
            UserRegister(username="john", email="john@example.com", password="NoDigitsHere")

    def test_password_exactly_8_chars(self):
        user = UserRegister(username="john", email="john@example.com", password="TestPas1")
        assert len(user.password) == 8

    def test_username_alphanumeric_underscore_only(self):
        with pytest.raises(ValidationError):
            UserRegister(username="john doe!", email="john@example.com", password="TestPass1")

    def test_username_min_length(self):
        with pytest.raises(ValidationError):
            UserRegister(username="ab", email="john@example.com", password="TestPass1")

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserRegister(username="john", email="not-an-email", password="TestPass1")

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            UserRegister(email="john@example.com", password="TestPass1")

    def test_missing_email(self):
        with pytest.raises(ValidationError):
            UserRegister(username="john", password="TestPass1")

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserRegister(username="john", email="john@example.com")


# ── UserLogin Schema ─────────────────────────────

class TestUserLoginSchema:

    def test_valid_login(self):
        login = UserLogin(username="john", password="pass123")
        assert login.username == "john"
        assert login.password == "pass123"

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            UserLogin(password="pass123")

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserLogin(username="john")


# ── UserResponse Schema ──────────────────────────

class TestUserResponseSchema:

    def test_from_attributes(self):
        from unittest.mock import MagicMock
        from datetime import datetime, timezone
        user = MagicMock()
        user.id = 1
        user.username = "john"
        user.email = "john@example.com"
        user.created_at = datetime.now(timezone.utc)
        result = UserResponse.model_validate(user)
        assert result.id == 1
        assert result.username == "john"


# ── Token Schema ──────────────────────────────────

class TestTokenSchema:

    def test_default_token_type(self):
        from datetime import datetime, timezone
        user_resp = UserResponse(id=1, username="john", email="john@example.com", created_at=datetime.now(timezone.utc))
        token = Token(access_token="abc123", user=user_resp)
        assert token.token_type == "bearer"

    def test_custom_token_type(self):
        from datetime import datetime, timezone
        user_resp = UserResponse(id=1, username="john", email="john@example.com", created_at=datetime.now(timezone.utc))
        token = Token(access_token="abc123", token_type="custom", user=user_resp)
        assert token.token_type == "custom"


# ── JobCreate Schema ─────────────────────────────

class TestJobCreateSchema:

    # --- api_call task type ---

    def test_api_call_valid(self):
        job = JobCreate(
            name="API Job",
            task_type="api_call",
            payload={"url": "https://example.com", "method": "GET"},
        )
        assert job.task_type == "api_call"

    def test_api_call_default_method(self):
        job = JobCreate(
            name="API Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
        )
        assert job.payload["url"] == "https://example.com"

    def test_api_call_missing_url(self):
        with pytest.raises(ValidationError, match="non-empty 'url'"):
            JobCreate(name="API Job", task_type="api_call", payload={})

    def test_api_call_empty_url(self):
        with pytest.raises(ValidationError, match="non-empty 'url'"):
            JobCreate(name="API Job", task_type="api_call", payload={"url": ""})

    def test_api_call_invalid_method(self):
        with pytest.raises(ValidationError, match="Invalid HTTP method"):
            JobCreate(
                name="API Job",
                task_type="api_call",
                payload={"url": "https://example.com", "method": "PATCH"},
            )

    def test_api_call_all_valid_methods(self):
        for method in ALLOWED_METHODS:
            job = JobCreate(
                name="API Job",
                task_type="api_call",
                payload={"url": "https://example.com", "method": method},
            )
            assert job is not None

    def test_api_call_method_case_insensitive(self):
        job = JobCreate(
            name="API Job",
            task_type="api_call",
            payload={"url": "https://example.com", "method": "post"},
        )
        assert job is not None

    # --- string_manipulation task type ---

    def test_string_manipulation_valid(self):
        job = JobCreate(
            name="String Job",
            task_type="string_manipulation",
            payload={"input": "hello world"},
        )
        assert job.task_type == "string_manipulation"

    def test_string_manipulation_empty_input(self):
        with pytest.raises(ValidationError, match="non-empty 'input'"):
            JobCreate(
                name="String Job",
                task_type="string_manipulation",
                payload={"input": ""},
            )

    def test_string_manipulation_missing_input(self):
        with pytest.raises(ValidationError, match="non-empty 'input'"):
            JobCreate(
                name="String Job",
                task_type="string_manipulation",
                payload={},
            )

    def test_string_manipulation_invalid_chars(self):
        with pytest.raises(ValidationError, match="only letters"):
            JobCreate(
                name="String Job",
                task_type="string_manipulation",
                payload={"input": "hello123"},
            )

    def test_string_manipulation_special_chars_rejected(self):
        with pytest.raises(ValidationError, match="only letters"):
            JobCreate(
                name="String Job",
                task_type="string_manipulation",
                payload={"input": "hello!@#"},
            )

    def test_string_manipulation_letters_and_spaces_only(self):
        job = JobCreate(
            name="String Job",
            task_type="string_manipulation",
            payload={"input": "Hello World Test"},
        )
        assert job.payload["input"] == "Hello World Test"

    # --- math task type ---

    def test_math_valid(self):
        job = JobCreate(name="Math Job", task_type="math", payload={"expression": "2 + 3"})
        assert job.task_type == "math"

    def test_math_complex_expression(self):
        job = JobCreate(name="Math Job", task_type="math", payload={"expression": "(2 + 3) * 4 / 2"})
        assert job is not None

    def test_math_empty_expression(self):
        with pytest.raises(ValidationError, match="non-empty 'expression'"):
            JobCreate(name="Math Job", task_type="math", payload={"expression": ""})

    def test_math_missing_expression(self):
        with pytest.raises(ValidationError, match="non-empty 'expression'"):
            JobCreate(name="Math Job", task_type="math", payload={})

    def test_math_invalid_chars(self):
        with pytest.raises(ValidationError, match="Invalid math expression"):
            JobCreate(name="Math Job", task_type="math", payload={"expression": "rm -rf /"})

    def test_math_import_blocked(self):
        with pytest.raises(ValidationError, match="Invalid math expression"):
            JobCreate(name="Math Job", task_type="math", payload={"expression": "__import__('os')"})

    def test_math_unevaluable_expression(self):
        with pytest.raises(ValidationError, match="cannot be evaluated"):
            JobCreate(name="Math Job", task_type="math", payload={"expression": "2 +"})

    def test_math_division(self):
        job = JobCreate(name="Math Job", task_type="math", payload={"expression": "10 / 3"})
        assert job is not None

    def test_math_decimals(self):
        job = JobCreate(name="Math Job", task_type="math", payload={"expression": "3.14 * 2"})
        assert job is not None

    # --- Invalid task type ---

    def test_unknown_task_type(self):
        with pytest.raises(ValidationError, match="Invalid task_type"):
            JobCreate(name="Bad Job", task_type="email", payload={})

    # --- Name validation ---

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(name="", task_type="api_call", payload={"url": "https://example.com"})

    # --- Rate limit ---

    def test_default_rate_limit(self):
        job = JobCreate(
            name="API Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
        )
        assert job.rate_limit_per_min == 60

    def test_custom_rate_limit(self):
        job = JobCreate(
            name="API Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=30,
        )
        assert job.rate_limit_per_min == 30

    def test_rate_limit_below_1_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(
                name="API Job",
                task_type="api_call",
                payload={"url": "https://example.com"},
                rate_limit_per_min=0,
            )

    # --- Allowed task types ---

    def test_allowed_task_types_set(self):
        assert ALLOWED_TASK_TYPES == {"api_call", "string_manipulation", "math"}

    def test_allowed_methods_set(self):
        assert ALLOWED_METHODS == {"GET", "POST", "PUT", "DELETE"}


# ── JobResponse Schema ───────────────────────────

class TestJobResponseSchema:

    def test_from_attributes(self):
        from unittest.mock import MagicMock
        job = MagicMock()
        job.id = 1
        job.name = "Test"
        job.task_type = "api_call"
        job.payload = {"url": "https://example.com"}
        job.rate_limit_per_min = 60
        job.is_active = True
        result = JobResponse.model_validate(job)
        assert result.id == 1
        assert result.is_active is True


# ── ScheduleCreate Schema ────────────────────────

class TestScheduleCreateSchema:

    def test_valid_cron(self):
        schedule = ScheduleCreate(cron_expression="*/5 * * * *")
        assert schedule.cron_expression == "*/5 * * * *"

    def test_max_runs_none_default(self):
        schedule = ScheduleCreate(cron_expression="*/5 * * * *")
        assert schedule.max_runs is None

    def test_max_runs_valid(self):
        schedule = ScheduleCreate(cron_expression="*/5 * * * *", max_runs=10)
        assert schedule.max_runs == 10

    def test_max_runs_below_1_rejected(self):
        with pytest.raises(ValidationError):
            ScheduleCreate(cron_expression="*/5 * * * *", max_runs=0)

    def test_max_runs_negative_rejected(self):
        with pytest.raises(ValidationError):
            ScheduleCreate(cron_expression="*/5 * * * *", max_runs=-1)

    def test_max_runs_exactly_1(self):
        schedule = ScheduleCreate(cron_expression="*/5 * * * *", max_runs=1)
        assert schedule.max_runs == 1

    def test_missing_cron_expression(self):
        with pytest.raises(ValidationError):
            ScheduleCreate()


# ── ScheduleResponse Schema ──────────────────────

class TestScheduleResponseSchema:

    def test_from_attributes(self):
        from unittest.mock import MagicMock
        from datetime import datetime, timezone
        sched = MagicMock()
        sched.id = 1
        sched.job_id = 1
        sched.cron_expression = "*/5 * * * *"
        sched.next_run_at = datetime.now(timezone.utc)
        sched.status = "active"
        sched.max_runs = None
        sched.run_count = 0
        result = ScheduleResponse.model_validate(sched)
        assert result.id == 1
        assert result.status == "active"
