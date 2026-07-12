from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import ok
from app.models.user import User
from app.services.notification_service import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    unread_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_notifications(db, user.id, page, page_size, unread_only))


@router.get("/unread-count")
async def notification_unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok({"count": await unread_notification_count(db, user.id)})


@router.post("/read-all")
async def read_all_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await mark_all_notifications_read(db, user.id)
    return ok({"count": count}, "全部已读")


@router.post("/{notification_id}/read")
async def read_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_notification_read(db, user.id, notification_id)
    return ok({"notification_id": notification_id}, "已读")
