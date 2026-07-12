"""global blocks, idempotent messages, and anonymous appearance uniqueness

Revision ID: 0008_hardening
Revises: 0007_anonymous_matching
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_hardening"
down_revision = "0007_anonymous_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("client_message_id", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_chat_message_client_id",
        "chat_messages",
        ["room_id", "sender_id", "client_message_id"],
    )
    op.create_unique_constraint(
        "uq_anonymous_identity_scope_appearance",
        "anonymous_identities",
        ["scope_type", "scope_id", "anonymous_name", "avatar_url"],
    )
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("blocked_user_id", sa.Integer(), nullable=False),
        sa.Column("source_room_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["blocked_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_room_id"], ["chat_rooms.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("owner_id", "blocked_user_id", name="uq_user_block_pair"),
    )
    op.create_index("ix_user_blocks_owner_id", "user_blocks", ["owner_id"])
    op.create_index(
        "ix_user_blocks_blocked_user_id", "user_blocks", ["blocked_user_id"]
    )


def downgrade() -> None:
    op.drop_table("user_blocks")
    op.drop_constraint(
        "uq_anonymous_identity_scope_appearance",
        "anonymous_identities",
        type_="unique",
    )
    op.drop_constraint(
        "uq_chat_message_client_id", "chat_messages", type_="unique"
    )
    op.drop_column("chat_messages", "client_message_id")
