from __future__ import annotations

import asyncio
import json
import sys
from secrets import token_urlsafe
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.core.crypto import encrypt_text
from app.core.config import settings
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal, redis_client
from app.models.chat import ChatMessage, ChatRoom, ChatRoomKind, ChatRoomStatus
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.notification import NotificationType, UserNotification
from app.models.social import (
    FriendRequest,
    FriendRequestStatus,
    Friendship,
    PostComment,
    PostLike,
    PostMedia,
    PostVisibility,
    SocialPost,
)
from app.models.user import User, UserStatus
from app.services.auth_service import hash_password
from app.services.salvage_service import rebuild_available_letter_pools


PROFILES = [
    ("晚风手记", "杭州", "平静", "记录晚风、散步和偶尔落下的雨。"),
    ("山茶来信", "成都", "喜悦", "喜欢旧书店，也喜欢热腾腾的早餐。"),
    ("雨后薄荷", "上海", "疲惫", "慢慢生活，认真收藏普通日子。"),
    ("半格月光", "南京", "平静", "夜跑、电影和不赶时间的周末。"),
    ("沿江拾光", "武汉", "喜悦", "在城市里寻找安静的小路。"),
    ("纸上青禾", "广州", "焦虑", "愿每一次表达都被温柔接住。"),
    ("北岸星灯", "北京", "孤独", "听歌的时候，会记下一些小句子。"),
    ("橘子海岸", "厦门", "喜悦", "海风、落日，还有刚刚好的晴天。"),
    ("云边慢邮", "重庆", "疲惫", "不急着抵达，先看一看沿途。"),
    ("清晨回声", "西安", "平静", "早起的人，偶尔也会熬夜想事情。"),
]

POSTS = [
    ("傍晚绕着湖走了一圈，风里已经有一点夏天的味道。", "今天完成了拖了很久的小事，心里忽然轻了一点。"),
    ("巷口的山茶开了，路过的人都忍不住慢下来。", "早餐店阿姨多送了一颗煎蛋，普通的一天有了小惊喜。"),
    ("雨停以后开窗，空气像被重新洗过一遍。", "忙完才发现天已经黑了，给自己泡杯热茶再休息。"),
    ("重看了一部旧电影，有些台词过几年再听会变得不一样。", "月亮被云遮住一半，剩下的一半也很亮。"),
    ("沿江骑了很远，回程时刚好遇到晚霞。", "把手机放远一小时，安静地吃了一顿饭。"),
    ("有点慌张也没关系，先把眼前的一件事做好。", "收到很久没联系的朋友发来的问候，原来惦记一直都在。"),
    ("随机播放到一首旧歌，像突然打开了一扇记忆里的门。", "夜色很安静，希望此刻还没睡的人也能放松一点。"),
    ("海边的风很大，吹散了今天一半的烦恼。", "买到一袋很甜的橘子，想把好运也分一点出去。"),
    ("山城的台阶走得很累，但拐角总有新的风景。", "允许今天效率不高，生活不是每一天都要交满分答卷。"),
    ("清晨的街道很空，第一班车载着各自的新一天。", "给未来写了一张明信片：别忘了现在认真生活的自己。"),
]

LETTERS = [
    "如果你刚好读到这封纸飞机，希望今天有一件小事让你微笑。",
    "最近学会了一件事：暂时没有答案，也可以先好好吃饭和睡觉。",
    "把没有说出口的疲惫放在这里。陌生的你，也请对自己温柔一点。",
    "今天路边的花开得很好，想把这份偶然遇见的明亮留给你。",
    "不是所有脚步都需要很快，慢一点也会到达想去的地方。",
    "愿你在很吵的世界里，仍有一个可以安心呼吸的小角落。",
    "有些低落会像天气一样过去，太阳没有消失，只是暂时在云后。",
    "认真生活的人值得被看见，哪怕今天只是完成了很普通的一天。",
    "当你觉得孤单时，请记得世界上也有人正望着同一片夜色。",
    "写给未来的某个清晨：醒来以后，继续相信会有新的故事。",
]

COMMENTS = ["这份心情我也有过。", "看到这里，今天也跟着明亮了一点。", "愿接下来的日子慢慢变好。", "很喜欢这样普通又温柔的瞬间。"]


