"""authenticated private media

Revision ID: 0012_private_media
Revises: 0011_security_sessions
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_private_media"
down_revision = "0011_security_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "private_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_private_media_public_id", "private_media", ["public_id"], unique=True)
    op.create_index("ix_private_media_owner_id", "private_media", ["owner_id"])
    op.create_unique_constraint("uq_private_media_storage_name", "private_media", ["storage_name"])


def downgrade() -> None:
    op.drop_table("private_media")
