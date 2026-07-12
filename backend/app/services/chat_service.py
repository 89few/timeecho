from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_text, encrypt_text
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit
from app.core.security import utcnow
from app.models.chat import ChatMessage, ChatRoom, ChatRoomKind, ChatRoomStatus
from app.models.letter import Letter, LetterStatus
from app.models.social import Friendship
from app.models.user import User, UserStatus
from app.models.security import PrivateMedia
from app.services.config_service import get_int_config
from app.services.risk_service import check_content
from app.services.block_service import ensure_not_blocked
from app.services.media_service import signed_media_url
from app.services.anonymous_identity_service import (
    ensure_room_identities,
    room_identity_payload,
    sender_display_name,
)


def _friend_pair(user_a_id: int, user_b_id: int) -> tuple[int, int, str]:
    low, high = sorted((user_a_id, user_b_id))
    return low, high, f"{low}:{high}"


def validate_chat_message_input(
    room: ChatRoom, kind: str, content: str, media_url: str | None
) -> tuple[str, str, str | None]:
    normalized_kind = (kind or "text").strip()
    normalized_media = (media_url or "").strip() or None
    if normalized_media and normalized_media.startswith("/api/media/"):
        normalized_media = normalized_media.split("?", 1)[0]
    if normalized_kind not in {
        "text", "emoji", "sticker", "image", "video", "audio"
    }:
        raise AppException("INVALID_MESSAGE_KIND", "不支持的消息类型", 422)
    if room.room_kind == ChatRoomKind.MATCH and normalized_kind not in {
        "text", "emoji", "sticker"
    }:
        raise AppException(
            "MATCH_MEDIA_DISABLED", "即时遇见暂时只支持文字和表情", 415
        )
    if normalized_kind in {"sticker", "image", "video", "audio"} and (
        not normalized_media or not normalized_media.startswith("/api/media/")
    ):
        raise AppException("INVALID_MEDIA_URL", "媒体地址无效", 422)
    normalized_content = (content or "").strip()
    if not normalized_content and normalized_media:
        normalized_content = {
            "sticker": "[表情包]",
            "image": "[图片]",
            "video": "[视频]",
            "audio": "[语音]",
        }[normalized_kind]
    if not normalized_content:
        raise AppException("EMPTY_MESSAGE", "消息不能为空", 422)
    return normalized_kind, normalized_content, normalized_media


async def _is_friendship(db: AsyncSession, user_a_id: int, user_b_id: int) -> bool:
    low, high, _ = _friend_pair(user_a_id, user_b_id)
    return (
        await db.scalar(
            select(Friendship.id).where(
                Friendship.user_low_id == low,
                Friendship.user_high_id == high,
            )
        )
        is not None
    )


async def create_chat_room_for_letter(
    db: AsyncSession, letter_id: int, user: User, redis: Redis | None = None
) -> ChatRoom:
    letter = await db.get(Letter, letter_id)
    if not letter or letter.status != LetterStatus.SALVAGED:
        raise AppException("LETTER_NOT_SALVAGED", "该纸飞机当前不能回信", 400)
    if letter.salvaged_by != user.id:
        raise AppException("FORBIDDEN", "只有打捞者可以发起回信", 403)
    await ensure_not_blocked(db, letter.author_id, user.id)

    existing = (
        await db.execute(select(ChatRoom).where(ChatRoom.letter_id == letter_id))
    ).scalar_one_or_none()
    if existing:
        expired_at = existing.expired_at
        if expired_at and expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)
        if (
            existing.status != ChatRoomStatus.ACTIVE
            or expired_at is None
            or expired_at <= utcnow()
        ):
            raise AppException("ROOM_EXPIRED", "该纸飞机会话已结束", 400)
        return existing

    now = utcnow()
    ttl_hours = 24
    if redis is not None:
        ttl_hours = await get_int_config(
            db, redis, "room_ttl_hours", settings.room_ttl_hours
        )
    room = ChatRoom(
        letter_id=letter_id,
        friend_pair_key=None,
        room_kind=ChatRoomKind.TEMPORARY,
        user_a_id=letter.author_id,
        user_b_id=user.id,
        status=ChatRoomStatus.ACTIVE,
        created_at=now,
        expired_at=now + timedelta(hours=ttl_hours),
    )
    db.add(room)
    await db.flush()
    await ensure_room_identities(db, room)
    await db.commit()
    await db.refresh(room)
    return room


