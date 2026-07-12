from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis
from app.core.exceptions import AppException, ok
from app.models.user import User
from app.models.letter import Letter, LetterStatus
from app.models.chat import ChatRoom, ChatRoomKind, ChatRoomStatus
from app.models.social import Friendship, SocialPost
from app.services.letter_service import emotion_summary
from app.schemas.user import UpdateUserMe
from app.services.user_service import get_public_user_profile, update_user_profile, user_public_payload
from app.services.block_service import create_global_block
from app.services.matching_service import block_anonymous_room
from redis.asyncio import Redis

router = APIRouter(prefix="/users", tags=["users"])

UPLOAD_DIR = Path("app/static/uploads")
AVATAR_MEDIA: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _valid_avatar_signature(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False



@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = user_public_payload(user)
    data["friend_count"] = int(
        await db.scalar(
            select(func.count(Friendship.id)).where(
                or_(Friendship.user_low_id == user.id, Friendship.user_high_id == user.id)
            )
        )
        or 0
    )
    data["post_count"] = int(
        await db.scalar(
            select(func.count(SocialPost.id)).where(
                SocialPost.author_id == user.id,
                SocialPost.deleted_at.is_(None),
            )
        )
        or 0
    )
    return ok(data)


@router.put("/me")
async def update_me(
    payload: UpdateUserMe,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await update_user_profile(db, user, payload.model_dump(), payload.model_fields_set)
    return ok(user_public_payload(updated), "个人资料已更新")


@router.post("/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content_type = (file.content_type or "").lower()
    if content_type in {"", "application/octet-stream"}:
        content_type = (mimetypes.guess_type(file.filename or "")[0] or "").lower()
    suffix = AVATAR_MEDIA.get(content_type)
    if suffix is None:
        raise AppException("UNSUPPORTED_AVATAR", "头像仅支持 JPG、PNG 或 WebP", 415)
    content = await file.read(8 * 1024 * 1024 + 1)
    await file.close()
    if not content:
        raise AppException("EMPTY_AVATAR", "头像文件不能为空", 422)
    if len(content) > 8 * 1024 * 1024:
        raise AppException("AVATAR_TOO_LARGE", "头像最大 8MB", 413)
    if not _valid_avatar_signature(content_type, content):
        raise AppException("INVALID_AVATAR", "头像文件内容与格式不匹配", 422)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    previous_url = user.avatar_url
    name = f"avatar-{user.id}-{uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / name
    destination.write_bytes(content)
    url = f"/static/uploads/{name}"
    try:
        updated = await update_user_profile(
            db, user, {"avatar_url": url}, {"avatar_url"}
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if previous_url and previous_url.startswith(f"/static/uploads/avatar-{user.id}-"):
        old_path = UPLOAD_DIR / previous_url.rsplit("/", 1)[-1]
        if old_path != destination:
            old_path.unlink(missing_ok=True)
    return ok(user_public_payload(updated), "头像已更新")


@router.get("/me/emotion-summary")
async def my_emotion_summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await emotion_summary(db, user, 7))


@router.get("/me/events")
async def my_events(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    letters = (
        await db.execute(
            select(Letter)
            .where(Letter.author_id == user.id, Letter.status == LetterStatus.SALVAGED)
            .order_by(desc(Letter.salvaged_at))
            .limit(100)
        )
    ).scalars().all()
    events = []
    for letter in letters:
        room = await db.scalar(select(ChatRoom).where(ChatRoom.letter_id == letter.id))
        events.append(
            {
                "id": f"salvaged-{letter.id}",
                "type": "LETTER_SALVAGED",
                "title": "你的纸飞机被打捞了",
                "message": f"{letter.emotion}纸飞机已被一位陌生人收到",
                "created_at": letter.salvaged_at,
                "letter_id": letter.id,
                "room_id": room.id if room else None,
            }
        )
    return ok(events)


@router.post("/{user_id}/block")
async def block_user(
    user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    target = await db.get(User, user_id)
    if not target:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    room = await db.scalar(
        select(ChatRoom)
        .where(
            ChatRoom.status == ChatRoomStatus.ACTIVE,
            ChatRoom.room_kind != ChatRoomKind.FRIEND,
            or_(
                (ChatRoom.user_a_id == user.id) & (ChatRoom.user_b_id == user_id),
                (ChatRoom.user_a_id == user_id) & (ChatRoom.user_b_id == user.id),
            ),
        )
        .order_by(ChatRoom.id.desc())
    )
    if room:
        await block_anonymous_room(db, redis, user, room.id)
    else:
        await create_global_block(db, user.id, user_id)
    return ok({"blocked": True}, "已拉黑")


@router.get("/{user_id}")
async def public_profile(
    user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await get_public_user_profile(db, user, user_id))
