import pytest

from backend.services.passwords import hash_password, verify_password


def test_hash_password_is_not_plaintext():
    hashed = hash_password("hunter2-secret")
    assert hashed != "hunter2-secret"
    assert "hunter2-secret" not in hashed


def test_hashes_are_unique_per_call():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_wrong_password_rejected():
    hashed = hash_password("right-password")
    assert verify_password("wrong-password", hashed) is False


def test_verify_empty_password_rejected():
    hashed = hash_password("real-password")
    assert verify_password("", hashed) is False


def test_verify_malformed_hash_returns_false():
    assert verify_password("anything", "not-a-valid-argon2-hash") is False