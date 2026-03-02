import re
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Dict

ALLOWED_TASK_TYPES = {"api_call", "string_manipulation", "math"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}
_SAFE_STRING_RE = re.compile(r"^[a-zA-Z\s]+$")
_SAFE_MATH_RE = re.compile(r"^[\d\s\+\-\*/\(\)\.]+$")


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1)
    task_type: str = Field(..., examples=["api_call", "string_manipulation", "math"])
    payload: Dict
    rate_limit_per_min: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def validate_payload_for_task_type(self):
        if self.task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(
                f"Invalid task_type '{self.task_type}'. Must be one of: {', '.join(sorted(ALLOWED_TASK_TYPES))}"
            )

        if self.task_type == "api_call":
            url = self.payload.get("url", "")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("api_call payload must contain a non-empty 'url' string")
            method = self.payload.get("method", "GET").upper()
            if method not in ALLOWED_METHODS:
                raise ValueError(f"Invalid HTTP method '{method}'. Must be one of: {', '.join(sorted(ALLOWED_METHODS))}")

        elif self.task_type == "string_manipulation":
            text = self.payload.get("input", "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("string_manipulation payload must contain a non-empty 'input' string")
            if not _SAFE_STRING_RE.match(text):
                raise ValueError("Invalid input: only letters (a-z, A-Z) and spaces are allowed")

        elif self.task_type == "math":
            expression = self.payload.get("expression", "")
            if not isinstance(expression, str) or not expression.strip():
                raise ValueError("math payload must contain a non-empty 'expression' string")
            if not _SAFE_MATH_RE.match(expression):
                raise ValueError(
                    "Invalid math expression: only numbers and + - * / ( ) . are allowed"
                )
            try:
                eval(expression, {"__builtins__": {}}, {})  # noqa: S307
            except Exception:
                raise ValueError(
                    f"Invalid math expression: '{expression}' cannot be evaluated"
                )

        return self


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    task_type: str
    payload: Dict
    rate_limit_per_min: int
    is_active: bool
