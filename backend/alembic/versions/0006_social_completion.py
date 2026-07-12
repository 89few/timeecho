"""complete social graph, notifications and friend direct messages

Revision ID: 0006_social_completion
Revises: 0005_profile_bio
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_social_completion"
down_revision = "0005_profile_bio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chat_rooms",
        "letter_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "chat_rooms",
        "expired_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column(
        "chat_rooms",
        sa.Column("friend_pair_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "chat_rooms",
        sa.Column(
            "room_kind",
            sa.String(length=16),
            nullable=False,
            server_default="TEMPORARY",
        ),
    )
    op.create_index(
        "ix_chat_rooms_friend_pair_key", "chat_rooms", ["friend_pair_key"]
    )
    op.create_index("ix_chat_rooms_room_kind", "chat_rooms", ["room_kind"])
    op.create_unique_constraint(
        "uq_chat_room_friend_pair_key", "chat_rooms", ["friend_pair_key"]
    )
    op.alter_column("chat_rooms", "room_kind", server_default=None)

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "type IN ('FRIEND_REQUEST', 'FRIEND_ACCEPTED', 'FRIEND_REJECTED', 'POST_LIKE', 'POST_COMMENT')",
            name="ck_user_notification_type",
        ),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_actor_id", "user_notifications", ["actor_id"])
    op.create_index("ix_user_notifications_type", "user_notifications", ["type"])
    op.create_index("ix_user_notifications_is_read", "user_notifications", ["is_read"])
    op.create_index("ix_user_notifications_created_at", "user_notifications", ["created_at"])


def downgrade() -> None:
    # FRIEND rooms have no letter or expiry by design.  Remove only those
    # v6-specific conversations before restoring the pre-v6 NOT NULL shape;
    # temporary paper-plane rooms and their messages remain untouched.
    op.execute(
        "DELETE FROM chat_messages WHERE room_id IN "
        "(SELECT id FROM chat_rooms WHERE room_kind = 'FRIEND')"
    )
    op.execute("DELETE FROM chat_rooms WHERE room_kind = 'FRIEND'")

    op.drop_index("ix_user_notifications_created_at", table_name="user_notifications")
    op.drop_index("ix_user_notifications_is_read", table_name="user_notifications")
    op.drop_index("ix_user_notifications_type", table_name="user_notifications")
    op.drop_index("ix_user_notifications_actor_id", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")

    op.drop_constraint("uq_chat_room_friend_pair_key", "chat_rooms", type_="unique")
    op.drop_index("ix_chat_rooms_room_kind", table_name="chat_rooms")
    op.drop_index("ix_chat_rooms_friend_pair_key", table_name="chat_rooms")
    op.drop_column("chat_rooms", "room_kind")
    op.drop_column("chat_rooms", "friend_pair_key")
    op.alter_column(
        "chat_rooms",
        "expired_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "chat_rooms",
        "letter_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
