"""Comprehensive unit tests for auth.py: password hashing, JWT tokens, user retrieval."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from auth import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from db.models.user import User
from jose import jwt

# ── Password Hashing ──────────────────────────────

class TestHashPassword:

    def test_returns_string(self):
        result = hash_password("mypassword")
        assert isinstance(result, str)

    def test_returns_bcrypt_hash(self):
        result = hash_password("mypassword")
        assert result.startswith("$2b$") or result.startswith("$2a$")

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_same_password_different_salts(self):
        h1 = hash_password("samepass")
        h2 = hash_password("samepass")
        assert h1 != h2  # bcrypt uses random salt

    def test_handles_unicode(self):
        result = hash_password("pässwörd")
        assert isinstance(result, str)

    def test_handles_empty_string(self):
        result = hash_password("")
        assert isinstance(result, str)


class TestVerifyPassword:

    def test_correct_password(self):
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_case_sensitive(self):
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False

    def test_unicode_password(self):
        hashed = hash_password("pässwörd")
        assert verify_password("pässwörd", hashed) is True
        assert verify_password("password", hashed) is False


# ── JWT Token Creation ────────────────────────────

class TestCreateAccessToken:

    def test_returns_string(self):
        token = create_access_token({"sub": "1"})
        assert isinstance(token, str)

    def test_contains_sub_claim(self):
        token = create_access_token({"sub": "42"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"

    def test_contains_exp_claim(self):
        token = create_access_token({"sub": "1"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_exp_is_future(self):
        token = create_access_token({"sub": "1"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        now = datetime.now(UTC)
        assert exp > now

    def test_exp_approximately_24_hours(self):
        token = create_access_token({"sub": "1"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        now = datetime.now(UTC)
        diff = exp - now
        assert timedelta(hours=23) < diff < timedelta(hours=25)

    def test_preserves_extra_data(self):
        token = create_access_token({"sub": "1", "role": "admin"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"

    def test_does_not_mutate_input(self):
        data = {"sub": "1"}
        create_access_token(data)
        assert "exp" not in data  # original dict unchanged


# ── Token Decoding ────────────────────────────────

class TestDecodeToken:

    def test_valid_token_returns_user_id(self):
        token = create_access_token({"sub": "42"})
        assert decode_token(token) == 42

    def test_invalid_token_returns_none(self):
        assert decode_token("not-a-valid-token") is None

    def test_expired_token_returns_none(self):
        expired = jwt.encode(
            {"sub": "1", "exp": datetime.now(UTC) - timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        assert decode_token(expired) is None

    def test_missing_sub_returns_none(self):
        token = jwt.encode(
            {"exp": datetime.now(UTC) + timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        assert decode_token(token) is None

    def test_wrong_secret_returns_none(self):
        token = jwt.encode(
            {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)},
            "wrong-secret-key",
            algorithm=ALGORITHM,
        )
        assert decode_token(token) is None

    def test_non_integer_sub_returns_none(self):
        token = jwt.encode(
            {"sub": "not-a-number", "exp": datetime.now(UTC) + timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        assert decode_token(token) is None

    def test_empty_string_returns_none(self):
        assert decode_token("") is None


# ── get_current_user (async) ─────────────────────

class TestGetCurrentUser:

    async def test_valid_token_returns_user(self, async_db):
        user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("TestPass123"),
        )
        async_db.add(user)
        await async_db.commit()

        token = create_access_token({"sub": str(user.id)})
        credentials = MagicMock()
        credentials.credentials = token

        result = await get_current_user(credentials=credentials, db=async_db)
        assert result.id == user.id
        assert result.username == "testuser"

    async def test_invalid_token_raises_401(self, async_db):
        from fastapi import HTTPException
        credentials = MagicMock()
        credentials.credentials = "invalid-token"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=async_db)
        assert exc_info.value.status_code == 401

    async def test_expired_token_raises_401(self, async_db):
        from fastapi import HTTPException
        expired = jwt.encode(
            {"sub": "1", "exp": datetime.now(UTC) - timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        credentials = MagicMock()
        credentials.credentials = expired

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=async_db)
        assert exc_info.value.status_code == 401

    async def test_missing_sub_raises_401(self, async_db):
        from fastapi import HTTPException
        token = jwt.encode(
            {"exp": datetime.now(UTC) + timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=async_db)
        assert exc_info.value.status_code == 401
        assert "missing subject" in exc_info.value.detail

    async def test_nonexistent_user_raises_401(self, async_db):
        from fastapi import HTTPException
        token = create_access_token({"sub": "99999"})
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=async_db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    async def test_non_integer_sub_raises_401(self, async_db):
        from fastapi import HTTPException
        token = jwt.encode(
            {"sub": "not-a-number", "exp": datetime.now(UTC) + timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=async_db)
        assert exc_info.value.status_code == 401


# ── Constants ─────────────────────────────────────

class TestAuthConstants:

    def test_algorithm_is_hs256(self):
        assert ALGORITHM == "HS256"

    def test_token_expires_in_24_hours(self):
        assert ACCESS_TOKEN_EXPIRE_HOURS == 24

    def test_secret_key_is_set(self):
        assert SECRET_KEY is not None
        assert len(SECRET_KEY) > 0
