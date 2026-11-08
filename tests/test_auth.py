import pytest
from fastapi import HTTPException

from backend.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.database import User


def test_password_hash_round_trip():
    encoded = hash_password("correct-password")
    assert verify_password("correct-password", encoded)
    assert not verify_password("wrong-password", encoded)
    assert "correct-password" not in encoded


def test_jwt_rejects_tampering():
    token = create_access_token(User(id=7, username="tester", password_hash="unused"))
    assert decode_access_token(token)["sub"] == "7"
    header, payload, signature = token.split(".")
    replacement = "A" if payload[5] != "A" else "B"
    tampered = f"{header}.{payload[:5]}{replacement}{payload[6:]}.{signature}"
    with pytest.raises(HTTPException):
        decode_access_token(tampered)
