"""add email and password authentication fields

Revision ID: 0003_email_auth
Revises: 0002_chat_media
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_email_auth"
down_revision = "0002_chat_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "phone_hash", existing_type=sa.String(length=128), nullable=True)
    op.alter_column("users", "phone_ciphertext", existing_type=sa.Text(), nullable=True)
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.execute(
        sa.text(
            "UPDATE users SET avatar_url = '/static/assets/avatars/avatar-' || "
            "(((id - 1) % 6) + 1) || '.png' WHERE avatar_url IS NULL"
        )
    )
    op.alter_column("users", "email_verified", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
    op.drop_column("users", "email")

    # Email-only accounts have no legacy phone value.  Give them deterministic
    # downgrade placeholders before restoring the old NOT NULL contract.
    op.execute(sa.text("UPDATE users SET phone_hash = 'email-only-' || id WHERE phone_hash IS NULL"))
    op.execute(sa.text("UPDATE users SET phone_ciphertext = '' WHERE phone_ciphertext IS NULL"))
    op.alter_column("users", "phone_ciphertext", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "phone_hash", existing_type=sa.String(length=128), nullable=False)
