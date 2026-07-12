"""temporary password flag

Revision ID: 0014_temporary_password
Revises: 0013_moderation_evidence
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_temporary_password"
down_revision = "0013_moderation_evidence"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False))

def downgrade() -> None:
    op.drop_column("users", "must_change_password")
