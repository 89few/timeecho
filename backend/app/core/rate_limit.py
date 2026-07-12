from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import AppException


async def incr_with_expire(redis: Redis, key: str, window_seconds: int) -> int:
    value = await redis.incr(key)
    if value == 1:
        await redis.expire(key, window_seconds)
    return int(value)


async def check_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    value = await incr_with_expire(redis, key, window_seconds)
    return value <= limit


async def enforce_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int, message: str = "请求过于频繁，请稍后再试") -> None:
    if not settings.rate_limits_enabled:
        return
    allowed = await check_rate_limit(redis, key, limit, window_seconds)
    if not allowed:
        raise AppException("RATE_LIMITED", message, 429)


async def get_count(redis: Redis, key: str) -> int:
    value = await redis.get(key)
    return int(value or 0)
