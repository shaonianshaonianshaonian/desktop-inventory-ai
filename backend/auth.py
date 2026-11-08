"""密码散列、JWT 签发与 FastAPI 登录依赖。"""

import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from backend.database import SessionLocal, User


JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))
_configured_secret = os.getenv("JWT_SECRET")
if _configured_secret is not None and len(_configured_secret) < 32:
    raise RuntimeError("JWT_SECRET 至少需要 32 个字符")
JWT_SECRET = _configured_secret or secrets.token_urlsafe(48)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    if not 8 <= len(password) <= 128:
        raise ValueError("密码长度必须为 8 到 128 个字符")
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = _b64url_decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64url_decode(salt_text),
            int(iterations_text),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp()),
    }
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{segments[0]}.{segments[1]}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        header_text, payload_text, signature_text = token.split(".")
        signing_input = f"{header_text}.{payload_text}".encode("ascii")
        expected = hmac.new(
            JWT_SECRET.encode(), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_text)):
            raise ValueError("签名无效")
        header = json.loads(_b64url_decode(header_text))
        payload = json.loads(_b64url_decode(payload_text))
        if header.get("alg") != JWT_ALGORITHM:
            raise ValueError("算法无效")
        if not isinstance(payload.get("exp"), int):
            raise ValueError("缺少过期时间")
        if payload["exp"] <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("令牌已过期")
        if not str(payload.get("sub", "")).isdigit():
            raise ValueError("用户标识无效")
        return payload
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_access_token(token)
    with SessionLocal() as session:
        user = session.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已停用",
                headers={"WWW-Authenticate": "Bearer"},
            )
        session.expunge(user)
        return user


def authenticate_user(username: str, password: str) -> User | None:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None or not verify_password(password, user.password_hash):
            return None
        session.expunge(user)
        return user
