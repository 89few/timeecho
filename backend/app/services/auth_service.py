from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr

import bcrypt
from redis.asyncio import Redis
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import phone_hash
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit, incr_with_expire
from app.core.security import decode_token, make_token_pair, token_hash, utcnow
from app.models.security import UserSession
from sqlalchemy import update
from app.models.user import User, UserStatus
from app.services.user_service import get_or_create_user_by_phone


def _code_key(phone: str) -> str:
    return f"auth:code:{phone_hash(phone)}"


async def send_code(redis: Redis, phone: str) -> None:
    hashed = phone_hash(phone)
    await enforce_rate_limit(redis, f"limit:sms:60s:{hashed}", 1, 60, "验证码发送过于频繁，请 60 秒后再试")
    await enforce_rate_limit(redis, f"limit:sms:hour:{hashed}", 3, 3600, "该手机号 1 小时内验证码次数已达上限")
    await enforce_rate_limit(redis, f"limit:sms:day:{hashed}", 5, 86400, "该手机号今日验证码次数已达上限")
    await redis.set(_code_key(phone), settings.dev_sms_code, ex=300)


async def login_with_code(db: AsyncSession, redis: Redis, phone: str, code: str, city: str | None = None) -> dict:
    hashed = phone_hash(phone)
    fail_key = f"limit:login_fail:10m:{hashed}"
    fail_count = int(await redis.get(fail_key) or 0)
    if fail_count >= 5:
        raise AppException("LOGIN_LOCKED", "登录失败次数过多，请 10 分钟后再试", 429)

    saved_code = await redis.get(_code_key(phone))
    if not saved_code or saved_code != code:
        await incr_with_expire(redis, fail_key, 600)
        raise AppException("INVALID_CODE", "验证码错误或已过期", 400)

    await redis.delete(_code_key(phone), fail_key)
    if settings.phone_auto_registration_enabled:
        user = await get_or_create_user_by_phone(db, phone, city)
    else:
        user = await db.scalar(select(User).where(User.phone_hash == hashed))
        if not user:
            raise AppException("ACCOUNT_NOT_FOUND", "账号不存在", 404)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return {
        **(await make_token_pair(db, user.id)),
        "uid": user.uid,
        "anonymous_name": user.anonymous_name,
    }


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    payload = decode_token(refresh_token, expected_type="refresh")
    if payload.get("role") != "user":
        raise AppException("INVALID_TOKEN", "刷新令牌无效", 401)
    session = await db.get(UserSession, int(payload.get("sid") or 0))
    now = utcnow()
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if (
        not session
        or session.user_id != int(payload["sub"])
        or session.revoked_at
        or expires_at <= now
        or session.refresh_jti_hash != token_hash(str(payload.get("jti") or ""))
    ):
        raise AppException("SESSION_REVOKED", "登录状态已失效，请重新登录", 401)
    return await make_token_pair(db, session.user_id, session)


def normalize_email(email: str) -> str:
    """Return the canonical representation used for uniqueness and login."""
    return email.strip().lower()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def _validate_username(username: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]{2,20}", username):
        raise AppException("INVALID_USERNAME", "账号须为 2 至 20 位中文、字母、数字或下划线", 400)


def _email_digest(email: str) -> str:
    value = f"{normalize_email(email)}:{settings.server_salt}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _email_code_key(email: str, purpose: str) -> str:
    return f"auth:email_code:{purpose}:{_email_digest(email)}"


