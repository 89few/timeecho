from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatRoomStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DESTROYED = "DESTROYED"
    EXPIRED = "EXPIRED"


class ChatRoomKind(str, enum.Enum):
    TEMPORARY = "TEMPORARY"
    FRIEND = "FRIEND"
    MATCH = "MATCH"


class ChatRoom(Base):
    __tablename__ = "chat_rooms"
    __table_args__ = (
        UniqueConstraint("letter_id", name="uq_chat_room_letter_id"),
        UniqueConstraint("friend_pair_key", name="uq_chat_room_friend_pair_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    letter_id: Mapped[int | None] = mapped_column(
        ForeignKey("letters.id"), index=True, nullable=True
    )
    friend_pair_key: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    room_kind: Mapped[ChatRoomKind] = mapped_column(
        Enum(ChatRoomKind, native_enum=False),
        default=ChatRoomKind.TEMPORARY,
        index=True,
        nullable=False,
    )
    user_a_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    user_b_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    status: Mapped[ChatRoomStatus] = mapped_column(
        Enum(ChatRoomStatus, native_enum=False),
        default=ChatRoomStatus.ACTIVE,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    destroyed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "sender_id",
            "client_message_id",
            name="uq_chat_message_client_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("chat_rooms.id"), index=True, nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    client_message_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    content_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    content_key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    message_kind: Mapped[str] = mapped_column(
        String(16), default="text", nullable=False
    )
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_flag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AnonymousIdentity(Base):
    __tablename__ = "anonymous_identities"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "user_id", name="uq_anonymous_identity_scope_user"),
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "anonymous_name",
            "avatar_url",
            name="uq_anonymous_identity_scope_appearance",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    anonymous_name: Mapped[str] = mapped_column(String(32), nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(255), nullable=False)
    card_consented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MatchStateStatus(str, enum.Enum):
    IDLE = "IDLE"
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"


class UserMatchState(Base):
    __tablename__ = "user_match_states"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[MatchStateStatus] = mapped_column(
        Enum(MatchStateStatus, native_enum=False), default=MatchStateStatus.IDLE, index=True, nullable=False
    )
    purpose: Mapped[str | None] = mapped_column(String(24), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(24), nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("chat_rooms.id", ondelete="SET NULL"), index=True, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)


class AnonymousMatch(Base):
    __tablename__ = "anonymous_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True, nullable=False)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (UniqueConstraint("match_id", "user_id", name="uq_match_participant_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("anonymous_matches.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    topic: Mapped[str] = mapped_column(String(24), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MatchExclusion(Base):
    __tablename__ = "match_exclusions"
    __table_args__ = (
        UniqueConstraint("owner_id", "excluded_user_id", "kind", name="uq_match_exclusion_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    excluded_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecentMatch(Base):
    __tablename__ = "recent_matches"
    __table_args__ = (UniqueConstraint("user_low_id", "user_high_id", name="uq_recent_match_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_low_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    user_high_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    last_matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("owner_id", "blocked_user_id", name="uq_user_block_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    blocked_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_rooms.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
