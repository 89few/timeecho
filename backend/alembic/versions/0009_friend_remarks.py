"""friend remarks

Revision ID: 0009_friend_remarks
Revises: 0008_hardening
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_friend_remarks"
down_revision = "0008_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friend_remarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("friend_id", sa.Integer(), nullable=False),
        sa.Column("remark", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["friend_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "friend_id", name="uq_friend_remark_pair"),
        sa.CheckConstraint("owner_id <> friend_id", name="ck_friend_remark_not_self"),
    )
    op.create_index("ix_friend_remarks_owner_id", "friend_remarks", ["owner_id"])
    op.create_index("ix_friend_remarks_friend_id", "friend_remarks", ["friend_id"])


def downgrade() -> None:
    op.drop_table("friend_remarks")
