from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.chat import (
    AnonymousMatch,
    ChatRoom,
    ChatRoomKind,
    ChatRoomStatus,
    MatchExclusion,
    MatchParticipant,
    MatchStateStatus,
    RecentMatch,
    UserMatchState,
)
from app.models.user import User
from app.services.anonymous_identity_service import ensure_room_identities
from app.services.block_service import create_global_block, is_blocked_between
from app.services.chat_service import chat_room_status_payload, destroy_room, get_active_room_for_user
from app.websocket.manager import manager, matching_manager

QUEUE_KEY = "match:waiting"
PREF_KEY = "match:preference:{user_id}"
HEARTBEAT_SECONDS = 60
MATCH_LOCK_KEY = "lock:matching:global"
MATCH_LOCK_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def _matching_lock(redis: Redis):
    token = secrets.token_hex(16)
    deadline = asyncio.get_running_loop().time() + 8
    acquired = False
    while asyncio.get_running_loop().time() < deadline:
        acquired = bool(
            await redis.set(MATCH_LOCK_KEY, token, nx=True, px=10_000)
        )
        if acquired:
            break
        await asyncio.sleep(0.02)
    if not acquired:
        raise AppException("MATCH_BUSY", "匹配请求较多，请稍后重试", 503)
    try:
        yield
    finally:
        await redis.eval(MATCH_LOCK_RELEASE, 1, MATCH_LOCK_KEY, token)


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _state(db: AsyncSession, user_id: int, *, lock: bool = False) -> UserMatchState:
    stmt = select(UserMatchState).where(UserMatchState.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    state = await db.scalar(stmt)
    if state is None:
        state = UserMatchState(user_id=user_id, status=MatchStateStatus.IDLE)
        db.add(state)
        await db.flush()
    return state


async def _status_payload(db: AsyncSession, user: User, state: UserMatchState) -> dict:
    data = {
        "status": state.status.value,
        "purpose": state.purpose,
        "topic": state.topic,
        "queued_at": state.queued_at,
        "room": None,
    }
    if state.status == MatchStateStatus.ACTIVE and state.room_id:
        room = await db.get(ChatRoom, state.room_id)
        if room and room.status == ChatRoomStatus.ACTIVE:
            data["room"] = await chat_room_status_payload(db, room, user.id)
        else:
            state.status = MatchStateStatus.IDLE
            state.room_id = None
    return data


async def matching_status(db: AsyncSession, redis: Redis, user: User) -> dict:
    await cleanup_stale_waiters(db, redis)
    state = await _state(db, user.id)
    data = await _status_payload(db, user, state)
    await db.commit()
    return data


async def cleanup_stale_waiters(db: AsyncSession, redis: Redis) -> int:
    cutoff = utcnow() - timedelta(seconds=HEARTBEAT_SECONDS)
    rows = list(
        (
            await db.execute(
                select(UserMatchState).where(
                    UserMatchState.status == MatchStateStatus.WAITING,
                    UserMatchState.heartbeat_at < cutoff,
                )
            )
        ).scalars().all()
    )
    for state in rows:
        state.status = MatchStateStatus.IDLE
        state.purpose = state.topic = None
        state.queued_at = state.heartbeat_at = None
        await redis.zrem(QUEUE_KEY, str(state.user_id))
        await redis.delete(PREF_KEY.format(user_id=state.user_id))
    if rows:
        await db.commit()
    return len(rows)


async def join_matching(
    db: AsyncSession, redis: Redis, user: User, purpose: str, topic: str
) -> dict:
    async with _matching_lock(redis):
        return await _join_matching_locked(db, redis, user, purpose, topic)


async def _join_matching_locked(
    db: AsyncSession, redis: Redis, user: User, purpose: str, topic: str
) -> dict:
    await cleanup_stale_waiters(db, redis)
    now = utcnow()
    state = await _state(db, user.id, lock=True)
    if state.status == MatchStateStatus.ACTIVE and state.room_id:
        return await _status_payload(db, user, state)
    if state.status != MatchStateStatus.WAITING:
        state.status = MatchStateStatus.WAITING
        state.purpose = purpose
        state.topic = topic
        state.queued_at = now
    state.heartbeat_at = now
    await db.flush()
    await redis.zadd(QUEUE_KEY, {str(user.id): now.timestamp()})
    await redis.set(
        PREF_KEY.format(user_id=user.id),
        json.dumps({"purpose": purpose, "topic": topic}),
        ex=HEARTBEAT_SECONDS + 15,
    )
    room = await _try_match(db, redis, user, state)
    if room:
        return {
            "status": "ACTIVE",
            "purpose": purpose,
            "topic": topic,
            "queued_at": state.queued_at,
            "room": await chat_room_status_payload(db, room, user.id),
        }
    await db.commit()
    return await _status_payload(db, user, state)


async def _excluded(db: AsyncSession, first: int, second: int) -> bool:
    if await is_blocked_between(db, first, second):
        return True
    return (
        await db.scalar(
            select(MatchExclusion.id).where(
                or_(
                    and_(MatchExclusion.owner_id == first, MatchExclusion.excluded_user_id == second),
                    and_(MatchExclusion.owner_id == second, MatchExclusion.excluded_user_id == first),
                )
            )
        )
        is not None
    )


def _compatibility(purpose: str, topic: str, candidate: UserMatchState, recent: RecentMatch | None) -> float:
    score = 0.0
    if {purpose, candidate.purpose} == {"VENT", "LISTEN"}:
        score += 100
    elif purpose == candidate.purpose == "CASUAL":
        score += 80
    elif purpose == candidate.purpose:
        score += 25
    if topic == candidate.topic:
        score += 35
    waited = max(0.0, (utcnow() - (_aware(candidate.queued_at) or utcnow())).total_seconds())
    score += min(waited / 3, 40)
    if recent:
        age = utcnow() - _aware(recent.last_matched_at)
        if age < timedelta(minutes=10):
            return -10000
        if age < timedelta(days=1):
            score -= 45
    return score


async def _try_match(
    db: AsyncSession, redis: Redis, user: User, state: UserMatchState
) -> ChatRoom | None:
    candidates = list(
        (
            await db.execute(
                select(UserMatchState)
                .where(
                    UserMatchState.user_id != user.id,
                    UserMatchState.status == MatchStateStatus.WAITING,
                    UserMatchState.heartbeat_at >= utcnow() - timedelta(seconds=HEARTBEAT_SECONDS),
                )
                .order_by(UserMatchState.user_id)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
    )
    ranked: list[tuple[float, UserMatchState]] = []
    for candidate in candidates:
        if await _excluded(db, user.id, candidate.user_id):
            continue
        low, high = sorted((user.id, candidate.user_id))
        recent = await db.scalar(
            select(RecentMatch).where(
                RecentMatch.user_low_id == low, RecentMatch.user_high_id == high
            )
        )
        ranked.append((_compatibility(state.purpose or "CASUAL", state.topic or "LIFE", candidate, recent), candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 0:
        return None
    candidate = ranked[0][1]
    peer = await db.get(User, candidate.user_id)
    if not peer:
        return None
    now = utcnow()
    room = ChatRoom(
        letter_id=None,
        friend_pair_key=None,
        room_kind=ChatRoomKind.MATCH,
        user_a_id=min(user.id, peer.id),
        user_b_id=max(user.id, peer.id),
        status=ChatRoomStatus.ACTIVE,
        created_at=now,
        expired_at=now + timedelta(hours=2),
    )
    db.add(room)
    await db.flush()
    match = AnonymousMatch(room_id=room.id, status="ACTIVE", created_at=now)
    db.add(match)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(match_id=match.id, user_id=user.id, purpose=state.purpose or "CASUAL", topic=state.topic or "LIFE", joined_at=now),
            MatchParticipant(match_id=match.id, user_id=peer.id, purpose=candidate.purpose or "CASUAL", topic=candidate.topic or "LIFE", joined_at=now),
        ]
    )
    await ensure_room_identities(db, room)
    for item in (state, candidate):
        item.status = MatchStateStatus.ACTIVE
        item.room_id = room.id
        item.heartbeat_at = now
    low, high = sorted((user.id, peer.id))
    recent = await db.scalar(
        select(RecentMatch).where(RecentMatch.user_low_id == low, RecentMatch.user_high_id == high)
    )
    if recent:
        recent.last_matched_at = now
        recent.match_count += 1
    else:
        db.add(RecentMatch(user_low_id=low, user_high_id=high, last_matched_at=now, match_count=1))
    await db.commit()
    for user_id in (user.id, peer.id):
        await redis.zrem(QUEUE_KEY, str(user_id))
        await redis.delete(PREF_KEY.format(user_id=user_id))
        await matching_manager.send_to_user(
            0, user_id, {"type": "matched", "room_id": room.id}
        )
    await db.refresh(room)
    return room


async def heartbeat(db: AsyncSession, redis: Redis, user: User) -> dict:
    state = await _state(db, user.id, lock=True)
    if state.status == MatchStateStatus.WAITING:
        state.heartbeat_at = utcnow()
        await redis.zadd(QUEUE_KEY, {str(user.id): state.queued_at.timestamp() if state.queued_at else utcnow().timestamp()})
        await redis.expire(PREF_KEY.format(user_id=user.id), HEARTBEAT_SECONDS + 15)
        await db.commit()
    return await _status_payload(db, user, state)


async def cancel_matching(db: AsyncSession, redis: Redis, user: User) -> dict:
    state = await _state(db, user.id, lock=True)
    if state.status == MatchStateStatus.ACTIVE:
        raise AppException("MATCH_ALREADY_ACTIVE", "已经匹配成功，请在聊天室结束对话", 409)
    state.status = MatchStateStatus.IDLE
    state.purpose = state.topic = None
    state.queued_at = state.heartbeat_at = None
    await db.commit()
    await redis.zrem(QUEUE_KEY, str(user.id))
    await redis.delete(PREF_KEY.format(user_id=user.id))
    return {"status": "IDLE", "room": None}


async def disconnect_waiter(db: AsyncSession, redis: Redis, user: User) -> None:
    state = await _state(db, user.id, lock=True)
    if state.status != MatchStateStatus.WAITING:
        return
    state.status = MatchStateStatus.IDLE
    state.purpose = state.topic = None
    state.queued_at = state.heartbeat_at = None
    await db.commit()
    await redis.zrem(QUEUE_KEY, str(user.id))
    await redis.delete(PREF_KEY.format(user_id=user.id))


async def end_match_room(
    db: AsyncSession, redis: Redis, user: User, room_id: int, action: str
) -> dict:
    async with _matching_lock(redis):
        room = await db.scalar(
            select(ChatRoom)
            .where(ChatRoom.id == room_id)
            .with_for_update()
        )
        if not room or user.id not in {room.user_a_id, room.user_b_id}:
            raise AppException("ROOM_NOT_FOUND", "聊天室不存在", 404)
        if room.status != ChatRoomStatus.ACTIVE:
            raise AppException("ROOM_EXPIRED", "聊天室已结束", 400)
        if room.room_kind != ChatRoomKind.MATCH:
            raise AppException("NOT_MATCH_ROOM", "该会话不是在线匹配房间", 400)
        peer_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
        if action == "BLOCK":
            await create_global_block(
                db,
                user.id,
                peer_id,
                source_room_id=room.id,
                commit=False,
            )
        elif action == "NO_REMATCH":
            existing = await db.scalar(
                select(MatchExclusion).where(
                    MatchExclusion.owner_id == user.id,
                    MatchExclusion.excluded_user_id == peer_id,
                    MatchExclusion.kind == action,
                )
            )
            if not existing:
                db.add(
                    MatchExclusion(
                        owner_id=user.id,
                        excluded_user_id=peer_id,
                        kind=action,
                        created_at=utcnow(),
                    )
                )
        await destroy_room(db, room.id, user, commit=False)
        match = await db.scalar(
            select(AnonymousMatch)
            .where(AnonymousMatch.room_id == room.id)
            .with_for_update()
        )
        if match:
            match.status = "ENDED"
            match.ended_reason = action
            match.ended_at = utcnow()
            participants = list(
                (
                    await db.execute(
                        select(MatchParticipant)
                        .where(MatchParticipant.match_id == match.id)
                        .order_by(MatchParticipant.user_id)
                        .with_for_update()
                    )
                ).scalars().all()
            )
            for participant in participants:
                participant.left_at = utcnow()
        states = list(
            (
                await db.execute(
                    select(UserMatchState)
                    .where(UserMatchState.room_id == room.id)
                    .order_by(UserMatchState.user_id)
                    .with_for_update()
                )
            ).scalars().all()
        )
        for state in states:
            state.status = MatchStateStatus.IDLE
            state.room_id = None
            state.purpose = state.topic = None
            state.queued_at = state.heartbeat_at = None
        await db.commit()
        for item in states:
            await redis.zrem(QUEUE_KEY, str(item.user_id))
            await redis.delete(PREF_KEY.format(user_id=item.user_id))
    await manager.send_to_user(
        room.id,
        peer_id,
        {
            "type": "room_ended",
            "room_id": room.id,
            "reason": action,
            "message": "对方已结束匿名会话",
        },
    )
    return {"status": "IDLE", "room_id": room.id, "action": action}


async def block_anonymous_room(
    db: AsyncSession, redis: Redis, user: User, room_id: int
) -> dict:
    room = await get_active_room_for_user(db, room_id, user.id)
    if room.room_kind == ChatRoomKind.FRIEND:
        raise AppException("NOT_ANONYMOUS_ROOM", "好友会话请先删除好友关系", 400)
    if room.room_kind == ChatRoomKind.MATCH:
        return await end_match_room(db, redis, user, room_id, "BLOCK")
    peer_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
    await create_global_block(
        db,
        user.id,
        peer_id,
        source_room_id=room.id,
        commit=False,
    )
    await destroy_room(db, room.id, user, commit=False)
    await db.commit()
    await manager.send_to_user(
        room.id,
        peer_id,
        {
            "type": "room_ended",
            "room_id": room.id,
            "reason": "BLOCK",
            "message": "对方已结束匿名会话",
        },
    )
    return {"room_id": room.id, "status": "DESTROYED", "action": "BLOCK"}
