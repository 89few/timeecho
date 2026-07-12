from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.chat import AnonymousIdentity, ChatRoom, ChatRoomKind
from app.models.social import FriendRemark
from app.models.user import User

ADJECTIVES = (
    "安静", "温柔", "清醒", "慢热", "勇敢", "自在", "晴朗", "柔软",
    "沉静", "好奇", "朦胧", "轻盈", "坦率", "可靠", "慵懒", "明亮",
)
NOUNS = (
    "海獭", "白鲸", "松鼠", "山雀", "月兔", "灰鹤", "小鹿", "海豚",
    "橘猫", "狐狸", "企鹅", "云豹", "信鸽", "树懒", "萤火", "鲸鱼",
)


def identity_scope(room: ChatRoom) -> tuple[str, int]:
    if room.room_kind == ChatRoomKind.TEMPORARY and room.letter_id is not None:
        return "LETTER", room.letter_id
    return "ROOM", room.id


async def ensure_identity(
    db: AsyncSession, scope_type: str, scope_id: int, user_id: int
) -> AnonymousIdentity:
    identity = await db.scalar(
        select(AnonymousIdentity).where(
            AnonymousIdentity.scope_type == scope_type,
            AnonymousIdentity.scope_id == scope_id,
            AnonymousIdentity.user_id == user_id,
        )
    )
    if identity:
        return identity
    appearances = set(
        (
            await db.execute(
                select(
                    AnonymousIdentity.anonymous_name,
                    AnonymousIdentity.avatar_url,
                ).where(
                    AnonymousIdentity.scope_type == scope_type,
                    AnonymousIdentity.scope_id == scope_id,
                )
            )
        ).all()
    )
    anonymous_name = ""
    avatar_url = ""
    for _ in range(64):
        anonymous_name = (
            f"{secrets.choice(ADJECTIVES)}的{secrets.choice(NOUNS)}"
        )
        avatar_url = (
            f"/static/assets/avatars/avatar-{secrets.randbelow(6) + 1}.png"
        )
        if (anonymous_name, avatar_url) not in appearances:
            break
    else:
        raise AppException("ANONYMOUS_IDENTITY_EXHAUSTED", "匿名身份生成失败", 500)
    identity = AnonymousIdentity(
        scope_type=scope_type,
        scope_id=scope_id,
        user_id=user_id,
        anonymous_name=anonymous_name,
        avatar_url=avatar_url,
        card_consented=False,
        created_at=utcnow(),
    )
    db.add(identity)
    await db.flush()
    return identity


async def ensure_letter_identities(
    db: AsyncSession, letter_id: int, author_id: int, salvager_id: int
) -> tuple[AnonymousIdentity, AnonymousIdentity]:
    author = await ensure_identity(db, "LETTER", letter_id, author_id)
    salvager = await ensure_identity(db, "LETTER", letter_id, salvager_id)
    return author, salvager


async def ensure_room_identities(
    db: AsyncSession, room: ChatRoom
) -> tuple[AnonymousIdentity, AnonymousIdentity]:
    scope_type, scope_id = identity_scope(room)
    first = await ensure_identity(db, scope_type, scope_id, room.user_a_id)
    second = await ensure_identity(db, scope_type, scope_id, room.user_b_id)
    return first, second


