"""persist chat media metadata

Revision ID: 0002_chat_media
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_chat_media"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("message_kind", sa.String(length=16), nullable=False, server_default="text"))
    op.add_column("chat_messages", sa.Column("media_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "media_url")
    op.drop_column("chat_messages", "message_kind")
