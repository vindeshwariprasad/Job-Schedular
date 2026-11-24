"""Tests for idempotency key support on POST /jobs."""

import json

import pytest
from services.idempotency_service import (
    IdempotencyResult,
    claim_idempotency_key,
    compute_payload_hash,
    store_idempotency_response,
    validate_idempotency_key,
)


class TestComputePayloadHash:
    def test_deterministic(self):
        payload = {"name": "Test", "type": "api_call"}
        h1 = compute_payload_hash(payload)
        h2 = compute_payload_hash(payload)
        assert h1 == h2

    def test_key_order_independent(self):
        h1 = compute_payload_hash({"a": 1, "b": 2})
        h2 = compute_payload_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_payloads_different_hashes(self):
        h1 = compute_payload_hash({"name": "A"})
        h2 = compute_payload_hash({"name": "B"})
        assert h1 != h2


class TestValidateIdempotencyKey:
    def test_valid_key(self):
        validate_idempotency_key("abc-123")

    def test_max_length_key(self):
        validate_idempotency_key("x" * 256)

    def test_too_long_key(self):
        with pytest.raises(ValueError, match="256"):
            validate_idempotency_key("x" * 257)


class TestClaimIdempotencyKey:
    def test_new_key_claimed(self, fake_redis):
        result = claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        assert result.result == IdempotencyResult.NEW

    def test_duplicate_key_same_payload_returns_cached(self, fake_redis):
        # First: claim and store
        claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        store_idempotency_response(fake_redis, 1, "key-1", "hash-1", {"id": 42})

        # Second: same key same hash
        result = claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        assert result.result == IdempotencyResult.CACHED
        assert result.cached_response == {"id": 42}

    def test_duplicate_key_different_payload_returns_mismatch(self, fake_redis):
        claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        store_idempotency_response(fake_redis, 1, "key-1", "hash-1", {"id": 42})

        result = claim_idempotency_key(fake_redis, 1, "key-1", "hash-DIFFERENT")
        assert result.result == IdempotencyResult.MISMATCH

    def test_in_progress_placeholder(self, fake_redis):
        # First request claims with placeholder
        claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        # Second request sees placeholder
        result = claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        assert result.result == IdempotencyResult.IN_PROGRESS

    def test_different_users_different_keys(self, fake_redis):
        # User 1 claims key
        claim_idempotency_key(fake_redis, 1, "same-key", "hash-1")
        store_idempotency_response(fake_redis, 1, "same-key", "hash-1", {"id": 1})

        # User 2 claims same key string — should get NEW since it's user-scoped
        r2 = claim_idempotency_key(fake_redis, 2, "same-key", "hash-1")
        assert r2.result == IdempotencyResult.NEW


class TestStoreIdempotencyResponse:
    def test_stores_and_retrieves(self, fake_redis):
        claim_idempotency_key(fake_redis, 1, "key-1", "hash-1")
        store_idempotency_response(fake_redis, 1, "key-1", "hash-1", {"id": 99, "name": "Test"})

        # Verify stored
        raw = fake_redis.get("idempotency:1:key-1")
        data = json.loads(raw)
        assert data["response"]["id"] == 99
        assert data["hash"] == "hash-1"
