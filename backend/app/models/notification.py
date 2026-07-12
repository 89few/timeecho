from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationType(str, enum.Enum):
    FRIEND_REQUEST = "FRIEND_REQUEST"
    FRIEND_ACCEPTED = "FRIEND_ACCEPTED"
    FRIEND_REJECTED = "FRIEND_REJECTED"
    POST_LIKE = "POST_LIKE"
    POST_COMMENT = "POST_COMMENT"
    CARD_EXCHANGE = "CARD_EXCHANGE"
    SYSTEM = "SYSTEM"


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, native_enum=False), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
