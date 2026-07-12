from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FriendRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class PostVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    FRIENDS = "FRIENDS"
    PRIVATE = "PRIVATE"


class FriendRequest(Base, TimestampMixin):
    __tablename__ = "friend_requests"
    __table_args__ = (
        UniqueConstraint("pair_low_id", "pair_high_id", name="uq_friend_request_pair"),
        CheckConstraint("requester_id <> addressee_id", name="ck_friend_request_not_self"),
        CheckConstraint("pair_low_id < pair_high_id", name="ck_friend_request_sorted_pair"),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_friend_request_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # A canonical pair is stored in addition to the direction so simultaneous
    # cross-requests cannot create two pending rows for the same people.
    pair_low_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pair_high_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[FriendRequestStatus] = mapped_column(
        Enum(FriendRequestStatus, native_enum=False),
        default=FriendRequestStatus.PENDING,
        index=True,
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(String(120), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_low_id", "user_high_id", name="uq_friendship_pair"),
        CheckConstraint("user_low_id < user_high_id", name="ck_friendship_sorted_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_low_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    user_high_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FriendRemark(Base, TimestampMixin):
    __tablename__ = "friend_remarks"
    __table_args__ = (
        UniqueConstraint("owner_id", "friend_id", name="uq_friend_remark_pair"),
        CheckConstraint("owner_id <> friend_id", name="ck_friend_remark_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    friend_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    remark: Mapped[str] = mapped_column(String(40), nullable=False)


class SocialPost(Base, TimestampMixin):
    __tablename__ = "social_posts"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('PUBLIC', 'FRIENDS', 'PRIVATE')",
            name="ck_social_post_visibility",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[PostVisibility] = mapped_column(
        Enum(PostVisibility, native_enum=False),
        default=PostVisibility.PUBLIC,
        index=True,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)


class PostMedia(Base):
    __tablename__ = "post_media"
    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video', 'audio')", name="ck_post_media_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("social_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("social_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostComment(Base, TimestampMixin):
    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("social_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("post_comments.id", ondelete="CASCADE"), index=True, nullable=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