async def create_or_get_friend_room(
    db: AsyncSession, current_user: User, friend_user_id: int
) -> ChatRoom:
    if friend_user_id == current_user.id:
        raise AppException("CANNOT_MESSAGE_SELF", "不能给自己发送私信", 400)
    peer = await db.get(User, friend_user_id)
    if not peer or peer.status == UserStatus.BANNED:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    if not await _is_friendship(db, current_user.id, friend_user_id):
        raise AppException("NOT_FRIENDS", "成为好友后才能发送私信", 403)
    await ensure_not_blocked(db, current_user.id, friend_user_id)

    low, high, pair_key = _friend_pair(current_user.id, friend_user_id)
    existing = await db.scalar(
        select(ChatRoom).where(ChatRoom.friend_pair_key == pair_key)
    )
    if existing:
        if existing.status != ChatRoomStatus.ACTIVE:
            existing.status = ChatRoomStatus.ACTIVE
            existing.destroyed_at = None
            await db.commit()
            await db.refresh(existing)
        return existing

    room = ChatRoom(
        letter_id=None,
        friend_pair_key=pair_key,
        room_kind=ChatRoomKind.FRIEND,
        user_a_id=low,
        user_b_id=high,
        status=ChatRoomStatus.ACTIVE,
        created_at=utcnow(),
        expired_at=None,
    )
    db.add(room)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(ChatRoom).where(ChatRoom.friend_pair_key == pair_key)
        )
        if existing:
            return existing
        raise
    await db.refresh(room)
    return room


async def get_room_for_user(
    db: AsyncSession, room_id: int, user_id: int
) -> ChatRoom:
    room = await db.get(ChatRoom, room_id)
    if not room:
        raise AppException("ROOM_NOT_FOUND", "聊天室不存在", 404)
    if user_id not in {room.user_a_id, room.user_b_id}:
        raise AppException("FORBIDDEN", "你不属于该聊天室", 403)
    return room


async def get_active_room_for_user(
    db: AsyncSession, room_id: int, user_id: int
) -> ChatRoom:
    room = await get_room_for_user(db, room_id, user_id)
    if room.status != ChatRoomStatus.ACTIVE:
        raise AppException("ROOM_EXPIRED", "聊天室已结束", 400)

    peer_id = room.user_b_id if user_id == room.user_a_id else room.user_a_id
    await ensure_not_blocked(db, user_id, peer_id)

    if room.room_kind == ChatRoomKind.FRIEND:
        if not await _is_friendship(db, user_id, peer_id):
            raise AppException("NOT_FRIENDS", "好友关系已解除，无法继续私信", 403)
        return room

    expired_at = room.expired_at
    if expired_at and expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)
    if expired_at is None or expired_at <= utcnow():
        raise AppException("ROOM_EXPIRED", "聊天室已结束", 400)
    return room


async def chat_room_status_payload(
    db: AsyncSession, room: ChatRoom, user_id: int
) -> dict:
    identity = await room_identity_payload(db, room, user_id)
    payload = {
        "room_id": room.id,
        "room_kind": room.room_kind.value,
        "letter_id": room.letter_id,
        "status": room.status.value,
        "created_at": room.created_at,
        "expired_at": room.expired_at,
        "destroyed_at": room.destroyed_at,
        "peer_anonymous_name": identity["peer_display_name"],
        "peer_display_name": identity["peer_display_name"],
        "peer_avatar_url": identity["peer_avatar_url"],
        "is_temporary": room.room_kind != ChatRoomKind.FRIEND,
        "identity_revealed": identity["identity_revealed"],
        "card_exchange_status": identity["card_exchange_status"],
        "my_anonymous_name": identity.get("my_anonymous_name"),
        "my_anonymous_avatar_url": identity.get("my_anonymous_avatar_url"),
    }
    if identity.get("identity_revealed") or room.room_kind == ChatRoomKind.FRIEND:
        payload["peer_user_id"] = identity.get("peer_user_id")
        payload["can_view_profile"] = bool(identity.get("can_view_profile"))
    return payload


