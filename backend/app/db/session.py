from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from redis.asyncio import Redis

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug is True and settings.app_env == "local-debug")
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def close_resources() -> None:
    await engine.dispose()
    await redis_client.aclose()
