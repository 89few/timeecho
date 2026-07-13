from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis, oauth2_scheme
from app.core.config import settings
from app.core.exceptions import AppException, ok
from app.schemas.auth import (
    EmailCodeRequest,
    EmailRegisterRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordLoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SendCodeRequest,
)
from app.services.auth_service import (
    login_with_code,
    login_with_password,
    refresh_access_token,
    register_with_email,
    request_password_reset,
    reset_password,
    send_code,
    send_email_code,
    hash_password,
    verify_password,
)
from sqlalchemy import update
from app.models.user import User
from app.models.security import UserSession
from app.core.security import decode_token, utcnow
from app.core.crypto import phone_hash

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/send-code")
async def send_login_code(
    payload: SendCodeRequest,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    if not settings.phone_auto_registration_enabled:
        exists = await db.scalar(
            select(User.id).where(User.phone_hash == phone_hash(payload.phone))
        )
        if not exists:
            raise AppException("ACCOUNT_NOT_FOUND", "账号不存在", 404)
    await send_code(redis, payload.phone)
    data = {}
    if settings.app_env.lower() in {"dev", "development", "local", "test"} and settings.dev_sms_code:
        data["dev_code"] = settings.dev_sms_code
    return ok(data, "验证码已发送")


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    data = await login_with_code(db, redis, payload.phone, payload.code, payload.city)
    return ok(data)


@router.post("/email/send-code")
async def send_email_verification_code(
    payload: EmailCodeRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    normalized_email = str(payload.email).strip().lower()
    user_exists = bool(
        await db.scalar(
            select(User.id).where(func.lower(User.email) == normalized_email)
        )
    )
    if payload.purpose == "register" and user_exists:
        raise AppException("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409)
    if payload.purpose == "reset" and not user_exists:
        raise AppException("ACCOUNT_NOT_FOUND", "该邮箱尚未注册", 404)
    dev_code = await send_email_code(redis, str(payload.email), payload.purpose)
    data = {"expires_in": settings.email_code_expire_minutes * 60}
    if dev_code:
        data["dev_code"] = dev_code
    return ok(data, "验证码已发送")


@router.post("/email/register")
async def email_register(
    payload: EmailRegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await register_with_email(
        db,
        redis,
        str(payload.email),
        payload.password,
        payload.code,
        payload.username,
        payload.city,
        payload.avatar_url,
    )
    return ok(data, "注册成功")


@router.post("/email/login")
async def email_login(
    payload: PasswordLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    return ok(await login_with_password(db, redis, payload.identifier, payload.password), "登录成功")


@router.post("/password/forgot")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    dev_code = await request_password_reset(db, redis, str(payload.email))
    data = {"expires_in": settings.email_code_expire_minutes * 60}
    if dev_code:
        data["dev_code"] = dev_code
    return ok(data, "如果该邮箱已注册，重置验证码将发送至邮箱")


@router.post("/password/reset")
async def password_reset(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await reset_password(db, redis, str(payload.email), payload.code, payload.new_password)
    return ok(message="密码已重置，请重新登录")


@router.post("/password/change")
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
        raise AppException("INVALID_CREDENTIALS", "当前密码错误", 400)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    await db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await db.commit()
    return ok(message="密码已修改，请重新登录")


@router.post("/refresh")
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return ok(await refresh_access_token(db, payload.refresh_token))


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(token, expected_type="access")
    session = await db.get(UserSession, int(payload.get("sid") or 0))
    if session and session.user_id == int(payload["sub"]):
        session.revoked_at = utcnow()
        await db.commit()
    return ok(message="已退出登录")


@router.post("/ws-ticket")
async def websocket_ticket(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    ticket = secrets.token_urlsafe(32)
    await redis.set(f"ws:ticket:{ticket}", str(user.id), ex=60)
    return ok({"ticket": ticket, "expires_in": 60})
