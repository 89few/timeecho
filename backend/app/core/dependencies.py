from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import decode_token
from app.db.session import get_db_session, redis_client
from app.models.user import User, UserStatus
from app.models.security import UserSession
from app.models.security import AdminRole, AdminSession, AdminUser
from app.core.security import token_hash


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def get_db() -> AsyncSession:
    async for session in get_db_session():
        yield session


async def get_redis() -> Redis:
    return redis_client


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    payload = decode_token(token, expected_type="access")
    if payload.get("role") != "user":
        raise AppException("FORBIDDEN", "无权访问", 403)
    user_id = int(payload["sub"])
    session_id = payload.get("sid")
    if not session_id:
        raise AppException("SESSION_REVOKED", "登录状态已失效，请重新登录", 401)
    session = await db.get(UserSession, int(session_id))
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if not session or session.user_id != user_id or session.revoked_at or expires_at <= datetime.now(timezone.utc):
        raise AppException("SESSION_REVOKED", "登录状态已失效，请重新登录", 401)
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status in {UserStatus.BANNED, UserStatus.DEACTIVATED}:
        raise AppException("USER_BANNED", "账号已被封禁", 403)
    if user.must_change_password and request.url.path not in {
        f"{settings.api_prefix}/auth/password/change",
        f"{settings.api_prefix}/auth/logout",
    }:
        raise AppException("PASSWORD_CHANGE_REQUIRED", "请先修改临时密码", 403)
    if user.status == UserStatus.MUTED and _as_utc(user.muted_until) and _as_utc(user.muted_until) > datetime.now(timezone.utc):
        # muted users can still read / me, but mutation endpoints call ensure_user_can_post.
        return user
    return user


async def get_current_admin(
    request: Request,
    te_admin_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not te_admin_session and settings.app_env.lower() == "test":
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            te_admin_session = authorization[7:].strip()
    if not te_admin_session:
        raise AppException("ADMIN_UNAUTHORIZED", "管理员登录已失效", 401)
    session = await db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(te_admin_session))
    )
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if not session or session.revoked_at or expires_at <= now:
        raise AppException("ADMIN_UNAUTHORIZED", "管理员登录已失效", 401)
    admin = await db.get(AdminUser, session.admin_id)
    if not admin or not admin.enabled:
        raise AppException("ADMIN_DISABLED", "管理员账号已禁用", 403)
    request.state.admin = admin
    request.state.admin_session = session
    return admin


def require_admin_roles(*roles: AdminRole):
    async def dependency(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.role not in roles:
            raise AppException("ADMIN_FORBIDDEN", "管理员权限不足", 403)
        return admin
    return dependency


def ensure_user_can_post(user: User) -> None:
    now = datetime.now(timezone.utc)
    if user.status == UserStatus.BANNED:
        raise AppException("USER_BANNED", "账号已被封禁", 403)
    if user.status == UserStatus.MUTED and _as_utc(user.muted_until) and _as_utc(user.muted_until) > now:
        raise AppException("USER_MUTED", "账号仍处于禁言中", 403)
