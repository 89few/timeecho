"""moderation evidence and appeal state

Revision ID: 0013_moderation_evidence
Revises: 0012_private_media
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_moderation_evidence"
down_revision = "0012_private_media"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("complaints", sa.Column("review_note", sa.Text()))
    op.add_column("complaints", sa.Column("evidence_ciphertext", sa.Text()))
    op.add_column("complaints", sa.Column("evidence_key_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("punishments", sa.Column("appeal_status", sa.String(24), server_default="NONE", nullable=False))
    op.add_column("punishments", sa.Column("review_note", sa.Text()))

def downgrade() -> None:
    op.drop_column("punishments", "review_note")
    op.drop_column("punishments", "appeal_status")
    op.drop_column("complaints", "evidence_key_version")
    op.drop_column("complaints", "evidence_ciphertext")
    op.drop_column("complaints", "review_note")
