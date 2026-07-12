from __future__ import annotations

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.chat import UserBlock
from app.models.social import FriendRemark, FriendRequest, Friendship


async def is_blocked_between(db: AsyncSession, first_id: int, second_id: int) -> bool:
    if first_id == second_id:
        return False
    return (
        await db.scalar(
            select(UserBlock.id).where(
                or_(
                    and_(
                        UserBlock.owner_id == first_id,
                        UserBlock.blocked_user_id == second_id,
                    ),
                    and_(
                        UserBlock.owner_id == second_id,
                        UserBlock.blocked_user_id == first_id,
                    ),
                )
            )
        )
        is not None
    )


async def blocked_user_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = list(
        (
            await db.execute(
                select(UserBlock).where(
                    or_(
                        UserBlock.owner_id == user_id,
                        UserBlock.blocked_user_id == user_id,
                    )
                )
            )
        ).scalars().all()
    )
    return {
        row.blocked_user_id if row.owner_id == user_id else row.owner_id
        for row in rows
    }


async def ensure_not_blocked(
    db: AsyncSession, first_id: int, second_id: int
) -> None:
    if await is_blocked_between(db, first_id, second_id):
        raise AppException("USER_BLOCKED", "你们之间已存在拉黑关系", 403)


async def create_global_block(
    db: AsyncSession,
    owner_id: int,
    blocked_user_id: int,
    *,
    source_room_id: int | None = None,
    commit: bool = True,
) -> UserBlock:
    if owner_id == blocked_user_id:
        raise AppException("CANNOT_BLOCK_SELF", "不能拉黑自己", 400)
    block = await db.scalar(
        select(UserBlock).where(
            UserBlock.owner_id == owner_id,
            UserBlock.blocked_user_id == blocked_user_id,
        )
    )
    if block is None:
        block = UserBlock(
            owner_id=owner_id,
            blocked_user_id=blocked_user_id,
            source_room_id=source_room_id,
            created_at=utcnow(),
        )
        db.add(block)
    low, high = sorted((owner_id, blocked_user_id))
    await db.execute(
        delete(Friendship).where(
            Friendship.user_low_id == low,
            Friendship.user_high_id == high,
        )
    )
    await db.execute(
        delete(FriendRequest).where(
            or_(
                and_(
                    FriendRequest.requester_id == owner_id,
                    FriendRequest.addressee_id == blocked_user_id,
                ),
                and_(
                    FriendRequest.requester_id == blocked_user_id,
                    FriendRequest.addressee_id == owner_id,
                ),
            )
        )
    )
    await db.execute(
        delete(FriendRemark).where(
            or_(
                and_(
                    FriendRemark.owner_id == owner_id,
                    FriendRemark.friend_id == blocked_user_id,
                ),
                and_(
                    FriendRemark.owner_id == blocked_user_id,
                    FriendRemark.friend_id == owner_id,
                ),
            )
        )
    )
    if commit:
        await db.commit()
        await db.refresh(block)
    else:
        await db.flush()
    return block
