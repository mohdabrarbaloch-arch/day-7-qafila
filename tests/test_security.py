"""Password hashing and JWT behaviour."""

from __future__ import annotations

import pytest

from app.security import (
    MAX_PASSWORD_BYTES,
    PasswordTooLongError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_the_password():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert hashed.startswith("$2b$")


def test_verify_accepts_the_right_password():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed) is True


def test_verify_rejects_the_wrong_password():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("wrong-horse-battery", hashed) is False


def test_same_password_hashes_differently():
    # bcrypt salts each hash; identical output would mean a broken salt.
    assert hash_password("same-password") != hash_password("same-password")


def test_password_over_72_bytes_is_rejected_not_truncated():
    too_long = "a" * (MAX_PASSWORD_BYTES + 1)
    with pytest.raises(PasswordTooLongError):
        hash_password(too_long)


def test_verify_returns_false_for_over_long_input():
    hashed = hash_password("a" * MAX_PASSWORD_BYTES)
    assert verify_password("a" * (MAX_PASSWORD_BYTES + 1), hashed) is False


def test_verify_handles_malformed_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_token_round_trips():
    token = create_access_token("user-123", "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"


def test_token_with_wrong_secret_fails():
    import jwt

    token = create_access_token("user-123", "admin")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "a-different-secret", algorithms=["HS256"])