def _validate_password(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(password) < 8 or len(encoded) > 72:
        raise AppException("WEAK_PASSWORD", "密码须为 8 至 72 字节", 400)
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        raise AppException("WEAK_PASSWORD", "密码必须同时包含字母和数字", 400)


def hash_password(password: str) -> str:
    _validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def _send_email_sync(recipient: str, code: str, purpose: str) -> None:
    subject = "TimeEcho 注册验证码" if purpose == "register" else "TimeEcho 重置密码验证码"
    action = "完成注册" if purpose == "register" else "重置密码"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email or ""))
    message["To"] = recipient
    message.set_content(
        f"你的 TimeEcho 验证码是：{code}\n\n"
        f"验证码用于{action}，{settings.email_code_expire_minutes} 分钟内有效。"
        "如非本人操作，请忽略此邮件。"
    )
    message.add_alternative(
        f"""<!doctype html>
<html><body style="margin:0;background:#f7f3ea;font-family:Arial,sans-serif;color:#243047">
<div style="max-width:520px;margin:32px auto;padding:32px;background:#fffdf8;border-radius:24px">
  <div style="font-size:26px;font-weight:800;color:#6d5b8c">TimeEcho</div>
  <p style="margin-top:24px">Use this verification code to {action}:</p>
  <div style="margin:24px 0;padding:18px;text-align:center;background:#eee7f7;border-radius:16px;font-size:36px;font-weight:800;letter-spacing:8px">{code}</div>
  <p>This code expires in {settings.email_code_expire_minutes} minutes and can only be used once.</p>
  <p style="color:#7b8190;font-size:13px">If you did not request this, you can safely ignore this email.</p>
</div></body></html>""",
        subtype="html",
    )

    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


def _dev_email_code_available() -> bool:
    return settings.email_dev_code_enabled and settings.app_env.lower() in {"dev", "development", "local", "test"}


async def send_email_code(redis: Redis, email: str, purpose: str, *, deliver: bool = True) -> str | None:
    normalized = normalize_email(email)
    digest = _email_digest(normalized)
    # Email sending keeps its own anti-abuse guard even when general testing
    # limits for letters/chat/salvage are disabled.
    minute_count = await incr_with_expire(redis, f"limit:email:60s:{purpose}:{digest}", 60)
    if minute_count > 1:
        raise AppException("RATE_LIMITED", "验证码发送过于频繁，请 60 秒后再试", 429)
    hour_count = await incr_with_expire(redis, f"limit:email:hour:{purpose}:{digest}", 3600)
    if hour_count > 5:
        raise AppException("RATE_LIMITED", "该邮箱一小时内验证码次数已达上限", 429)

    dev_mode = _dev_email_code_available()
    if not _smtp_configured() and not dev_mode:
        raise AppException("EMAIL_NOT_CONFIGURED", "邮件服务尚未配置，请联系管理员", 503)

    code = settings.dev_email_code if dev_mode else f"{secrets.randbelow(1_000_000):06d}"
    await redis.set(
        _email_code_key(normalized, purpose),
        code,
        ex=max(1, settings.email_code_expire_minutes) * 60,
    )
    if deliver and _smtp_configured():
        try:
            await asyncio.to_thread(_send_email_sync, normalized, code, purpose)
        except (OSError, smtplib.SMTPException) as exc:
            await redis.delete(_email_code_key(normalized, purpose))
            raise AppException("EMAIL_SEND_FAILED", "验证码邮件发送失败，请稍后重试", 503) from exc
    return code if dev_mode else None


async def _consume_email_code(redis: Redis, email: str, purpose: str, code: str | None) -> bool:
    if not code:
        return False
    key = _email_code_key(email, purpose)
    saved = await redis.get(key)
    if not saved or not hmac.compare_digest(str(saved), code):
        raise AppException("INVALID_CODE", "验证码错误或已过期", 400)
    await redis.delete(key)
    return True


async def _make_unique_username(db: AsyncSession) -> str:
    for _ in range(20):
        candidate = f"echo_{secrets.token_hex(4)}"
        exists = await db.scalar(select(User.id).where(func.lower(User.username) == candidate))
        if not exists:
            return candidate
    raise AppException("USERNAME_GENERATION_FAILED", "暂时无法生成账号，请稍后重试", 503)


