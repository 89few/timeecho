from __future__ import annotations

from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    AVAILABLE_ALL_KEY,
    AVAILABLE_CITY_KEY,
    AVAILABLE_EMOTION_CITY_KEY,
    AVAILABLE_EMOTION_KEY,
)
from app.core.crypto import decrypt_text
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit
from app.core.security import utcnow
from app.models.letter import Letter, LetterStatus
from app.models.user import User
from app.services.config_service import get_int_config
from app.services.anonymous_identity_service import ensure_letter_identities
from app.services.block_service import is_blocked_between

AVAILABLE_POOL_PATTERNS = [
    AVAILABLE_ALL_KEY,
    "letter:available:emotion:*",
    "letter:available:city:*",
    "letter:available:emotion_city:*",
]


def available_keys(emotion: str | None, city: str | None) -> list[str]:
    keys = [AVAILABLE_ALL_KEY]
    if emotion:
        keys.append(AVAILABLE_EMOTION_KEY.format(emotion=emotion))
    if city:
        keys.append(AVAILABLE_CITY_KEY.format(city=city))
    if emotion and city:
        keys.append(AVAILABLE_EMOTION_CITY_KEY.format(emotion=emotion, city=city))
    return keys


def ordered_match_keys(emotion: str | None, city: str | None) -> list[str]:
    keys: list[str] = []
    if emotion and city:
        keys.append(AVAILABLE_EMOTION_CITY_KEY.format(emotion=emotion, city=city))
    if emotion:
        keys.append(AVAILABLE_EMOTION_KEY.format(emotion=emotion))
    if city:
        keys.append(AVAILABLE_CITY_KEY.format(city=city))
    keys.append(AVAILABLE_ALL_KEY)
    return keys


async def add_to_available_pools(redis: Redis, letter: Letter) -> None:
    if letter.status != LetterStatus.AVAILABLE:
        return
    letter_id = str(letter.id)
    for key in available_keys(letter.emotion, letter.city):
        await redis.sadd(key, letter_id)


async def remove_from_available_pools(redis: Redis, letter: Letter) -> None:
    letter_id = str(letter.id)
    for key in available_keys(letter.emotion, letter.city):
        await redis.srem(key, letter_id)


async def rebuild_available_letter_pools(db: AsyncSession, redis: Redis) -> int:
    keys_to_delete: set[str] = set()
    for pattern in AVAILABLE_POOL_PATTERNS:
        if "*" in pattern and hasattr(redis, "keys"):
            keys_to_delete.update(await redis.keys(pattern))
        else:
            keys_to_delete.add(pattern)
    if keys_to_delete:
        await redis.delete(*keys_to_delete)

    rows = (await db.execute(select(Letter).where(Letter.status == LetterStatus.AVAILABLE))).scalars().all()
    for letter in rows:
        await add_to_available_pools(redis, letter)
    return len(rows)


async def reconcile_available_letter_pools(db: AsyncSession, redis: Redis) -> int:
    rows = (await db.execute(select(Letter).where(Letter.status == LetterStatus.AVAILABLE))).scalars().all()
    fixed = 0
    for letter in rows:
        if not await redis.sismember(AVAILABLE_ALL_KEY, str(letter.id)):
            await add_to_available_pools(redis, letter)
            fixed += 1
    return fixed


async def _pick_candidate(redis: Redis, key: str) -> str | None:
    member = await redis.srandmember(key)
    return str(member) if member else None


async def salvage_letter(db: AsyncSession, redis: Redis, user: User, emotion: str | None, city: str | None) -> dict | None:
    daily_limit = await get_int_config(db, redis, "daily_salvage_limit", settings.daily_salvage_limit)
    rate_limit_key = f"limit:salvage:day:{user.id}"

    target_emotion = emotion or user.emotion
    target_city = city or user.city
    keys = ordered_match_keys(target_emotion, target_city)

    tried: set[int] = set()
    for key in keys:
        for _ in range(20):
            raw_id = await _pick_candidate(redis, key)
            if not raw_id:
                break
            try:
                letter_id = int(raw_id)
            except ValueError:
                await redis.srem(key, raw_id)
                continue
            if letter_id in tried:
                continue
            tried.add(letter_id)

            letter = await db.get(Letter, letter_id)
            if not letter or letter.status != LetterStatus.AVAILABLE:
                if letter:
                    await remove_from_available_pools(redis, letter)
                continue
            if letter.author_id == user.id:
                continue
            if await is_blocked_between(db, letter.author_id, user.id):
                continue

            now = utcnow()
            destroy_at = now + timedelta(hours=24)
            result = await db.execute(
                update(Letter)
                .where(Letter.id == letter_id, Letter.status == LetterStatus.AVAILABLE, Letter.author_id != user.id)
                .values(status=LetterStatus.SALVAGED, salvaged_by=user.id, salvaged_at=now, destroy_at=destroy_at)
            )
            if result.rowcount == 1:
                # Only a real, database-confirmed salvage consumes quota.
                # If quota is exhausted, roll back the candidate update so
                # another user can still salvage this letter.
                try:
                    await enforce_rate_limit(redis, rate_limit_key, daily_limit, 86400, "今日打捞次数已达上限")
                except AppException:
                    await db.rollback()
                    raise
                letter = await db.get(Letter, letter_id)
                assert letter is not None
                author_identity, _ = await ensure_letter_identities(
                    db, letter.id, letter.author_id, user.id
                )
                await db.commit()
                await db.refresh(letter)
                await remove_from_available_pools(redis, letter)
                content = decrypt_text(letter.content_ciphertext)
                return {
                    "letter_id": letter.id,
                    "content": content,
                    "emotion": letter.emotion,
                    "author_anonymous_name": author_identity.anonymous_name,
                    "author_anonymous_avatar_url": author_identity.avatar_url,
                    "salvaged_at": letter.salvaged_at,
                    "destroy_at": letter.destroy_at,
                }
            await db.rollback()
    return None
