from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from redis.asyncio import Redis
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_text
from app.core.dependencies import get_current_admin, get_db, get_redis
from app.core.exceptions import AppException, ok
from app.models.chat import ChatMessage
from app.models.complaint import Complaint, ComplaintStatus
from app.models.letter import Letter, LetterStatus
from app.models.sensitive_word import SensitiveWord
from app.models.system_config import SystemConfig
from app.models.user import User, UserStatus
from app.models.social import FriendRequest, Friendship, PostComment, PostLike, PostMedia, SocialPost
from app.schemas.admin import (
    AdminLoginRequest,
    AdminCreateRequest,
    AdminPasswordChange,
    AdminEnabledUpdate,
    BanRequest,
    ComplaintHandleRequest,
    ComplaintResolutionRequest,
    ConfigUpdate,
    MuteRequest,
    ReviewActionRequest,
    SensitiveWordCreate,
    AdminUserCreate,
    AdminUserUpdate,
)
from app.services.admin_service import admin_login, create_admin_account, approve_letter, ban_user, dashboard, mute_user, reject_letter, unmute_user
from app.models.security import AdminRole, AdminSession, AdminUser, UserSession
from app.services.auth_service import verify_password
from app.core.dependencies import require_admin_roles
from app.services.config_service import clear_config_cache, validate_config
from app.services.risk_service import clear_sensitive_word_cache
from app.services.salvage_service import rebuild_available_letter_pools
from app.services.auth_service import hash_password, normalize_email, normalize_username
from app.services.user_service import new_anonymous_name
from app.core.security import utcnow
from app.core.config import settings
from app.workers.cleanup_worker import cleanup_once
from app.workers.release_letter_worker import process_due_letters_once
from app.services.matching_service import disconnect_waiter
from app.websocket.manager import manager, matching_manager
from app.models.punishment import Punishment, PunishmentType
from app.models.notification import NotificationType
from app.services.notification_service import create_notification
from app.core.crypto import encrypt_text
from datetime import timedelta

router = APIRouter(prefix="/admin", tags=["admin"])


