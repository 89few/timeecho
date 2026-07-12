from __future__ import annotations

import json

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.notification import NotificationType, UserNotification
from app.models.user import User


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    actor_id: int | None = None,
    data: dict | None = None,
    commit: bool = True,
) -> UserNotification:
    notification = UserNotification(
        user_id=user_id,
        actor_id=actor_id,
        type=notification_type,
        title=title,
        message=message,
        data_json=json.dumps(data, ensure_ascii=False) if data else None,
        is_read=False,
        created_at=utcnow(),
    )
    db.add(notification)
    if commit:
        await db.commit()
        await db.refresh(notification)
    else:
        await db.flush()
    return notification


def _decode_data(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


async def notification_payload(
    db: AsyncSession,
    notification: UserNotification,
    actor: User | None = None,
) -> dict:
    if actor is None and notification.actor_id:
        actor = await db.get(User, notification.actor_id)
    return {
        "id": notification.id,
        "type": notification.type.value,
        "title": notification.title,
        "message": notification.message,
        "data": _decode_data(notification.data_json),
        "is_read": notification.is_read,
        "created_at": notification.created_at,
        "actor": {
            "id": actor.id,
            "uid": actor.uid,
            "display_name": actor.username or actor.anonymous_name,
            "username": actor.username,
            "avatar_url": actor.avatar_url,
            "bio": actor.bio,
        }
        if actor
        else None,
    }


async def list_notifications(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    unread_only: bool = False,
) -> dict:
    stmt = select(UserNotification).where(UserNotification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(UserNotification.is_read.is_(False))
    stmt = (
        stmt.order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    actor_ids = {row.actor_id for row in rows if row.actor_id}
    actors = (
        {
            actor.id: actor
            for actor in (
                await db.execute(select(User).where(User.id.in_(actor_ids)))
            ).scalars().all()
        }
        if actor_ids
        else {}
    )
    return {
        "items": [
            await notification_payload(db, row, actors.get(row.actor_id))
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }


async def unread_notification_count(db: AsyncSession, user_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count(UserNotification.id)).where(
                UserNotification.user_id == user_id,
                UserNotification.is_read.is_(False),
            )
        )
        or 0
    )


async def mark_notification_read(
    db: AsyncSession, user_id: int, notification_id: int
) -> None:
    notification = await db.get(UserNotification, notification_id)
    if not notification or notification.user_id != user_id:
        raise AppException("NOTIFICATION_NOT_FOUND", "通知不存在", 404)
    if not notification.is_read:
        notification.is_read = True
        await db.commit()


async def mark_all_notifications_read(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        update(UserNotification)
        .where(
            UserNotification.user_id == user_id,
            UserNotification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return int(result.rowcount or 0)