async def seed() -> None:
    now = utcnow()
    async with AsyncSessionLocal() as db:
        users: list[User] = []
        for index, (name, city, emotion, bio) in enumerate(PROFILES, start=1):
            email = f"echo{index:02d}@timeecho.local"
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    username=name,
                    # Seeded community profiles are display-only. A random,
                    # unrecoverable credential prevents anyone from logging in
                    # with a password published in the source tree.
                    password_hash=hash_password(token_urlsafe(32)),
                    email_verified=True,
                    avatar_url=f"/static/assets/avatars/avatar-{((index - 1) % 6) + 1}.png",
                    bio=bio,
                    anonymous_name=f"回声{index:04d}",
                    city=city,
                    emotion=emotion,
                    status=UserStatus.ACTIVE,
                    last_login_at=now - timedelta(minutes=index * 37),
                )
                db.add(user)
                await db.flush()
            users.append(user)

        # Two natural-looking public moments per profile.
        for index, user in enumerate(users):
            for offset, text in enumerate(POSTS[index]):
                post = await db.scalar(
                    select(SocialPost).where(
                        SocialPost.author_id == user.id,
                        SocialPost.text == text,
                    )
                )
                if post is None:
                    created = now - timedelta(hours=(index * 3 + offset + 1))
                    post = SocialPost(
                        author_id=user.id,
                        text=text,
                        visibility=PostVisibility.PUBLIC,
                        created_at=created,
                        updated_at=created,
                    )
                    db.add(post)
                    await db.flush()
                    if (index + offset) % 3 == 0:
                        db.add(
                            PostMedia(
                                post_id=post.id,
                                kind="image",
                                url=f"/static/assets/avatars/avatar-{((index + offset) % 6) + 1}.png",
                                sort_order=0,
                                created_at=created,
                            )
                        )
                    liker = users[(index + 2 + offset) % len(users)]
                    commenter = users[(index + 4 + offset) % len(users)]
                    db.add(PostLike(post_id=post.id, user_id=liker.id, created_at=created + timedelta(minutes=8)))
                    db.add(
                        PostComment(
                            post_id=post.id,
                            author_id=commenter.id,
                            text=COMMENTS[(index + offset) % len(COMMENTS)],
                            created_at=created + timedelta(minutes=13),
                            updated_at=created + timedelta(minutes=13),
                        )
                    )

        # Three paper planes per profile: two available now, one still sealed.
        for index, user in enumerate(users):
            existing_count = int(await db.scalar(
                select(func.count(Letter.id)).where(Letter.author_id == user.id)
            ) or 0)
            for offset in range(existing_count, 3):
                content = LETTERS[(index + offset) % len(LETTERS)]
                sealed = offset == 2
                db.add(
                    Letter(
                        author_id=user.id,
                        content_ciphertext=encrypt_text(content),
                        content_key_version=settings.encryption_key_version,
                        emotion=PROFILES[index][2],
                        city=PROFILES[index][1],
                        status=LetterStatus.SEALED if sealed else LetterStatus.AVAILABLE,
                        seal_days=1 if sealed else 0,
                        release_at=now + timedelta(days=1) if sealed else now - timedelta(hours=index + offset + 1),
                        risk_level=RiskLevel.NONE,
                    )
                )

        # A friend ring gives every profile two contacts.
        for index, user in enumerate(users):
            other = users[(index + 1) % len(users)]
            low, high = sorted((user.id, other.id))
            exists = await db.scalar(
                select(Friendship.id).where(
                    Friendship.user_low_id == low,
                    Friendship.user_high_id == high,
                )
            )
            if not exists:
                db.add(Friendship(user_low_id=low, user_high_id=high, created_at=now - timedelta(days=index + 1)))

        # One unread friend request and its notification exercise the badge flow.
        requester, addressee = users[0], users[2]
        low, high = sorted((requester.id, addressee.id))
        request = await db.scalar(
            select(FriendRequest).where(
                FriendRequest.pair_low_id == low,
                FriendRequest.pair_high_id == high,
            )
        )
        if request is None:
            request = FriendRequest(
                requester_id=requester.id,
                addressee_id=addressee.id,
                pair_low_id=low,
                pair_high_id=high,
                status=FriendRequestStatus.PENDING,
                message="你好，看到你也喜欢散步，想认识一下。",
                created_at=now - timedelta(minutes=24),
                updated_at=now - timedelta(minutes=24),
            )
            db.add(request)
            await db.flush()
            db.add(
                UserNotification(
                    user_id=addressee.id,
                    actor_id=requester.id,
                    type=NotificationType.FRIEND_REQUEST,
                    title="新的好友申请",
                    message=f"{requester.username} 想添加你为好友",
                    data_json=json.dumps({"request_id": request.id, "actor_id": requester.id}),
                    is_read=False,
                    created_at=now - timedelta(minutes=24),
                )
            )

        await db.commit()

        # Five persistent friend conversations with realistic unread state.
        for index in range(5):
            first, second = users[index * 2], users[index * 2 + 1]
            low, high = sorted((first.id, second.id))
            pair_key = f"{low}:{high}"
            room = await db.scalar(select(ChatRoom).where(ChatRoom.friend_pair_key == pair_key))
            if room is None:
                room = ChatRoom(
                    letter_id=None,
                    friend_pair_key=pair_key,
                    room_kind=ChatRoomKind.FRIEND,
                    user_a_id=low,
                    user_b_id=high,
                    status=ChatRoomStatus.ACTIVE,
                    created_at=now - timedelta(hours=index + 2),
                    expired_at=None,
                )
                db.add(room)
                await db.flush()
            message_count = await db.scalar(
                select(func.count(ChatMessage.id)).where(ChatMessage.room_id == room.id)
            )
            if not message_count:
                lines = (
                    (first, "今天过得怎么样？", True),
                    (second, "还不错，刚刚散步回来。", True),
                    (first, "那就好，晚一点记得早点休息。", False),
                )
                for offset, (sender, text, is_read) in enumerate(lines):
                    created = now - timedelta(minutes=(18 - offset * 5 + index))
                    db.add(
                        ChatMessage(
                            room_id=room.id,
                            sender_id=sender.id,
                            content_ciphertext=encrypt_text(text),
                            content_key_version=settings.encryption_key_version,
                            message_kind="text",
                            is_read=is_read,
                            created_at=created,
                        )
                    )

        await db.commit()
        available = await rebuild_available_letter_pools(db, redis_client)
        counts = {
            "users": await db.scalar(select(func.count(User.id))),
            "letters": await db.scalar(select(func.count(Letter.id))),
            "posts": await db.scalar(select(func.count(SocialPost.id))),
            "friendships": await db.scalar(select(func.count(Friendship.id))),
            "rooms": await db.scalar(select(func.count(ChatRoom.id))),
            "notifications": await db.scalar(select(func.count(UserNotification.id))),
            "available_pool": available,
        }
        print("Community seed complete: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    asyncio.run(seed())
