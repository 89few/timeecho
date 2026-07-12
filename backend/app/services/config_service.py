from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_config import SystemConfig

CONFIG_CACHE_PREFIX = "risk:system_config:"
CONFIG_CACHE_TTL = 300

DEFAULT_CONFIGS: dict[str, int] = {
    "daily_letter_limit": settings.daily_letter_limit,
    "daily_salvage_limit": settings.daily_salvage_limit,
    "daily_complaint_limit": settings.daily_complaint_limit,
    "chat_message_limit_per_minute": settings.chat_message_limit_per_minute,
    "room_ttl_hours": getattr(settings, "room_ttl_hours", 24),
}

CONFIG_RULES: dict[str, tuple[int, int]] = {
    "daily_letter_limit": (0, 1000),
    "daily_salvage_limit": (0, 1000),
    "daily_complaint_limit": (1, 1000),
    "chat_message_limit_per_minute": (1, 600),
    "room_ttl_hours": (1, 720),
}


def validate_config(config_key: str, raw_value: str) -> str:
    if config_key not in CONFIG_RULES:
        raise ValueError("configuration key is not allowed")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("configuration value must be an integer") from exc
    minimum, maximum = CONFIG_RULES[config_key]
    if not minimum <= value <= maximum:
        raise ValueError(f"configuration value must be between {minimum} and {maximum}")
    return str(value)


def _cache_key(config_key: str) -> str:
    return f"{CONFIG_CACHE_PREFIX}{config_key}"


async def get_config_value(db: AsyncSession, redis: Redis | None, config_key: str, default: str | int | None = None) -> str | None:
    if redis is not None:
        cached = await redis.get(_cache_key(config_key))
        if cached is not None:
            return str(cached)

    row = (await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))).scalar_one_or_none()
    if row is not None:
        value = row.config_value
    elif default is not None:
        value = str(default)
    elif config_key in DEFAULT_CONFIGS:
        value = str(DEFAULT_CONFIGS[config_key])
    else:
        value = None

    if redis is not None and value is not None:
        await redis.set(_cache_key(config_key), value, ex=CONFIG_CACHE_TTL)
    return value


async def get_int_config(db: AsyncSession, redis: Redis | None, config_key: str, default: int | None = None) -> int:
    raw = await get_config_value(db, redis, config_key, default if default is not None else DEFAULT_CONFIGS.get(config_key))
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        if default is not None:
            return default
        return int(DEFAULT_CONFIGS[config_key])


async def clear_config_cache(redis: Redis, config_key: str | None = None) -> None:
    if config_key:
        await redis.delete(_cache_key(config_key))
        return
    if hasattr(redis, "keys"):
        keys = await redis.keys(f"{CONFIG_CACHE_PREFIX}*")
        if keys:
            await redis.delete(*keys)
