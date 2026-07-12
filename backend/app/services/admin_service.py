from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import SEALED_ZSET_KEY
from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.chat import ChatRoom
from app.models.complaint import Complaint, ComplaintStatus
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.punishment import Punishment, PunishmentType
from app.models.sensitive_word import SensitiveWord
from app.models.system_config import SystemConfig
from app.models.user import User, UserStatus
from app.models.security import UserSession
from app.models.social import Friendship, SocialPost
from app.models.security import AdminLoginLog, AdminRole, AdminSession, AdminUser
from app.models.chat import MatchStateStatus, UserMatchState
from app.websocket.manager import manager, matching_manager
import shutil
from app.services.auth_service import hash_password, verify_password
from app.services.salvage_service import add_to_available_pools


def _session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def admin_login(
    db: AsyncSession,
    username: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[AdminUser, str, datetime]:
    now = utcnow()
    normalized = username.strip().lower()
    admin = await db.scalar(select(AdminUser).where(AdminUser.username == normalized))
    reason = None
    if not admin or not admin.enabled:
        reason = "NOT_FOUND_OR_DISABLED"
    elif admin.locked_until and (
        admin.locked_until.replace(tzinfo=timezone.utc)
        if admin.locked_until.tzinfo is None else admin.locked_until
    ) > now:
        reason = "LOCKED"
    elif not verify_password(password, admin.password_hash):
        admin.failed_attempts += 1
        if admin.failed_attempts >= 5:
            admin.locked_until = now + timedelta(minutes=15)
        reason = "INVALID_PASSWORD"
    if reason:
        db.add(AdminLoginLog(admin_id=admin.id if admin else None, username=normalized, success=False, reason=reason, ip_address=ip_address, user_agent=user_agent, created_at=now))
        await db.commit()
        raise AppException("INVALID_ADMIN_LOGIN", "管理员账号或密码错误", 401)
    admin.failed_attempts = 0
    admin.locked_until = None
    raw_token = secrets.token_urlsafe(48)
    expires_at = now + timedelta(hours=8)
    db.add(AdminSession(admin_id=admin.id, token_hash=_session_hash(raw_token), expires_at=expires_at, ip_address=ip_address, user_agent=user_agent, created_at=now))
    db.add(AdminLoginLog(admin_id=admin.id, username=normalized, success=True, ip_address=ip_address, user_agent=user_agent, created_at=now))
    await db.commit()
    return admin, raw_token, expires_at


async def create_admin_account(db: AsyncSession, username: str, password: str, role: AdminRole) -> AdminUser:
    normalized = username.strip().lower()
    if await db.scalar(select(AdminUser.id).where(AdminUser.username == normalized)):
        raise AppException("ADMIN_EXISTS", "管理员账号已存在", 409)
    now = utcnow()
    admin = AdminUser(username=normalized, password_hash=hash_password(password), role=role, enabled=True, failed_attempts=0, password_changed_at=now, created_at=now, updated_at=now)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def dashboard(db: AsyncSession, redis: Redis) -> dict:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=6)
    async def count(model, *where):
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()
    return {
        "today_registered_users": await count(User, User.created_at >= today),
        "today_letters": await count(Letter, Letter.created_at >= today),
        "today_released_letters": await count(Letter, Letter.status == LetterStatus.AVAILABLE, Letter.updated_at >= today),
        "today_salvaged_letters": await count(Letter, Letter.salvaged_at >= today),
        "today_chat_rooms": await count(ChatRoom, ChatRoom.created_at >= today),
        "today_complaints": await count(Complaint, Complaint.created_at >= today),
        "today_intercepts": await count(Letter, Letter.created_at >= today, Letter.risk_level != RiskLevel.NONE),
        "risk_review_letters": await count(Letter, Letter.status == LetterStatus.RISK_REVIEW),
        "total_users": await count(User),
        "active_users": await count(User, User.last_login_at >= today),
        "dau": await count(User, User.last_login_at >= today),
        "wau": await count(User, User.last_login_at >= week),
        "online_users": len({uid for users in manager.active.values() for uid in users} | {uid for users in matching_manager.active.values() for uid in users}),
        "matching_queue": await count(UserMatchState, UserMatchState.status == MatchStateStatus.WAITING),
        "total_posts": await count(SocialPost, SocialPost.deleted_at.is_(None)),
        "total_friendships": await count(Friendship),
        "health": {
            "postgres": "ok",
            "redis": "ok" if await redis.ping() else "error",
            "websocket_connections": sum(len(users) for users in manager.active.values()) + sum(len(users) for users in matching_manager.active.values()),
            "smtp": "configured" if settings.smtp_host and settings.smtp_from_email else "not_configured",
            "disk_free_gb": round(shutil.disk_usage("/").free / (1024 ** 3), 2),
        },
    }


async def mute_user(db: AsyncSession, user_id: int, minutes: int, reason: str | None) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status in {UserStatus.BANNED, UserStatus.DEACTIVATED}:
        raise AppException("INVALID_STATUS_TRANSITION", "封禁或注销账号不能禁言", 409)
    user.status = UserStatus.MUTED
    user.muted_until = utcnow() + timedelta(minutes=minutes)
    db.add(Punishment(user_id=user.id, type=PunishmentType.MUTE, reason=reason, end_at=user.muted_until, created_by="admin"))
    await db.commit()
    await db.refresh(user)
    return user


async def ban_user(db: AsyncSession, user_id: int, reason: str | None) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status == UserStatus.DEACTIVATED:
        raise AppException("INVALID_STATUS_TRANSITION", "已注销账号不能封禁", 409)
    user.status = UserStatus.BANNED
    user.banned_at = utcnow()
    db.add(Punishment(user_id=user.id, type=PunishmentType.BAN, reason=reason, created_by="admin"))
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()
    await db.refresh(user)
    return user


async def unmute_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status != UserStatus.MUTED:
        raise AppException("INVALID_STATUS_TRANSITION", "该账号不处于禁言状态", 409)
    user.status = UserStatus.ACTIVE
    user.muted_until = None
    await db.commit()
    await db.refresh(user)
    return user


async def approve_letter(db: AsyncSession, redis: Redis, letter_id: int, release_now: bool = False) -> Letter:
    letter = await db.get(Letter, letter_id)
    if not letter or letter.status != LetterStatus.RISK_REVIEW:
        raise AppException("LETTER_NOT_FOUND", "待审核纸飞机不存在", 404)
    now = utcnow()
    if release_now or (letter.release_at and letter.release_at <= now):
        letter.status = LetterStatus.AVAILABLE
        await db.commit()
        await db.refresh(letter)
        await add_to_available_pools(redis, letter)
    else:
        letter.status = LetterStatus.SEALED
        await db.commit()
        await db.refresh(letter)
        await redis.zadd(SEALED_ZSET_KEY, {str(letter.id): letter.release_at.timestamp()})
    return letter


async def reject_letter(db: AsyncSession, letter_id: int) -> Letter:
    letter = await db.get(Letter, letter_id)
    if not letter or letter.status != LetterStatus.RISK_REVIEW:
        raise AppException("LETTER_NOT_FOUND", "待审核纸飞机不存在", 404)
    letter.status = LetterStatus.DESTROYED
    letter.content_ciphertext = ""
    await db.commit()
    await db.refresh(letter)
    return letter
