"""add friends and social feed

Revision ID: 0004_social
Revises: 0003_email_auth
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_social"
down_revision = "0003_email_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friend_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("addressee_id", sa.Integer(), nullable=False),
        sa.Column("pair_low_id", sa.Integer(), nullable=False),
        sa.Column("pair_high_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("message", sa.String(length=120), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["addressee_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pair_low_id", "pair_high_id", name="uq_friend_request_pair"),
        sa.CheckConstraint("requester_id <> addressee_id", name="ck_friend_request_not_self"),
        sa.CheckConstraint("pair_low_id < pair_high_id", name="ck_friend_request_sorted_pair"),
        sa.CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'REJECTED')", name="ck_friend_request_status"),
    )
    op.create_index("ix_friend_requests_requester_id", "friend_requests", ["requester_id"])
    op.create_index("ix_friend_requests_addressee_id", "friend_requests", ["addressee_id"])
    op.create_index("ix_friend_requests_status", "friend_requests", ["status"])

    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_low_id", sa.Integer(), nullable=False),
        sa.Column("user_high_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_friendship_pair"),
        sa.CheckConstraint("user_low_id < user_high_id", name="ck_friendship_sorted_pair"),
    )
    op.create_index("ix_friendships_user_low_id", "friendships", ["user_low_id"])
    op.create_index("ix_friendships_user_high_id", "friendships", ["user_high_id"])

    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="FRIENDS"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("visibility IN ('PUBLIC', 'FRIENDS', 'PRIVATE')", name="ck_social_post_visibility"),
    )
    op.create_index("ix_social_posts_author_id", "social_posts", ["author_id"])
    op.create_index("ix_social_posts_visibility", "social_posts", ["visibility"])
    op.create_index("ix_social_posts_deleted_at", "social_posts", ["deleted_at"])
    op.create_index("ix_social_posts_created_at", "social_posts", ["created_at"])

    op.create_table(
        "post_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('image', 'video', 'audio')", name="ck_post_media_kind"),
    )
    op.create_index("ix_post_media_post_id", "post_media", ["post_id"])

    op.create_table(
        "post_likes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("post_id", "user_id", name="uq_post_like_user"),
    )
    op.create_index("ix_post_likes_post_id", "post_likes", ["post_id"])
    op.create_index("ix_post_likes_user_id", "post_likes", ["user_id"])

    op.create_table(
        "post_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("parent_comment_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_comment_id"], ["post_comments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_post_comments_post_id", "post_comments", ["post_id"])
    op.create_index("ix_post_comments_author_id", "post_comments", ["author_id"])
    op.create_index("ix_post_comments_parent_comment_id", "post_comments", ["parent_comment_id"])
    op.create_index("ix_post_comments_deleted_at", "post_comments", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("post_comments")
    op.drop_table("post_likes")
    op.drop_table("post_media")
    op.drop_table("social_posts")
    op.drop_table("friendships")
    op.drop_table("friend_requests")
