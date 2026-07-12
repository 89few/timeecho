from __future__ import annotations

import asyncio
import logging
from datetime import timezone

from app.core.constants import SEALED_ZSET_KEY
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.letter import Letter, LetterStatus
from app.services.salvage_service import add_to_available_pools, reconcile_available_letter_pools

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def process_due_letters_once(limit: int = 100, redis=None) -> int:
    redis = redis or redis_client
    now_ts = utcnow().timestamp()
    letter_ids = await redis.zrangebyscore(SEALED_ZSET_KEY, min=0, max=now_ts, start=0, num=limit)
    if not letter_ids:
        return 0

    released = 0
    async with AsyncSessionLocal() as db:
        for raw_id in letter_ids:
            try:
                letter_id = int(raw_id)
            except ValueError:
                await redis.zrem(SEALED_ZSET_KEY, raw_id)
                continue
            letter = await db.get(Letter, letter_id)
            if not letter:
                await redis.zrem(SEALED_ZSET_KEY, raw_id)
                continue
            if letter.status != LetterStatus.SEALED:
                await redis.zrem(SEALED_ZSET_KEY, raw_id)
                continue
            release_at = letter.release_at
            if release_at and release_at.tzinfo is None:
                release_at = release_at.replace(tzinfo=timezone.utc)
            if release_at and release_at <= utcnow():
                letter.status = LetterStatus.AVAILABLE
                try:
                    await db.commit()
                    await db.refresh(letter)
                    await add_to_available_pools(redis, letter)
                    await redis.zrem(SEALED_ZSET_KEY, raw_id)
                    released += 1
                except Exception:
                    await db.rollback()
                    logger.exception("release compensation required for letter_id=%s", letter_id)
                    raise
    return released


async def reconcile_available_once(redis=None) -> int:
    redis = redis or redis_client
    async with AsyncSessionLocal() as db:
        return await reconcile_available_letter_pools(db, redis)


async def main() -> None:
    logger.info("release letter worker started")
    reconcile_count = await reconcile_available_once()
    if reconcile_count:
        logger.info("reconciled %s available letters on startup", reconcile_count)
    loop_count = 0
    while True:
        try:
            released = await process_due_letters_once()
            loop_count += 1
            if loop_count % 12 == 0:
                fixed = await reconcile_available_once()
                if fixed:
                    logger.info("reconciled %s missing available pool indexes", fixed)
            if released:
                logger.info("released %s letters", released)
        except Exception:
            logger.exception("release worker error")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
