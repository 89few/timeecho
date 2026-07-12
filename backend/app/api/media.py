from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import AppException
from app.models.chat import ChatMessage, ChatRoom
from app.models.security import PrivateMedia
from app.models.social import Friendship, PostMedia, PostVisibility, SocialPost
from app.models.user import User
from app.services.media_service import verify_media_signature

router = APIRouter(prefix="/media", tags=["private-media"])
PRIVATE_DIR = Path("private_uploads")


async def _can_access(db: AsyncSession, user_id: int, media: PrivateMedia) -> bool:
    if media.owner_id == user_id:
        return True
    url = f"/api/media/{media.public_id}"
    room = await db.scalar(
        select(ChatRoom)
        .join(ChatMessage, ChatMessage.room_id == ChatRoom.id)
        .where(
            ChatMessage.media_url == url,
            or_(ChatRoom.user_a_id == user_id, ChatRoom.user_b_id == user_id),
        )
    )
    if room:
        return True
    post = await db.scalar(
        select(SocialPost)
        .join(PostMedia, PostMedia.post_id == SocialPost.id)
        .where(PostMedia.url == url, SocialPost.deleted_at.is_(None))
    )
    if not post:
        return False
    if post.visibility == PostVisibility.PUBLIC or post.author_id == user_id:
        return True
    if post.visibility == PostVisibility.FRIENDS:
        low, high = sorted((post.author_id, user_id))
        return bool(await db.scalar(select(Friendship.id).where(Friendship.user_low_id == low, Friendship.user_high_id == high)))
    return False


@router.get("/{public_id}")
async def private_media(
    public_id: str,
    uid: int | None = None,
    exp: int | None = None,
    sig: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    media = await db.scalar(select(PrivateMedia).where(PrivateMedia.public_id == public_id))
    if uid is None or exp is None or sig is None or not verify_media_signature(public_id, uid, exp, sig) or not media or not await _can_access(db, uid, media):
        raise AppException("MEDIA_NOT_FOUND", "媒体不存在", 404)
    path = PRIVATE_DIR / media.storage_name
    if not path.is_file():
        raise AppException("MEDIA_NOT_FOUND", "媒体不存在", 404)
    return FileResponse(path, media_type=media.content_type, headers={"Cache-Control": "private, max-age=300"})
