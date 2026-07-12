from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update

from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.chat import (
    AnonymousMatch,
    ChatMessage,
    ChatRoom,
    ChatRoomKind,
    ChatRoomStatus,
    MatchParticipant,
    MatchStateStatus,
    UserMatchState,
)
from app.models.letter import Letter, LetterStatus
from app.services.salvage_service import remove_from_available_pools

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def cleanup_once(redis=None) -> dict[str, int]:
    redis = redis or redis_client
    now = utcnow()
    rooms = 0
    letters = 0
    async with AsyncSessionLocal() as db:
        expired_rooms = (await db.execute(
            select(ChatRoom).where(ChatRoom.status == ChatRoomStatus.ACTIVE, ChatRoom.expired_at <= now)
        )).scalars().all()
        for room in expired_rooms:
            room.status = ChatRoomStatus.EXPIRED
            room.destroyed_at = now
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.room_id == room.id, ChatMessage.deleted_at.is_(None))
                .values(content_ciphertext="", deleted_at=now)
            )
            await redis.delete(f"chat:offline:{room.id}:{room.user_a_id}", f"chat:offline:{room.id}:{room.user_b_id}")
            if room.room_kind == ChatRoomKind.MATCH:
                match = await db.scalar(select(AnonymousMatch).where(AnonymousMatch.room_id == room.id))
                if match:
                    match.status = "ENDED"
                    match.ended_reason = "TIMEOUT"
                    match.ended_at = now
                    await db.execute(
                        update(MatchParticipant)
                        .where(MatchParticipant.match_id == match.id, MatchParticipant.left_at.is_(None))
                        .values(left_at=now)
                    )
                await db.execute(
                    update(UserMatchState)
                    .where(UserMatchState.room_id == room.id)
                    .values(
                        status=MatchStateStatus.IDLE,
                        room_id=None,
                        purpose=None,
                        topic=None,
                        queued_at=None,
                        heartbeat_at=None,
                    )
                )
            rooms += 1

        expired_letters = (await db.execute(
            select(Letter).where(Letter.status == LetterStatus.SALVAGED, Letter.destroy_at <= now)
        )).scalars().all()
        for letter in expired_letters:
            letter.status = LetterStatus.DESTROYED
            letter.content_ciphertext = ""
            await remove_from_available_pools(redis, letter)
            letters += 1

        await db.commit()
    return {"rooms": rooms, "letters": letters}


async def main() -> None:
    logger.info("cleanup worker started")
    while True:
        try:
            result = await cleanup_once()
            if result["rooms"] or result["letters"]:
                logger.info("cleanup result: %s", result)
        except Exception:
            logger.exception("cleanup worker error")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
