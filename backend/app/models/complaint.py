from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ComplaintStatus(str, enum.Enum):
    PENDING = "PENDING"
    HANDLED = "HANDLED"
    REJECTED = "REJECTED"


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    letter_id: Mapped[int | None] = mapped_column(ForeignKey("letters.id"), index=True, nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("chat_rooms.id"), index=True, nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id"), index=True, nullable=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ComplaintStatus] = mapped_column(Enum(ComplaintStatus, native_enum=False), default=ComplaintStatus.PENDING, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
