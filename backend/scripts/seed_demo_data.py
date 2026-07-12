from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.core.crypto import encrypt_text, phone_hash
from app.core.config import settings
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.user import User, UserStatus
from app.models.social import Friendship, PostComment, PostLike, PostMedia, PostVisibility, SocialPost
from app.services.salvage_service import rebuild_available_letter_pools

EMOTIONS = ["喜悦", "疲惫", "焦虑", "孤独", "平静"]
CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "南京", "重庆"]
TEXTS = [
    "晚风经过窗边的时候，我忽然想起一件很久以前的小事。",
    "今天也认真生活过了，希望看到这封信的人一切顺利。",
    "有些答案不用马上找到，慢一点也没有关系。",
    "刚走过一条开满花的小路，想把这份安静留给陌生的你。",
    "如果你最近有点累，就把这一分钟当作树洞里的休息。",
    "我正在学习接受不完美，也祝你能对自己温柔一点。",
    "城市很吵，但总有一盏灯和一个角落属于认真生活的人。",
    "今天完成了一件拖了很久的事，小小地为自己高兴。",
]


async def seed(user_count: int, letters_per_user: int) -> None:
    rng = random.Random(20260709)
    now = utcnow()
    async with AsyncSessionLocal() as db:
        users: list[User] = []
        for index in range(user_count):
            phone = f"199{index:08d}"
            hashed = phone_hash(phone)
            user = await db.scalar(select(User).where(User.phone_hash == hashed))
            if user is None:
                user = User(
                    phone_hash=hashed,
                    phone_ciphertext=encrypt_text(phone),
                    anonymous_name=f"回声{index + 1:04d}",
                    city=CITIES[index % len(CITIES)],
                    emotion=EMOTIONS[index % len(EMOTIONS)],
                    status=UserStatus.ACTIVE,
                    last_login_at=now - timedelta(minutes=rng.randrange(1, 10000)),
                    username=f"demo_{index + 1:04d}",
                    avatar_url=f"/static/assets/avatars/avatar-{(index % 6) + 1}.png",
                )
                db.add(user)
            else:
                if not user.username:
                    user.username = f"demo_{index + 1:04d}"
                if not user.avatar_url:
                    user.avatar_url = f"/static/assets/avatars/avatar-{(index % 6) + 1}.png"
            users.append(user)
        await db.flush()

        seeded_author_ids = [user.id for user in users]
        existing_letters = await db.scalar(
            select(func.count(Letter.id)).where(Letter.author_id.in_(seeded_author_ids))
        )
        target_letters = user_count * letters_per_user
        if (existing_letters or 0) < target_letters:
            for user_index, user in enumerate(users):
                for letter_index in range(letters_per_user):
                    marker = f"[演示数据] U{user_index:04d}-L{letter_index:02d}"
                    content = f"{marker} {TEXTS[(user_index + letter_index) % len(TEXTS)]}"
                    # 70% immediately available, 20% sealed, 10% already salvaged.
                    bucket = (user_index + letter_index) % 10
                    status = LetterStatus.AVAILABLE if bucket < 7 else LetterStatus.SEALED
                    salvager = None
                    salvaged_at = None
                    destroy_at = None
                    if bucket == 9:
                        status = LetterStatus.SALVAGED
                        salvager = users[(user_index + 17) % len(users)].id
                        salvaged_at = now - timedelta(hours=rng.randrange(1, 20))
                        destroy_at = salvaged_at + timedelta(hours=24)
                    letter = Letter(
                        author_id=user.id,
                        content_ciphertext=encrypt_text(content),
                        content_key_version=settings.encryption_key_version,
                        emotion=EMOTIONS[(user_index + letter_index) % len(EMOTIONS)],
                        city=CITIES[(user_index + letter_index) % len(CITIES)],
                        status=status,
                        seal_days=7,
                        release_at=now - timedelta(days=1) if status != LetterStatus.SEALED else now + timedelta(days=7),
                        salvaged_by=salvager,
                        salvaged_at=salvaged_at,
                        destroy_at=destroy_at,
                        risk_level=RiskLevel.NONE,
                    )
                    db.add(letter)
            await db.commit()
        else:
            await db.commit()

        # Public feed and lightweight social graph for realistic UI testing.
        post_count = min(user_count, 120)
        for index, user in enumerate(users[:post_count]):
            marker = f"[演示动态] P{index:04d}"
            post = await db.scalar(
                select(SocialPost).where(SocialPost.author_id == user.id, SocialPost.text.like(f"{marker}%"))
            )
            if post is None:
                post = SocialPost(
                    author_id=user.id,
                    text=f"{marker} {TEXTS[index % len(TEXTS)]}",
                    visibility=PostVisibility.PUBLIC,
                    created_at=now - timedelta(minutes=index * 11),
                    updated_at=now - timedelta(minutes=index * 11),
                )
                db.add(post)
                await db.flush()
                if index % 3 == 0:
                    db.add(
                        PostMedia(
                            post_id=post.id,
                            kind="image",
                            url=f"/static/assets/avatars/avatar-{(index % 6) + 1}.png",
                            sort_order=0,
                            created_at=post.created_at,
                        )
                    )
                liker = users[(index + 1) % len(users)]
                db.add(PostLike(post_id=post.id, user_id=liker.id, created_at=post.created_at))
                db.add(
                    PostComment(
                        post_id=post.id,
                        author_id=liker.id,
                        text="这条回声我听见了。",
                        created_at=post.created_at,
                        updated_at=post.created_at,
                    )
                )

        for index in range(min(user_count - 1, 100)):
            low, high = sorted((users[index].id, users[index + 1].id))
            exists = await db.scalar(
                select(Friendship.id).where(
                    Friendship.user_low_id == low,
                    Friendship.user_high_id == high,
                )
            )
            if not exists:
                db.add(Friendship(user_low_id=low, user_high_id=high, created_at=now))
        await db.commit()

        available_count = await rebuild_available_letter_pools(db, redis_client)
        total_users = await db.scalar(select(func.count(User.id)))
        total_letters = await db.scalar(select(func.count(Letter.id)))
        total_posts = await db.scalar(select(func.count(SocialPost.id)))
        print(
            f"Seed complete: users={total_users}, letters={total_letters}, "
            f"posts={total_posts}, available_pool={available_count}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create deterministic TimeEcho demo users and letters.")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--letters-per-user", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.users <= 10000 or not 1 <= args.letters_per_user <= 20:
        parser.error("users must be 1..10000 and letters-per-user must be 1..20")
    asyncio.run(seed(args.users, args.letters_per_user))


if __name__ == "__main__":
    main()
