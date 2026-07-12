"""relationship anonymous identities and online matching

Revision ID: 0007_anonymous_matching
Revises: 0006_social_completion
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_anonymous_matching"
down_revision = "0006_social_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_user_notification_type", "user_notifications", type_="check")
    op.create_check_constraint(
        "ck_user_notification_type",
        "user_notifications",
        "type IN ('FRIEND_REQUEST', 'FRIEND_ACCEPTED', 'FRIEND_REJECTED', 'POST_LIKE', 'POST_COMMENT', 'CARD_EXCHANGE')",
    )
    op.create_table(
        "anonymous_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("anonymous_name", sa.String(32), nullable=False),
        sa.Column("avatar_url", sa.String(255), nullable=False),
        sa.Column("card_consented", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        sa.Column("revealed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("scope_type", "scope_id", "user_id", name="uq_anonymous_identity_scope_user"),
    )
    for column in ("scope_type", "scope_id", "user_id"):
        op.create_index(f"ix_anonymous_identities_{column}", "anonymous_identities", [column])

    op.create_table(
        "user_match_states",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="IDLE"),
        sa.Column("purpose", sa.String(24)),
        sa.Column("topic", sa.String(24)),
        sa.Column("room_id", sa.Integer()),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="SET NULL"),
    )
    for column in ("status", "room_id", "queued_at", "heartbeat_at"):
        op.create_index(f"ix_user_match_states_{column}", "user_match_states", [column])

    op.create_table(
        "anonymous_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("ended_reason", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_anonymous_matches_room_id", "anonymous_matches", ["room_id"], unique=True)
    op.create_index("ix_anonymous_matches_status", "anonymous_matches", ["status"])

    op.create_table(
        "match_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("topic", sa.String(24), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["match_id"], ["anonymous_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("match_id", "user_id", name="uq_match_participant_user"),
    )
    op.create_index("ix_match_participants_match_id", "match_participants", ["match_id"])
    op.create_index("ix_match_participants_user_id", "match_participants", ["user_id"])

    op.create_table(
        "match_exclusions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("excluded_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["excluded_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "excluded_user_id", "kind", name="uq_match_exclusion_kind"),
    )
    for column in ("owner_id", "excluded_user_id", "kind"):
        op.create_index(f"ix_match_exclusions_{column}", "match_exclusions", [column])

    op.create_table(
        "recent_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_low_id", sa.Integer(), nullable=False),
        sa.Column("user_high_id", sa.Integer(), nullable=False),
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["user_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_recent_match_pair"),
    )
    for column in ("user_low_id", "user_high_id", "last_matched_at"):
        op.create_index(f"ix_recent_matches_{column}", "recent_matches", [column])


def downgrade() -> None:
    op.execute("DELETE FROM user_notifications WHERE type = 'CARD_EXCHANGE'")
    op.drop_constraint("ck_user_notification_type", "user_notifications", type_="check")
    op.create_check_constraint(
        "ck_user_notification_type",
        "user_notifications",
        "type IN ('FRIEND_REQUEST', 'FRIEND_ACCEPTED', 'FRIEND_REJECTED', 'POST_LIKE', 'POST_COMMENT')",
    )
    op.drop_table("recent_matches")
    op.drop_table("match_exclusions")
    op.drop_table("match_participants")
    op.drop_table("anonymous_matches")
    op.drop_table("user_match_states")
    op.drop_table("anonymous_identities")
