from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import mimetypes
import json

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis
from redis.asyncio import Redis
from app.core.exceptions import AppException, ok
from app.models.user import User
from app.models.security import PrivateMedia
from app.core.security import utcnow
from app.models.chat import ChatRoomKind
from app.services.chat_service import chat_message_history, chat_room_status_payload, create_or_get_friend_room, destroy_room, get_active_room_for_user, get_room_for_user, list_chat_rooms_for_user, mark_message_read, save_chat_message, validate_chat_message_input
from app.services.anonymous_identity_service import sender_display_name
from app.schemas.chat import ChatMessageCreate
from app.services.anonymous_identity_service import consent_card_exchange
from app.websocket.manager import manager
from app.services.matching_service import block_anonymous_room
from app.services.notification_service import create_notification
from app.models.notification import NotificationType
from app.services.media_service import signed_media_url

router = APIRouter(prefix="/chat", tags=["chat"])
UPLOAD_DIR = Path("private_uploads")
ALLOWED_MEDIA = {
    "image/jpeg": ("image", ".jpg", 8 * 1024 * 1024),
    "image/png": ("image", ".png", 8 * 1024 * 1024),
    "image/webp": ("sticker", ".webp", 8 * 1024 * 1024),
    "video/mp4": ("video", ".mp4", 30 * 1024 * 1024),
    "video/quicktime": ("video", ".mov", 30 * 1024 * 1024),
    "audio/mp4": ("audio", ".m4a", 10 * 1024 * 1024),
    "audio/aac": ("audio", ".aac", 10 * 1024 * 1024),
    "audio/mpeg": ("audio", ".mp3", 10 * 1024 * 1024),
}


@router.post("/friends/{friend_user_id}/room")
async def friend_room(
    friend_user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await create_or_get_friend_room(db, user, friend_user_id)
    return ok(await chat_room_status_payload(db, room, user.id), "好友会话已建立")


@router.get("/rooms")
async def room_list(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await list_chat_rooms_for_user(db, user.id))


@router.get("/rooms/{room_id}")
async def room_status(room_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    room = await get_room_for_user(db, room_id, user.id)
    return ok(await chat_room_status_payload(db, room, user.id))


@router.get("/rooms/{room_id}/messages")
async def room_messages(room_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    room = await get_active_room_for_user(db, room_id, user.id)
    return ok(await chat_message_history(db, room, user.id))


@router.post("/rooms/{room_id}/messages")
async def send_room_message(
    room_id: int,
    payload: ChatMessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    room = await get_active_room_for_user(db, room_id, user.id)
    kind, content, media_url = validate_chat_message_input(
        room, payload.kind, payload.content, payload.media_url
    )
    message, unread_count, created = await save_chat_message(
        db,
        redis,
        room,
        user,
        content,
        kind=kind,
        media_url=media_url,
        client_message_id=payload.client_message_id,
    )
    if created:
        recipient_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
        message_payload = {
            "type": "message",
            "room_id": room.id,
            "message_id": message.id,
            "client_message_id": message.client_message_id,
            "sender_name": await sender_display_name(db, room, user),
            "sender_role": "peer",
            "content": content,
            "kind": kind,
            "media_url": signed_media_url(media_url, recipient_id),
            "created_at": message.created_at.isoformat(),
        }
        if await manager.send_to_user(room.id, recipient_id, message_payload):
            await mark_message_read(db, message.id)
        else:
            offline_key = f"chat:offline:{room.id}:{recipient_id}"
            await redis.rpush(
                offline_key, json.dumps(message_payload, ensure_ascii=False)
            )
            await redis.expire(offline_key, 60 * 60 * 12)
    return ok(
        {
            "message_id": message.id,
            "client_message_id": message.client_message_id,
            "created": created,
            "unread_count": unread_count,
        },
        "发送成功" if created else "重复消息已忽略",
    )


@router.post("/rooms/{room_id}/exit")
async def exit_room(room_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    active = await get_active_room_for_user(db, room_id, user.id)
    peer_id = active.user_b_id if user.id == active.user_a_id else active.user_a_id
    room = await destroy_room(db, room_id, user)
    await manager.send_to_user(
        room.id,
        peer_id,
        {
            "type": "room_ended",
            "room_id": room.id,
            "reason": "EXIT",
            "message": "对方已结束匿名会话",
        },
    )
    return ok({"room_id": room.id, "status": room.status.value}, "会话已销毁")


@router.post("/rooms/{room_id}/card-exchange")
async def exchange_card(
    room_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await get_active_room_for_user(db, room_id, user.id)
    data = await consent_card_exchange(db, room, user.id)
    peer_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
    if data.pop("newly_consented", False) and not data["identity_revealed"]:
        await create_notification(
            db,
            user_id=peer_id,
            actor_id=None,
            notification_type=NotificationType.CARD_EXCHANGE,
            title="交换名片邀请",
            message="匿名会话中的对方邀请你交换名片",
            data={"room_id": room.id},
        )
    await manager.send_to_user(
        room.id,
        peer_id,
        {
            "type": "card_exchange",
            "status": "REVEALED" if data["identity_revealed"] else "INVITED",
            "message": "双方已交换名片" if data["identity_revealed"] else "对方邀请你交换名片",
        },
    )
    return ok(data, "双方已交换名片" if data["identity_revealed"] else "已同意，等待对方确认")


@router.post("/rooms/{room_id}/block")
async def block_room(
    room_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    return ok(await block_anonymous_room(db, redis, user, room_id), "已拉黑并结束会话")


@router.post("/rooms/{room_id}/media")
async def upload_media(
    room_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await get_active_room_for_user(db, room_id, user.id)
    if room.room_kind == ChatRoomKind.MATCH:
        from app.core.exceptions import AppException

        raise AppException("MATCH_MEDIA_DISABLED", "即时遇见暂时只支持文字和表情", 415)
    detected_type = file.content_type or ""
    if detected_type in {"", "application/octet-stream"}:
        detected_type = mimetypes.guess_type(file.filename or "")[0] or detected_type
    media = ALLOWED_MEDIA.get(detected_type)
    if media is None:
        from app.core.exceptions import AppException

        raise AppException("UNSUPPORTED_MEDIA", "仅支持 JPG、PNG、WebP、MP4 和常用音频格式", 415)
    kind, suffix, max_bytes = media
    content = await file.read(max_bytes + 1)
    await file.close()
    if not content:
        raise AppException("EMPTY_MEDIA", "媒体文件不能为空", 422)
    if len(content) > max_bytes:
        from app.core.exceptions import AppException

        raise AppException("MEDIA_TOO_LARGE", "媒体文件过大", 413)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}{suffix}"
    (UPLOAD_DIR / name).write_bytes(content)
    public_id = uuid4().hex
    db.add(PrivateMedia(public_id=public_id, owner_id=user.id, storage_name=name, content_type=detected_type, kind=kind, size_bytes=len(content), created_at=utcnow()))
    await db.commit()
    return ok({"kind": kind, "url": signed_media_url(f"/api/media/{public_id}", user.id), "size": len(content)}, "上传成功")