async def _email_auth_payload(db: AsyncSession, user: User) -> dict:
    return {
        **(await make_token_pair(db, user.id)),
        "user_id": user.id,
        "uid": user.uid,
        "email": user.email,
        "username": user.username,
        "anonymous_name": user.anonymous_name,
        "avatar_url": user.avatar_url,
        "email_verified": user.email_verified,
        "must_change_password": user.must_change_password,
    }


async def register_with_email(
    db: AsyncSession,
    redis: Redis,
    email: str,
    password: str,
    code: str | None = None,
    username: str | None = None,
    city: str | None = None,
    avatar_url: str | None = None,
) -> dict:
    normalized_email = normalize_email(email)
    # Validate before consuming a one-time code, so a typo in another field
    # does not force the user to request a second email.
    _validate_password(password)
    existing = await db.scalar(select(User.id).where(func.lower(User.email) == normalized_email))
    if existing:
        raise AppException("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409)

    normalized_username = normalize_username(username) if username else await _make_unique_username(db)
    if username:
        _validate_username(normalized_username)
        username_exists = await db.scalar(select(User.id).where(func.lower(User.username) == normalized_username))
        if username_exists:
            raise AppException("USERNAME_TAKEN", "该账号已被使用", 409)

    must_verify = settings.email_verification_required or not settings.email_allow_unverified_registration
    verified = await _consume_email_code(redis, normalized_email, "register", code) if code else False
    if must_verify and not verified:
        raise AppException("EMAIL_CODE_REQUIRED", "请先完成邮箱验证", 400)

    from app.services.user_service import new_anonymous_name

    if avatar_url and not re.fullmatch(r"/static/assets/avatars/avatar-[1-6]\.png", avatar_url):
        raise AppException("INVALID_AVATAR", "默认头像地址无效", 400)

    user = User(
        email=normalized_email,
        username=normalized_username,
        password_hash=hash_password(password),
        email_verified=verified,
        avatar_url=avatar_url or f"/static/assets/avatars/avatar-{secrets.randbelow(6) + 1}.png",
        anonymous_name=new_anonymous_name(),
        city=city,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppException("ACCOUNT_ALREADY_EXISTS", "邮箱或账号已被使用", 409) from exc
    await db.refresh(user)
    return await _email_auth_payload(db, user)


async def login_with_password(db: AsyncSession, redis: Redis, identifier: str, password: str) -> dict:
    normalized = identifier.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    fail_key = f"limit:password_login_fail:10m:{digest}"
    if int(await redis.get(fail_key) or 0) >= 5:
        raise AppException("LOGIN_LOCKED", "登录失败次数过多，请 10 分钟后再试", 429)

    user = await db.scalar(
        select(User).where(
            or_(func.lower(User.email) == normalized, func.lower(User.username) == normalized)
        )
    )
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        await incr_with_expire(redis, fail_key, 600)
        raise AppException("INVALID_CREDENTIALS", "账号或密码错误", 401)
    if user.status == UserStatus.BANNED:
        raise AppException("USER_BANNED", "账号已被封禁", 403)

    await redis.delete(fail_key)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return await _email_auth_payload(db, user)


async def request_password_reset(db: AsyncSession, redis: Redis, email: str) -> str | None:
    """Request a reset without revealing whether the address is registered."""
    normalized = normalize_email(email)
    user_exists = await db.scalar(select(User.id).where(func.lower(User.email) == normalized))
    return await send_email_code(redis, normalized, "reset", deliver=bool(user_exists))


async def reset_password(db: AsyncSession, redis: Redis, email: str, code: str, new_password: str) -> None:
    normalized = normalize_email(email)
    _validate_password(new_password)
    user = await db.scalar(select(User).where(func.lower(User.email) == normalized))
    # Use the same public error for missing accounts and bad codes.
    if not user:
        raise AppException("INVALID_CODE", "验证码错误或已过期", 400)
    await _consume_email_code(redis, normalized, "reset", code)
    user.password_hash = hash_password(new_password)
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()
