from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.security import UserSession
from sqlalchemy.ext.asyncio import AsyncSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_token(subject: str, token_type: str = "access", role: str = "user", expires_delta: timedelta | None = None, **claims) -> str:
    now = utcnow()
    if expires_delta is None:
        if token_type == "refresh":
            expires_delta = timedelta(days=settings.refresh_token_expire_days)
        else:
            expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": claims.pop("jti", secrets.token_urlsafe(24)),
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AppException("INVALID_TOKEN", "登录状态无效或已过期", 401) from exc
    if expected_type and payload.get("type") != expected_type:
        raise AppException("INVALID_TOKEN_TYPE", "令牌类型不正确", 401)
    return payload


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def make_token_pair(
    db: AsyncSession, user_id: int, session: UserSession | None = None
) -> dict[str, str]:
    now = utcnow()
    refresh_jti = secrets.token_urlsafe(32)
    if session is None:
        session = UserSession(
            user_id=user_id,
            refresh_jti_hash=token_hash(refresh_jti),
            created_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(session)
        await db.flush()
    else:
        session.refresh_jti_hash = token_hash(refresh_jti)
        session.last_used_at = now
        session.expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    await db.commit()
    return {
        "access_token": create_token(str(user_id), "access", "user", sid=session.id),
        "refresh_token": create_token(str(user_id), "refresh", "user", jti=refresh_jti, sid=session.id),
        "token_type": "bearer",
    }