def _decrypt_content(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    return decrypt_text(ciphertext)


def _admin_letter_review_payload(letter: Letter) -> dict:
    destroyed = letter.status == LetterStatus.DESTROYED or not bool(letter.content_ciphertext)
    return {
        "id": letter.id,
        "author_id": letter.author_id,
        "content": None if destroyed else _decrypt_content(letter.content_ciphertext),
        "content_destroyed": destroyed,
        "emotion": letter.emotion,
        "city": letter.city,
        "status": letter.status.value,
        "risk_level": letter.risk_level.value,
        "created_at": letter.created_at,
    }


async def _complaint_target_content(db: AsyncSession, complaint: Complaint) -> tuple[str | None, str | None, bool]:
    if complaint.letter_id:
        letter = await db.get(Letter, complaint.letter_id)
        if not letter:
            return "LETTER", None, True
        destroyed = letter.status == LetterStatus.DESTROYED or not bool(letter.content_ciphertext)
        return "LETTER", None if destroyed else _decrypt_content(letter.content_ciphertext), destroyed
    if complaint.message_id:
        msg = await db.get(ChatMessage, complaint.message_id)
        if not msg:
            return "MESSAGE", None, True
        destroyed = msg.deleted_at is not None or not bool(msg.content_ciphertext)
        return "MESSAGE", None if destroyed else _decrypt_content(msg.content_ciphertext), destroyed
    if complaint.room_id:
        return "ROOM", f"room_id={complaint.room_id}", False
    return None, None, True


@router.post("/login")
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    ip = request.client.host if request.client else None
    key = f"limit:admin_login:{ip or 'unknown'}:{payload.username.strip().lower()}"
    attempts = int(await redis.get(key) or 0)
    if attempts >= 10:
        raise AppException("ADMIN_LOGIN_RATE_LIMITED", "登录尝试过多，请稍后再试", 429)
    try:
        admin, raw_token, expires_at = await admin_login(
            db, payload.username, payload.password, ip, request.headers.get("user-agent")
        )
    except AppException:
        await redis.incr(key)
        await redis.expire(key, 600)
        raise
    await redis.delete(key)
    response.set_cookie(
        "te_admin_session", raw_token, httponly=True,
        secure=settings.app_env.lower() == "prod", samesite="strict",
        max_age=8 * 3600, path="/api/admin",
    )
    data = {"username": admin.username, "role": admin.role.value, "expires_at": expires_at}
    if settings.app_env.lower() == "test":
        data["access_token"] = raw_token
    return ok(data)


@router.get("/me")
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return ok({"id": admin.id, "username": admin.username, "role": admin.role.value})


@router.post("/logout")
async def admin_logout(
    response: Response,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    session = request.state.admin_session
    session.revoked_at = utcnow()
    await db.commit()
    response.delete_cookie("te_admin_session", path="/api/admin")
    return ok(message="已退出")


@router.post("/admins")
async def create_admin(
    payload: AdminCreateRequest,
    _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    try:
        role = AdminRole(payload.role)
    except ValueError as exc:
        raise AppException("INVALID_ADMIN_ROLE", "管理员角色无效", 422) from exc
    admin = await create_admin_account(db, payload.username, payload.password, role)
    return ok({"id": admin.id, "username": admin.username, "role": admin.role.value})


@router.get("/admins")
async def list_admins(
    _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(AdminUser).order_by(AdminUser.id))).scalars().all()
    return ok([{"id": item.id, "username": item.username, "role": item.role.value, "enabled": item.enabled, "created_at": item.created_at} for item in rows])


@router.post("/password")
async def change_admin_password(
    payload: AdminPasswordChange,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, admin.password_hash):
        raise AppException("INVALID_ADMIN_PASSWORD", "当前密码错误", 400)
    admin.password_hash = hash_password(payload.new_password)
    admin.password_changed_at = utcnow()
    await db.execute(
        update(AdminSession).where(
            AdminSession.admin_id == admin.id,
            AdminSession.id != request.state.admin_session.id,
            AdminSession.revoked_at.is_(None),
        ).values(revoked_at=utcnow())
    )
    await db.commit()
    return ok(message="密码已修改")


@router.put("/admins/{admin_id}/enabled")
async def set_admin_enabled(
    admin_id: int,
    payload: AdminEnabledUpdate,
    current: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if current.id == admin_id and not payload.enabled:
        raise AppException("CANNOT_DISABLE_SELF", "不能禁用当前管理员", 400)
    target = await db.get(AdminUser, admin_id)
    if not target:
        raise AppException("ADMIN_NOT_FOUND", "管理员不存在", 404)
    target.enabled = payload.enabled
    if not payload.enabled:
        await db.execute(update(AdminSession).where(AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await db.commit()
    return ok({"id": target.id, "enabled": target.enabled})


@router.get("/dashboard")
async def get_dashboard(_: AdminUser = Depends(get_current_admin), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await dashboard(db, redis))


def _admin_user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "uid": user.uid,
        "email": user.email,
        "username": user.username,
        "anonymous_name": user.anonymous_name,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "status": user.status.value,
        "city": user.city,
        "emotion": user.emotion,
        "email_verified": user.email_verified,
        "created_at": user.created_at,
    }


@router.get("/users")
async def users(
    q: str | None = Query(default=None, max_length=100),
    status: UserStatus | None = None,
    _: str = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if q:
        query = q.strip()
        term = f"%{query}%"
        filters = [
            User.uid == query,
            User.email.ilike(term),
            User.username.ilike(term),
            User.anonymous_name.ilike(term),
        ]
        if query.isdigit():
            filters.append(User.id == int(query))
        stmt = stmt.where(or_(*filters))
    if status:
        stmt = stmt.where(User.status == status)
    rows = (await db.execute(stmt.order_by(User.id.desc()).limit(200))).scalars().all()
    return ok([_admin_user_payload(user) for user in rows])


@router.post("/users")
async def create_user(payload: AdminUserCreate, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.OPERATOR)), db: AsyncSession = Depends(get_db)):
    email = normalize_email(str(payload.email))
    username = normalize_username(payload.username)
    if await db.scalar(select(User.id).where(or_(func.lower(User.email) == email, func.lower(User.username) == username))):
        raise AppException("USER_ALREADY_EXISTS", "邮箱或用户名已存在", 409)
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(payload.password),
        must_change_password=True,
        email_verified=True,
        anonymous_name=new_anonymous_name(),
        avatar_url="/static/assets/avatars/avatar-1.png",
        city=payload.city,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(_admin_user_payload(user), "用户已创建")


@router.get("/users/{user_id}")
async def user_detail(user_id: int, _: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    return ok(_admin_user_payload(user))


@router.put("/users/{user_id}")
async def update_user(user_id: int, payload: AdminUserUpdate, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    values = payload.model_dump(exclude_unset=True)
    if "email" in values:
        user.email = normalize_email(str(values["email"]))
    if "username" in values:
        user.username = normalize_username(values["username"])
    for field in ("city", "emotion", "bio", "avatar_url"):
        if field in values:
            setattr(user, field, values[field] or None)
    await db.commit()
    await db.refresh(user)
    return ok(_admin_user_payload(user), "用户资料已更新")


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    user.email = None
    user.password_hash = None
    user.phone_hash = None
    user.phone_ciphertext = None
    user.username = f"deleted_{user.id}"
    user.bio = None
    user.status = UserStatus.DEACTIVATED
    user.banned_at = utcnow()
    await db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await db.commit()
    await manager.disconnect_user(user.id)
    await matching_manager.disconnect_user(user.id)
    await disconnect_waiter(db, redis, user)
    return ok({"id": user.id, "status": user.status.value}, "用户已停用并清除登录凭据")


@router.post("/users/{user_id}/activate")
async def activate_user(user_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status != UserStatus.DORMANT:
        raise AppException("INVALID_STATUS_TRANSITION", "只有休眠账号可以直接恢复", 409)
    user.status = UserStatus.ACTIVE
    user.banned_at = None
    user.muted_until = None
    await db.commit()
    return ok(_admin_user_payload(user), "用户状态已恢复")


@router.post("/users/{user_id}/mute")
async def mute(user_id: int, payload: MuteRequest, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    user = await mute_user(db, user_id, payload.minutes, payload.reason)
    return ok({"id": user.id, "status": user.status.value, "muted_until": user.muted_until})


@router.post("/users/{user_id}/ban")
async def ban(user_id: int, payload: BanRequest, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    user = await ban_user(db, user_id, payload.reason)
    await manager.disconnect_user(user.id)
    await matching_manager.disconnect_user(user.id)
    await disconnect_waiter(db, redis, user)
    return ok({"id": user.id, "status": user.status.value, "banned_at": user.banned_at})


@router.post("/users/{user_id}/unmute")
async def unmute(user_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    user = await unmute_user(db, user_id)
    return ok({"id": user.id, "status": user.status.value})


@router.post("/users/{user_id}/unban")
async def unban(user_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if user.status != UserStatus.BANNED:
        raise AppException("INVALID_STATUS_TRANSITION", "该账号不处于封禁状态", 409)
    if not user.email and not user.phone_hash:
        raise AppException("ACCOUNT_DEACTIVATED", "已注销账号不能恢复", 409)
    user.status = UserStatus.ACTIVE
    user.banned_at = None
    await db.commit()
    return ok(_admin_user_payload(user), "账号已解封")


@router.get("/reviews/letters")
async def review_letters(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Letter).where(Letter.status == LetterStatus.RISK_REVIEW).order_by(Letter.id.desc()))).scalars().all()
    return ok([_admin_letter_review_payload(x) for x in rows])


@router.post("/reviews/letters/{letter_id}/approve")
async def approve(letter_id: int, payload: ReviewActionRequest, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    letter = await approve_letter(db, redis, letter_id, payload.release_now)
    return ok({"id": letter.id, "status": letter.status.value})


@router.post("/reviews/letters/{letter_id}/reject")
async def reject(letter_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    letter = await reject_letter(db, letter_id)
    return ok({"id": letter.id, "status": letter.status.value})


@router.get("/complaints")
async def complaints(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Complaint).order_by(Complaint.id.desc()).limit(100))).scalars().all()
    user_ids = {
        user_id
        for complaint in rows
        for user_id in (complaint.reporter_id, complaint.target_user_id)
        if user_id is not None
    }
    users = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
    } if user_ids else {}
    data = []
    for c in rows:
        target_type, target_content, content_destroyed = await _complaint_target_content(db, c)
        reporter = users.get(c.reporter_id)
        target = users.get(c.target_user_id) if c.target_user_id else None
        data.append({
            "id": c.id,
            "target_type": target_type,
            "target_content": target_content,
            "content_destroyed": content_destroyed,
            "status": c.status.value,
            "reason": c.reason,
            "description": c.description,
            "reporter": _admin_user_payload(reporter) if reporter else None,
            "target_user": _admin_user_payload(target) if target else None,
            "created_at": c.created_at,
            "handled_at": c.handled_at,
        })
    return ok(data)


@router.post("/complaints/{complaint_id}/handle")
async def handle_complaint(complaint_id: int, payload: ComplaintHandleRequest, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    complaint = await db.get(Complaint, complaint_id)
    if not complaint:
        raise AppException("COMPLAINT_NOT_FOUND", "举报不存在", 404)
    try:
        complaint.status = ComplaintStatus(payload.status)
    except ValueError as exc:
        raise AppException("INVALID_COMPLAINT_STATUS", "举报处理状态不正确", 400) from exc
    complaint.handled_by = "admin"
    complaint.handled_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(complaint)
    return ok({"id": complaint.id, "status": complaint.status.value, "handled_at": complaint.handled_at})


@router.post("/complaints/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: int,
    payload: ComplaintResolutionRequest,
    admin: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)),
    db: AsyncSession = Depends(get_db),
):
    complaint = await db.get(Complaint, complaint_id, with_for_update=True)
    if not complaint or complaint.status != ComplaintStatus.PENDING:
        raise AppException("COMPLAINT_NOT_PENDING", "举报不存在或已经处理", 409)
    _, evidence, _ = await _complaint_target_content(db, complaint)
    if evidence and not complaint.evidence_ciphertext:
        complaint.evidence_ciphertext = encrypt_text(evidence)
        complaint.evidence_key_version = settings.encryption_key_version
    complaint.review_note = payload.review_note
    complaint.handled_by = f"admin:{admin.id}"
    complaint.handled_at = utcnow()
    complaint.status = ComplaintStatus.REJECTED if payload.decision == "REJECTED" else ComplaintStatus.HANDLED
    target = await db.get(User, complaint.target_user_id) if complaint.target_user_id else None
    if payload.decision == "VIOLATION" and payload.action != "NONE":
        if payload.action == "REMOVE_CONTENT":
            if complaint.letter_id:
                letter = await db.get(Letter, complaint.letter_id)
                if letter:
                    letter.content_ciphertext = ""
                    letter.status = LetterStatus.DESTROYED
            if complaint.message_id:
                message = await db.get(ChatMessage, complaint.message_id)
                if message:
                    message.content_ciphertext = ""
                    message.deleted_at = utcnow()
        elif target:
            if target.status == UserStatus.DEACTIVATED:
                raise AppException("INVALID_STATUS_TRANSITION", "已注销账号不能处罚", 409)
            if payload.action == "BAN":
                target.status = UserStatus.BANNED
                target.banned_at = utcnow()
                punishment_type = PunishmentType.BAN
                end_at = None
            else:
                if target.status == UserStatus.BANNED:
                    raise AppException("INVALID_STATUS_TRANSITION", "封禁账号不能改为禁言", 409)
                target.status = UserStatus.MUTED
                end_at = utcnow() + timedelta(minutes=payload.duration_minutes or 60)
                target.muted_until = end_at
                punishment_type = PunishmentType.MUTE
            db.add(Punishment(user_id=target.id, type=punishment_type, reason=payload.review_note, end_at=end_at, created_by=f"admin:{admin.id}", review_note=payload.review_note))
            await db.execute(update(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await create_notification(db, user_id=complaint.reporter_id, notification_type=NotificationType.SYSTEM, title="举报处理结果", message="举报已处理", data={"complaint_id": complaint.id, "decision": payload.decision}, commit=False)
    await db.commit()
    return ok({"id": complaint.id, "status": complaint.status.value, "action": payload.action}, "举报处理完成")


@router.get("/sensitive-words")
async def sensitive_words(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SensitiveWord).order_by(SensitiveWord.id.desc()))).scalars().all()
    return ok([{"id": w.id, "word": w.word, "category": w.category, "level": w.level, "enabled": w.enabled} for w in rows])


@router.post("/sensitive-words")
async def create_sensitive_word(payload: SensitiveWordCreate, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    word = SensitiveWord(**payload.model_dump())
    db.add(word)
    await db.commit()
    await db.refresh(word)
    await clear_sensitive_word_cache(redis)
    return ok({"id": word.id, "word": word.word})


@router.delete("/sensitive-words/{word_id}")
async def delete_sensitive_word(word_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    word = await db.get(SensitiveWord, word_id)
    if not word:
        raise AppException("WORD_NOT_FOUND", "敏感词不存在", 404)
    await db.delete(word)
    await db.commit()
    await clear_sensitive_word_cache(redis)
    return ok({"id": word_id})


@router.get("/configs")
async def configs(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))).scalars().all()
    return ok([{"config_key": c.config_key, "config_value": c.config_value, "description": c.description} for c in rows])


@router.put("/configs/{config_key}")
async def update_config(config_key: str, payload: ConfigUpdate, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    try:
        validated_value = validate_config(config_key, payload.config_value)
    except ValueError as exc:
        raise AppException("INVALID_CONFIG", str(exc), 422) from exc
    config = (await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))).scalar_one_or_none()
    if not config:
        config = SystemConfig(config_key=config_key, config_value=validated_value, description=payload.description)
        db.add(config)
    else:
        config.config_value = validated_value
        if payload.description is not None:
            config.description = payload.description
    await db.commit()
    await clear_config_cache(redis, config_key)
    return ok({"config_key": config_key, "config_value": validated_value})


@router.get("/social/posts")
async def admin_posts(
    q: str | None = Query(default=None, max_length=100),
    include_deleted: bool = False,
    _: str = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SocialPost)
    if not include_deleted:
        stmt = stmt.where(SocialPost.deleted_at.is_(None))
    if q:
        stmt = stmt.where(SocialPost.text.ilike(f"%{q.strip()}%"))
    posts = (await db.execute(stmt.order_by(SocialPost.id.desc()).limit(200))).scalars().all()
    post_ids = [post.id for post in posts]
    author_ids = {post.author_id for post in posts}
    authors = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(author_ids)))
        ).scalars().all()
    } if author_ids else {}
    media_by_post: dict[int, list[PostMedia]] = {}
    if post_ids:
        for item in (
            await db.execute(
                select(PostMedia)
                .where(PostMedia.post_id.in_(post_ids))
                .order_by(PostMedia.post_id, PostMedia.sort_order)
            )
        ).scalars().all():
            media_by_post.setdefault(item.post_id, []).append(item)
    like_counts = dict((await db.execute(
        select(PostLike.post_id, func.count(PostLike.id))
        .where(PostLike.post_id.in_(post_ids))
        .group_by(PostLike.post_id)
    )).all()) if post_ids else {}
    comment_counts = dict((await db.execute(
        select(PostComment.post_id, func.count(PostComment.id))
        .where(PostComment.post_id.in_(post_ids), PostComment.deleted_at.is_(None))
        .group_by(PostComment.post_id)
    )).all()) if post_ids else {}
    result = []
    for post in posts:
        author = authors.get(post.author_id)
        media = media_by_post.get(post.id, [])
        result.append({
            "id": post.id,
            "author_id": post.author_id,
            "author_uid": author.uid if author else None,
            "author_name": author.username if author else None,
            "text": post.text,
            "visibility": post.visibility.value,
            "media": [{"kind": item.kind, "url": item.url} for item in media],
            "like_count": int(like_counts.get(post.id, 0)),
            "comment_count": int(comment_counts.get(post.id, 0)),
            "created_at": post.created_at,
            "deleted_at": post.deleted_at,
        })
    return ok(result)


@router.delete("/social/posts/{post_id}")
async def admin_delete_post(post_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    post = await db.get(SocialPost, post_id)
    if not post:
        raise AppException("POST_NOT_FOUND", "动态不存在", 404)
    post.deleted_at = utcnow()
    await db.commit()
    return ok({"id": post.id}, "动态已删除")


@router.get("/social/comments")
async def admin_comments(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    comments = (
        await db.execute(
            select(PostComment).where(PostComment.deleted_at.is_(None)).order_by(PostComment.id.desc()).limit(300)
        )
    ).scalars().all()
    author_ids = {comment.author_id for comment in comments}
    authors = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(author_ids)))
        ).scalars().all()
    } if author_ids else {}
    result = []
    for comment in comments:
        author = authors.get(comment.author_id)
        result.append({
            "id": comment.id,
            "post_id": comment.post_id,
            "author_id": comment.author_id,
            "author_uid": author.uid if author else None,
            "author_name": author.username if author else None,
            "text": comment.text,
            "created_at": comment.created_at,
        })
    return ok(result)


