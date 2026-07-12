from __future__ import annotations

import enum
import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MUTED = "MUTED"
    BANNED = "BANNED"
    DORMANT = "DORMANT"
    DEACTIVATED = "DEACTIVATED"


def generate_user_uid() -> str:
    """Generate a fixed-width public identifier; the database enforces uniqueness."""
    return str(secrets.randbelow(90_000_000) + 10_000_000)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(
        String(8), unique=True, index=True, nullable=False, default=generate_user_uid
    )
    # Phone login is kept for backwards compatibility.  New accounts may be
    # email-only, so the two legacy columns must be nullable.
    phone_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    phone_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(String(160), nullable=True)
    anonymous_name: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, native_enum=False), default=UserStatus.ACTIVE, index=True, nullable=False)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
