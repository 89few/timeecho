from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SensitiveWord(Base):
    __tablename__ = "sensitive_words"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
