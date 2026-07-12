"""immutable eight digit user uid

Revision ID: 0010_user_uid
Revises: 0009_friend_remarks
"""

from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa

revision = "0010_user_uid"
down_revision = "0009_friend_remarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("uid", sa.String(length=8), nullable=True))
    bind = op.get_bind()
    user_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM users")).fetchall()]
    used: set[str] = set()
    for user_id in user_ids:
        while True:
            uid = str(secrets.randbelow(90_000_000) + 10_000_000)
            if uid not in used:
                used.add(uid)
                break
        bind.execute(
            sa.text("UPDATE users SET uid = :uid WHERE id = :user_id"),
            {"uid": uid, "user_id": user_id},
        )
    op.alter_column("users", "uid", existing_type=sa.String(length=8), nullable=False)
    op.create_index("ix_users_uid", "users", ["uid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_uid", table_name="users")
    op.drop_column("users", "uid")
