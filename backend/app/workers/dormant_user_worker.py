from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.user import User, UserStatus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def dormant_user_once(days: int | None = None) -> int:
    threshold = utcnow() - timedelta(days=days or settings.dormant_after_days)
    changed = 0
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(User).where(
                User.status == UserStatus.ACTIVE,
                or_(User.last_login_at.is_(None), User.last_login_at < threshold),
                User.created_at < threshold,
            )
        )).scalars().all()
        for user in rows:
            user.status = UserStatus.DORMANT
            await redis_client.delete(f"limit:letter:day:{user.id}", f"limit:salvage:day:{user.id}", f"limit:complaint:day:{user.id}")
            changed += 1
        await db.commit()
    return changed


async def main() -> None:
    logger.info("dormant user worker started")
    while True:
        try:
            changed = await dormant_user_once()
            if changed:
                logger.info("marked %s users dormant", changed)
        except Exception:
            logger.exception("dormant user worker error")
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
