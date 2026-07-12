from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.social import PostComment, PostLike, PostVisibility, SocialPost
from app.models.user import User
from app.schemas.social import CommentCreate
from app.services.social_service import create_comment, toggle_post_like

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

COMMENTS = (
    "很喜欢这样安静的瞬间。",
    "看到这里，心情也跟着轻了一点。",
    "愿接下来还有更多小小的好事。",
    "这份感受我也有过，抱抱你。",
    "普通的一天被你记录得很温柔。",
    "谢谢分享，刚好需要看到这句话。",
)


async def engage_once() -> dict:
    if settings.app_env != "dev" or not settings.community_simulation_enabled:
        return {"action": "disabled"}
    rng = random.SystemRandom()
    async with AsyncSessionLocal() as db:
        bots = list(
            (
                await db.execute(
                    select(User).where(User.email.like("echo%@timeecho.local"))
                )
            ).scalars().all()
        )
        if not bots:
            return {"action": "no_community_accounts"}
        bot_ids = [bot.id for bot in bots]
        posts = list(
            (
                await db.execute(
                    select(SocialPost)
                    .where(
                        SocialPost.author_id.not_in(bot_ids),
                        SocialPost.visibility == PostVisibility.PUBLIC,
                        SocialPost.deleted_at.is_(None),
                        SocialPost.created_at <= utcnow() - timedelta(minutes=2),
                    )
                    .order_by(SocialPost.created_at.desc())
                    .limit(60)
                )
            ).scalars().all()
        )
        rng.shuffle(posts)
        rng.shuffle(bots)
        for post in posts:
            for bot in bots:
                already_liked = await db.scalar(
                    select(PostLike.id).where(PostLike.post_id == post.id, PostLike.user_id == bot.id)
                )
                already_commented = await db.scalar(
                    select(PostComment.id).where(PostComment.post_id == post.id, PostComment.author_id == bot.id)
                )
                like_count = int(await db.scalar(select(func.count(PostLike.id)).where(PostLike.post_id == post.id)) or 0)
                comment_count = int(await db.scalar(select(func.count(PostComment.id)).where(PostComment.post_id == post.id)) or 0)
                if not already_liked and like_count < 6:
                    await toggle_post_like(db, bot, post.id)
                    return {"action": "like", "post_id": post.id}
                if not already_commented and comment_count < 4 and rng.random() < 0.45:
                    await create_comment(
                        db,
                        redis_client,
                        bot,
                        post.id,
                        CommentCreate(text=rng.choice(COMMENTS)),
                    )
                    return {"action": "comment", "post_id": post.id}
        return {"action": "nothing_due"}


async def main() -> None:
    logger.info("community interaction worker started")
    while True:
        minimum = max(60, settings.community_simulation_min_seconds)
        maximum = max(minimum, settings.community_simulation_max_seconds)
        # Wait before every action, including the first one after a restart, so
        # interactions never appear as an immediate automated response.
        await asyncio.sleep(random.SystemRandom().randint(minimum, maximum))
        try:
            result = await engage_once()
            if result["action"] not in {"nothing_due", "disabled"}:
                logger.info("community interaction: %s", result["action"])
        except Exception:
            logger.exception("community interaction worker error")


if __name__ == "__main__":
    asyncio.run(main())