async def list_chat_rooms_for_user(db: AsyncSession, user_id: int) -> list[dict]:
    rooms = (
        await db.execute(
            select(ChatRoom)
            .where(
                or_(ChatRoom.user_a_id == user_id, ChatRoom.user_b_id == user_id),
                ChatRoom.status == ChatRoomStatus.ACTIVE,
            )
            .order_by(desc(ChatRoom.created_at))
        )
    ).scalars().all()
    room_ids = [room.id for room in rooms]
    unread_counts: dict[int, int] = {}
    last_messages: dict[int, ChatMessage] = {}
    if room_ids:
        unread_rows = (
            await db.execute(
                select(ChatMessage.room_id, func.count(ChatMessage.id))
                .where(
                    ChatMessage.room_id.in_(room_ids),
                    ChatMessage.sender_id != user_id,
                    ChatMessage.is_read.is_(False),
                    ChatMessage.deleted_at.is_(None),
                )
                .group_by(ChatMessage.room_id)
            )
        ).all()
        unread_counts = {int(room_id): int(count) for room_id, count in unread_rows}
        latest_ids = (
            select(func.max(ChatMessage.id))
            .where(
                ChatMessage.room_id.in_(room_ids),
                ChatMessage.deleted_at.is_(None),
            )
            .group_by(ChatMessage.room_id)
        )
        latest_rows = (
            await db.execute(select(ChatMessage).where(ChatMessage.id.in_(latest_ids)))
        ).scalars().all()
        last_messages = {message.room_id: message for message in latest_rows}

    result: list[dict] = []
    for room in rooms:
        if room.room_kind == ChatRoomKind.FRIEND:
            peer_id = room.user_b_id if user_id == room.user_a_id else room.user_a_id
            if not await _is_friendship(db, user_id, peer_id):
                continue
        payload = await chat_room_status_payload(db, room, user_id)
        last = last_messages.get(room.id)
        payload["unread_count"] = unread_counts.get(room.id, 0)
        payload["last_message"] = (
            decrypt_text(last.content_ciphertext)
            if last
            else None
        )
        payload["last_message_at"] = last.created_at if last else room.created_at
        result.append(payload)
    result.sort(
        key=lambda item: item.get("last_message_at") or item.get("created_at"),
        reverse=True,
    )
    return result


async def mark_messages_read(db: AsyncSession, room_id: int, reader_id: int) -> int:
    result = await db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.room_id == room_id,
            ChatMessage.sender_id != reader_id,
            ChatMessage.is_read.is_(False),
            ChatMessage.deleted_at.is_(None),
        )
        .values(is_read=True)
    )
    await db.commit()
    return int(result.rowcount or 0)


async def mark_message_read(db: AsyncSession, message_id: int) -> None:
    msg = await db.get(ChatMessage, message_id)
    if msg and not msg.is_read:
        msg.is_read = True
        await db.commit()


async def consecutive_unread_count(
    db: AsyncSession, room_id: int, sender_id: int
) -> int:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.room_id == room_id,
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(desc(ChatMessage.id))
            .limit(20)
        )
    ).scalars().all()
    count = 0
    for msg in rows:
        if msg.sender_id != sender_id or msg.is_read:
            break
        count += 1
    return count