async def room_identity_payload(
    db: AsyncSession, room: ChatRoom, viewer_id: int
) -> dict:
    if viewer_id not in {room.user_a_id, room.user_b_id}:
        raise AppException("FORBIDDEN", "你不属于该聊天室", 403)
    peer_id = room.user_b_id if viewer_id == room.user_a_id else room.user_a_id
    peer = await db.get(User, peer_id)
    if room.room_kind == ChatRoomKind.FRIEND:
        remark = await db.scalar(
            select(FriendRemark.remark).where(
                FriendRemark.owner_id == viewer_id,
                FriendRemark.friend_id == peer_id,
            )
        )
        display_name = remark or ((peer.username or peer.anonymous_name) if peer else "好友")
        return {
            "peer_display_name": display_name,
            "peer_avatar_url": peer.avatar_url if peer else None,
            "peer_user_id": peer_id,
            "can_view_profile": True,
            "identity_revealed": True,
            "card_exchange_status": "NOT_REQUIRED",
        }

    first, second = await ensure_room_identities(db, room)
    mine = first if first.user_id == viewer_id else second
    theirs = second if first.user_id == viewer_id else first
    revealed = bool(mine.revealed_at and theirs.revealed_at)
    if revealed and peer:
        return {
            "peer_display_name": peer.username or peer.anonymous_name,
            "peer_avatar_url": peer.avatar_url,
            "peer_user_id": peer.id,
            "can_view_profile": True,
            "identity_revealed": True,
            "card_exchange_status": "REVEALED",
            "my_anonymous_name": mine.anonymous_name,
            "my_anonymous_avatar_url": mine.avatar_url,
        }
    if mine.card_consented and not theirs.card_consented:
        exchange_status = "WAITING_FOR_PEER"
    elif theirs.card_consented and not mine.card_consented:
        exchange_status = "INVITED"
    else:
        exchange_status = "NONE"
    return {
        "peer_display_name": theirs.anonymous_name,
        "peer_avatar_url": theirs.avatar_url,
        "identity_revealed": False,
        "card_exchange_status": exchange_status,
        "my_anonymous_name": mine.anonymous_name,
        "my_anonymous_avatar_url": mine.avatar_url,
    }


async def consent_card_exchange(
    db: AsyncSession, room: ChatRoom, user_id: int
) -> dict:
    if room.room_kind == ChatRoomKind.FRIEND:
        raise AppException("CARD_ALREADY_VISIBLE", "好友会话已显示真实身份", 409)
    if user_id not in {room.user_a_id, room.user_b_id}:
        raise AppException("FORBIDDEN", "你不属于该聊天室", 403)
    scope_type, scope_id = identity_scope(room)
    identities = list(
        (
            await db.execute(
                select(AnonymousIdentity)
                .where(
                    AnonymousIdentity.scope_type == scope_type,
                    AnonymousIdentity.scope_id == scope_id,
                )
                .with_for_update()
            )
        ).scalars().all()
    )
    if len(identities) < 2:
        await ensure_room_identities(db, room)
        identities = list(
            (
                await db.execute(
                    select(AnonymousIdentity)
                    .where(
                        AnonymousIdentity.scope_type == scope_type,
                        AnonymousIdentity.scope_id == scope_id,
                    )
                    .with_for_update()
                )
            ).scalars().all()
        )
    mine = next((item for item in identities if item.user_id == user_id), None)
    peer = next((item for item in identities if item.user_id != user_id), None)
    if not mine or not peer:
        raise AppException("ROOM_IDENTITY_INCOMPLETE", "匿名身份初始化失败", 500)
    now = utcnow()
    newly_consented = not mine.card_consented
    if newly_consented:
        mine.card_consented = True
        mine.consented_at = now
    revealed = mine.card_consented and peer.card_consented
    if revealed:
        # Both rows switch in the same database transaction and timestamp.
        mine.revealed_at = peer.revealed_at = now
    await db.commit()
    payload = await room_identity_payload(db, room, user_id)
    payload["newly_consented"] = newly_consented
    return payload


async def sender_display_name(
    db: AsyncSession, room: ChatRoom, sender: User
) -> str:
    if room.room_kind == ChatRoomKind.FRIEND:
        recipient_id = (
            room.user_b_id if sender.id == room.user_a_id else room.user_a_id
        )
        remark = await db.scalar(
            select(FriendRemark.remark).where(
                FriendRemark.owner_id == recipient_id,
                FriendRemark.friend_id == sender.id,
            )
        )
        return remark or sender.username or sender.anonymous_name
    first, second = await ensure_room_identities(db, room)
    mine = first if first.user_id == sender.id else second
    peer = second if first.user_id == sender.id else first
    if mine.revealed_at and peer.revealed_at:
        return sender.username or sender.anonymous_name
    return mine.anonymous_name
