from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PunishmentType(str, enum.Enum):
    MUTE = "MUTE"
    BAN = "BAN"
    CONTENT_REMOVAL = "CONTENT_REMOVAL"


class Punishment(Base):
    __tablename__ = "punishments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    type: Mapped[PunishmentType] = mapped_column(Enum(PunishmentType, native_enum=False), index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    appeal_status: Mapped[str] = mapped_column(String(24), default="NONE", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