@router.delete("/social/comments/{comment_id}")
async def admin_delete_comment(comment_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    comment = await db.get(PostComment, comment_id)
    if not comment:
        raise AppException("COMMENT_NOT_FOUND", "评论不存在", 404)
    comment.deleted_at = utcnow()
    await db.commit()
    return ok({"id": comment.id}, "评论已删除")


@router.get("/social/friends")
async def admin_friendships(_: str = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    friendships = (await db.execute(select(Friendship).order_by(Friendship.id.desc()).limit(300))).scalars().all()
    requests = (await db.execute(select(FriendRequest).order_by(FriendRequest.id.desc()).limit(300))).scalars().all()
    user_ids = {
        value
        for item in friendships
        for value in (item.user_low_id, item.user_high_id)
    } | {
        value
        for item in requests
        for value in (item.requester_id, item.addressee_id)
    }
    users = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
    } if user_ids else {}

    def identity(user_id: int) -> dict:
        user = users.get(user_id)
        return {
            "id": user_id,
            "uid": user.uid if user else None,
            "name": (user.username or user.anonymous_name) if user else "已注销用户",
        }

    return ok({
        "friendships": [{"id": item.id, "user_a": identity(item.user_low_id), "user_b": identity(item.user_high_id), "created_at": item.created_at} for item in friendships],
        "requests": [{"id": item.id, "requester": identity(item.requester_id), "addressee": identity(item.addressee_id), "status": item.status.value, "message": item.message, "created_at": item.created_at} for item in requests],
    })


@router.delete("/social/friends/{friendship_id}")
async def admin_delete_friendship(friendship_id: int, _: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.MODERATOR)), db: AsyncSession = Depends(get_db)):
    friendship = await db.get(Friendship, friendship_id)
    if not friendship:
        raise AppException("FRIENDSHIP_NOT_FOUND", "好友关系不存在", 404)
    await db.delete(friendship)
    await db.commit()
    return ok({"id": friendship_id}, "好友关系已删除")


@router.post("/maintenance/rebuild-available-pools")
async def rebuild_pools(_: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.OPERATOR)), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    count = await rebuild_available_letter_pools(db, redis)
    return ok({"rebuilt": count}, "可打捞池已重建")


@router.post("/maintenance/process-due-letters-once")
async def process_due_letters(_: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.OPERATOR)), redis: Redis = Depends(get_redis)):
    released = await process_due_letters_once(redis=redis)
    return ok({"released": released}, "已执行一次到期释放")


@router.post("/maintenance/cleanup-once")
async def run_cleanup(_: AdminUser = Depends(require_admin_roles(AdminRole.SUPER_ADMIN, AdminRole.OPERATOR)), redis: Redis = Depends(get_redis)):
    result = await cleanup_once(redis=redis)
    return ok(result, "已执行一次清理")
