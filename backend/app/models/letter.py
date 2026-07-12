from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LetterStatus(str, enum.Enum):
    SEALED = "SEALED"
    AVAILABLE = "AVAILABLE"
    SALVAGED = "SALVAGED"
    RISK_REVIEW = "RISK_REVIEW"
    DESTROYED = "DESTROYED"


class RiskLevel(str, enum.Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Letter(Base, TimestampMixin):
    __tablename__ = "letters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    content_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    content_key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    emotion: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    city: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[LetterStatus] = mapped_column(Enum(LetterStatus, native_enum=False), default=LetterStatus.SEALED, index=True, nullable=False)
    seal_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    salvaged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    salvaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    destroy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, native_enum=False), default=RiskLevel.NONE, index=True, nullable=False)
