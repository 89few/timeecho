from __future__ import annotations

from pathlib import Path
import mimetypes
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ensure_user_can_post, get_current_user, get_db, get_redis
from app.core.exceptions import AppException, ok
from app.models.social import FriendRequestStatus
from app.models.user import User
from app.models.security import PrivateMedia
from app.core.security import utcnow
from app.services.media_service import signed_media_url
from app.schemas.social import (
    CommentCreate,
    FriendRemarkUpdate,
    FriendRequestCreate,
    PostCreate,
)
from app.services.social_service import (
    create_comment,
    create_post,
    delete_comment,
    delete_post,
    get_post,
    list_comments,
    list_friend_requests,
    list_friends,
    list_posts,
    remove_friend,
    respond_friend_request,
    search_users,
    send_friend_request,
    set_friend_remark,
    toggle_post_like,
)

router = APIRouter(prefix="/social", tags=["social"])
UPLOAD_DIR = Path("private_uploads")
ALLOWED_MEDIA: dict[str, tuple[str, str, int]] = {
    "image/jpeg": ("image", ".jpg", 10 * 1024 * 1024),
    "image/png": ("image", ".png", 10 * 1024 * 1024),
    "image/webp": ("image", ".webp", 10 * 1024 * 1024),
    "video/mp4": ("video", ".mp4", 50 * 1024 * 1024),
    "video/quicktime": ("video", ".mov", 50 * 1024 * 1024),
    "audio/mp4": ("audio", ".m4a", 15 * 1024 * 1024),
    "audio/aac": ("audio", ".aac", 15 * 1024 * 1024),
    "audio/mpeg": ("audio", ".mp3", 15 * 1024 * 1024),
}


def _valid_signature(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type in {"video/mp4", "audio/mp4"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if content_type == "video/quicktime":
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if content_type == "audio/mpeg":
        return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    if content_type == "audio/aac":
        return len(content) >= 2 and content[0] == 0xFF and content[1] & 0xF6 == 0xF0
    return False


@router.post("/media")
async def upload_social_media(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_user_can_post(user)
    content_type = (file.content_type or "").lower()
    if content_type in {"", "application/octet-stream"}:
        content_type = (mimetypes.guess_type(file.filename or "")[0] or content_type).lower()
    media = ALLOWED_MEDIA.get(content_type)
    if media is None:
        raise AppException("UNSUPPORTED_MEDIA", "仅支持 JPG、PNG、WebP、MP4 和常用音频格式", 415)
    kind, suffix, max_bytes = media
    content = await file.read(max_bytes + 1)
    await file.close()
    if not content:
        raise AppException("EMPTY_MEDIA", "上传文件不能为空", 422)
    if len(content) > max_bytes:
        raise AppException("MEDIA_TOO_LARGE", "图片最大 10MB、音频最大 15MB、视频最大 50MB", 413)
    if not _valid_signature(content_type, content):
        raise AppException("INVALID_MEDIA", "文件内容与媒体格式不匹配", 422)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}{suffix}"
    (UPLOAD_DIR / name).write_bytes(content)
    public_id = uuid4().hex
    db.add(PrivateMedia(public_id=public_id, owner_id=user.id, storage_name=name, content_type=content_type, kind=kind, size_bytes=len(content), created_at=utcnow()))
    await db.commit()
    return ok(
        {"kind": kind, "url": signed_media_url(f"/api/media/{public_id}", user.id), "size": len(content)},
        "上传成功",
    )


@router.get("/friends/search")
async def friend_search(
    q: str = Query(min_length=2, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await search_users(db, user, q, page, page_size))


@router.post("/friends/requests")
async def create_friend_request(
    payload: FriendRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await send_friend_request(db, user, payload.target_user_id, payload.message),
        "好友申请已发送",
    )


@router.get("/friends/requests")
async def friend_requests(
    box: Literal["incoming", "outgoing"] = Query(default="incoming"),
    status: FriendRequestStatus | None = Query(default=FriendRequestStatus.PENDING),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_friend_requests(db, user, box, status, page, page_size))


@router.post("/friends/requests/{request_id}/accept")
async def accept_friend_request(
    request_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await respond_friend_request(db, user, request_id, True), "已添加为好友")


@router.post("/friends/requests/{request_id}/reject")
async def reject_friend_request(
    request_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await respond_friend_request(db, user, request_id, False), "已拒绝好友申请")


@router.get("/friends")
async def friends(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_friends(db, user, page, page_size))


@router.delete("/friends/{friend_user_id}")
async def delete_friend(
    friend_user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await remove_friend(db, user, friend_user_id)
    return ok({"friend_user_id": friend_user_id}, "好友已删除")


@router.put("/friends/{friend_user_id}/remark")
async def update_friend_remark(
    friend_user_id: int,
    payload: FriendRemarkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await set_friend_remark(db, user, friend_user_id, payload.remark),
        "备注已更新",
    )


@router.post("/posts")
async def publish_post(
    payload: PostCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    return ok(await create_post(db, redis, user, payload), "动态发布成功")


@router.get("/posts")
async def post_feed(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    author_id: int | None = Query(default=None, gt=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_posts(db, user, page, page_size, author_id))


@router.get("/posts/{post_id}")
async def post_detail(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await get_post(db, user, post_id))


@router.delete("/posts/{post_id}")
async def remove_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_post(db, user, post_id)
    return ok({"post_id": post_id}, "动态已删除")


@router.post("/posts/{post_id}/likes")
async def toggle_like(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await toggle_post_like(db, user, post_id))


@router.post("/posts/{post_id}/comments")
async def publish_comment(
    post_id: int,
    payload: CommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    return ok(await create_comment(db, redis, user, post_id, payload), "评论成功")


@router.get("/posts/{post_id}/comments")
async def comments(
    post_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_comments(db, user, post_id, page, page_size))


@router.delete("/comments/{comment_id}")
async def remove_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_comment(db, user, comment_id)
    return ok({"comment_id": comment_id}, "评论已删除")