async def save_chat_message(
    db: AsyncSession,
    redis: Redis,
    room: ChatRoom,
    sender: User,
    content: str,
    kind: str = "text",
    media_url: str | None = None,
    client_message_id: str | None = None,
) -> tuple[ChatMessage, int, bool]:
    peer_id = room.user_b_id if sender.id == room.user_a_id else room.user_a_id
    await ensure_not_blocked(db, sender.id, peer_id)
    if media_url and media_url.startswith("/api/media/"):
        public_id = media_url.rsplit("/", 1)[-1]
        owned = await db.scalar(select(PrivateMedia.id).where(PrivateMedia.public_id == public_id, PrivateMedia.owner_id == sender.id))
        if not owned:
            raise AppException("INVALID_MEDIA_URL", "媒体不存在或不属于当前用户", 422)
    normalized_client_id = (client_message_id or str(uuid4())).strip()
    if not normalized_client_id or len(normalized_client_id) > 64:
        raise AppException(
            "INVALID_CLIENT_MESSAGE_ID",
            "client_message_id 长度必须为 1 到 64 个字符",
            422,
        )
    existing = await db.scalar(
        select(ChatMessage).where(
            ChatMessage.room_id == room.id,
            ChatMessage.sender_id == sender.id,
            ChatMessage.client_message_id == normalized_client_id,
        )
    )
    if existing is not None:
        unread_count = await consecutive_unread_count(db, room.id, sender.id)
        return existing, unread_count, False
    per_minute_limit = await get_int_config(
        db,
        redis,
        "chat_message_limit_per_minute",
        settings.chat_message_limit_per_minute,
    )
    await enforce_rate_limit(
        redis,
        f"limit:chat:minute:{room.id}:{sender.id}",
        per_minute_limit,
        60,
        f"发送过于频繁，每分钟最多 {per_minute_limit} 条",
    )
    risk = await check_content(db, redis, content)
    if not risk.allowed:
        raise AppException(
            "MESSAGE_BLOCKED", risk.reason or "消息被风控拦截", 400
        )
    now = utcnow()
    msg = ChatMessage(
        room_id=room.id,
        sender_id=sender.id,
        client_message_id=normalized_client_id,
        content_ciphertext=encrypt_text(content),
        content_key_version=settings.encryption_key_version,
        message_kind=kind,
        media_url=media_url,
        is_read=False,
        risk_flag=risk.category,
        created_at=now,
    )
    db.add(msg)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(ChatMessage).where(
                ChatMessage.room_id == room.id,
                ChatMessage.sender_id == sender.id,
                ChatMessage.client_message_id == normalized_client_id,
            )
        )
        if existing is None:
            raise
        unread_count = await consecutive_unread_count(db, room.id, sender.id)
        return existing, unread_count, False
    await db.refresh(msg)
    unread_count = await consecutive_unread_count(db, room.id, sender.id)
    return msg, unread_count, True


async def chat_message_history(
    db: AsyncSession, room: ChatRoom, user_id: int
) -> list[dict]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.room_id == room.id,
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(ChatMessage.created_at)
            .limit(500 if room.room_kind == ChatRoomKind.FRIEND else 200)
        )
    ).scalars().all()
    result = []
    for msg in rows:
        sender = await db.get(User, msg.sender_id)
        sender_name = await sender_display_name(db, room, sender) if sender else "匿名用户"
        result.append(
            {
                "type": "message",
                "message_id": msg.id,
                "client_message_id": msg.client_message_id,
                "sender_name": sender_name,
                "sender_role": "self" if msg.sender_id == user_id else "peer",
                "mine": msg.sender_id == user_id,
                "content": decrypt_text(msg.content_ciphertext),
                "kind": msg.message_kind,
                "media_url": signed_media_url(msg.media_url, user_id),
                "created_at": msg.created_at,
            }
        )
    return result


async def destroy_room(
    db: AsyncSession,
    room_id: int,
    user: User | None = None,
    status: ChatRoomStatus = ChatRoomStatus.DESTROYED,
    commit: bool = True,
) -> ChatRoom:
    room = await db.get(ChatRoom, room_id)
    if not room:
        raise AppException("ROOM_NOT_FOUND", "聊天室不存在", 404)
    if user and user.id not in {room.user_a_id, room.user_b_id}:
        raise AppException("FORBIDDEN", "你不属于该聊天室", 403)
    if room.room_kind == ChatRoomKind.FRIEND:
        raise AppException("FRIEND_ROOM_PERSISTENT", "好友私信不会自动销毁", 400)
    if room.status == ChatRoomStatus.ACTIVE:
        now = utcnow()
        room.status = status
        room.destroyed_at = now
        await db.execute(
            update(ChatMessage)
            .where(
                ChatMessage.room_id == room.id,
                ChatMessage.deleted_at.is_(None),
            )
            .values(
                content_ciphertext="", deleted_at=now
            )
        )
        if commit:
            await db.commit()
            await db.refresh(room)
        else:
            await db.flush()
    return room
