from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import ok
from app.models.social import FriendRequestStatus
from app.models.user import User
from app.services.chat_service import list_chat_rooms_for_user
from app.services.notification_service import list_notifications
from app.services.social_service import list_friend_requests


router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/messages")
async def messages_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the complete messages-tab snapshot in one internet round trip."""
    rooms = await list_chat_rooms_for_user(db, user.id)
    notifications = await list_notifications(db, user.id, 1, 50, False)
    requests = await list_friend_requests(
        db, user, "incoming", FriendRequestStatus.PENDING, 1, 20
    )
    return ok(
        {
            "rooms": rooms,
            "notifications": notifications["items"],
            "friend_requests": requests["items"],
        }
    )
