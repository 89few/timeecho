from __future__ import annotations

import random
import re

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ANONYMOUS_NAMES
from app.core.crypto import decrypt_text, encrypt_text, mask_phone, phone_hash
from app.core.exceptions import AppException
from app.models.social import (
    FriendRemark,
    FriendRequest,
    FriendRequestStatus,
    Friendship,
    SocialPost,
)
from app.models.user import User, UserStatus
from app.services.block_service import ensure_not_blocked


def new_anonymous_name() -> str:
    return f"{random.choice(ANONYMOUS_NAMES)}{random.randint(100, 999)}"


async def get_or_create_user_by_phone(db: AsyncSession, phone: str, city: str | None = None) -> User:
    hashed = phone_hash(phone)
    user = (await db.execute(select(User).where(User.phone_hash == hashed))).scalar_one_or_none()
    if user:
        if city and not user.city:
            user.city = city
        return user
    user = User(
        phone_hash=hashed,
        phone_ciphertext=encrypt_text(phone),
        anonymous_name=new_anonymous_name(),
        avatar_url=f"/static/assets/avatars/avatar-{random.randint(1, 6)}.png",
        city=city,
    )
    db.add(user)
    await db.flush()
    return user


def user_public_payload(user: User) -> dict:
    phone = decrypt_text(user.phone_ciphertext) if user.phone_ciphertext else None
    return {
        "uid": user.uid,
        "anonymous_name": user.anonymous_name,
        "phone_masked": mask_phone(phone) if phone else None,
        "email": user.email,
        "username": user.username,
        "email_verified": user.email_verified,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "emotion": user.emotion,
        "status": user.status.value,
        "muted_until": user.muted_until,
        "created_at": user.created_at,
    }


def _valid_profile_avatar(url: str) -> bool:
    return bool(
        re.fullmatch(r"/static/assets/avatars/avatar-[1-6]\.png", url)
        or re.fullmatch(r"/static/uploads/[A-Za-z0-9][A-Za-z0-9._-]*", url)
    )


async def update_user_profile(db: AsyncSession, user: User, values: dict, fields_set: set[str]) -> User:
    if "username" in fields_set:
        if not values.get("username"):
            raise AppException("INVALID_USERNAME", "账号不能为空", 400)
        username = values["username"].strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]{2,20}", username):
            raise AppException("INVALID_USERNAME", "账号须为 2 至 20 位中文、字母、数字或下划线", 400)
        owner_id = await db.scalar(select(User.id).where(func.lower(User.username) == username))
        if owner_id is not None and owner_id != user.id:
            raise AppException("USERNAME_TAKEN", "该账号已被使用", 409)
        user.username = username

    if "avatar_url" in fields_set:
        avatar_url = values.get("avatar_url")
        if not avatar_url or not _valid_profile_avatar(avatar_url):
            raise AppException("INVALID_AVATAR", "头像地址无效", 400)
        user.avatar_url = avatar_url
    if "city" in fields_set:
        user.city = values.get("city") or None
    if "bio" in fields_set:
        user.bio = (values.get("bio") or "").strip() or None
    if "emotion" in fields_set:
        user.emotion = values.get("emotion") or None

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppException("USERNAME_TAKEN", "该账号已被使用", 409) from exc
    await db.refresh(user)
    return user


async def get_public_user_profile(
    db: AsyncSession, current_user: User, target_user_id: int
) -> dict:
    target = await db.get(User, target_user_id)
    if not target or target.status == UserStatus.BANNED:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if current_user.id != target.id:
        await ensure_not_blocked(db, current_user.id, target.id)

    low, high = sorted((current_user.id, target.id))
    friendship = await db.scalar(
        select(Friendship).where(
            Friendship.user_low_id == low, Friendship.user_high_id == high
        )
    ) if current_user.id != target.id else None
    pending = await db.scalar(
        select(FriendRequest).where(
            FriendRequest.status == FriendRequestStatus.PENDING,
            or_(
                and_(
                    FriendRequest.requester_id == current_user.id,
                    FriendRequest.addressee_id == target.id,
                ),
                and_(
                    FriendRequest.requester_id == target.id,
                    FriendRequest.addressee_id == current_user.id,
                ),
            ),
        )
    ) if current_user.id != target.id and friendship is None else None

    if current_user.id == target.id:
        relationship = "SELF"
    elif friendship:
        relationship = "FRIEND"
    elif pending and pending.requester_id == current_user.id:
        relationship = "OUTGOING_PENDING"
    elif pending:
        relationship = "INCOMING_PENDING"
    else:
        relationship = "NONE"
    remark = (
        await db.scalar(
            select(FriendRemark.remark).where(
                FriendRemark.owner_id == current_user.id,
                FriendRemark.friend_id == target.id,
            )
        )
        if friendship
        else None
    )

    friend_count = int(
        await db.scalar(
            select(func.count(Friendship.id)).where(
                or_(
                    Friendship.user_low_id == target.id,
                    Friendship.user_high_id == target.id,
                )
            )
        )
        or 0
    )
    post_count = int(
        await db.scalar(
            select(func.count(SocialPost.id)).where(
                SocialPost.author_id == target.id,
                SocialPost.deleted_at.is_(None),
            )
        )
        or 0
    )
    return {
        "id": target.id,
        "uid": target.uid,
        "username": target.username,
        "display_name": remark or target.username or target.anonymous_name,
        "remark": remark,
        "anonymous_name": target.anonymous_name,
        "avatar_url": target.avatar_url,
        "bio": target.bio,
        "emotion": target.emotion,
        "friend_count": friend_count,
        "post_count": post_count,
        "is_me": current_user.id == target.id,
        "is_friend": friendship is not None,
        "relationship": relationship,
        "pending_request_id": pending.id if pending else None,
        "can_message": friendship is not None,
    }
