"""add public profile biography

Revision ID: 0005_profile_bio
Revises: 0004_social
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_profile_bio"
down_revision = "0004_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bio")
