"""security sessions, admin RBAC, audit and ciphertext versions

Revision ID: 0011_security_sessions
Revises: 0010_user_uid
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_security_sessions"
down_revision = "0010_user_uid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mfa_secret_ciphertext", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)
    op.create_index("ix_admin_users_role", "admin_users", ["role"])
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=True)
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_index("ix_admin_sessions_revoked_at", "admin_sessions", ["revoked_at"])
    op.create_table(
        "admin_login_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(64)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_login_logs_admin_id", "admin_login_logs", ["admin_id"])
    op.create_index("ix_admin_login_logs_username", "admin_login_logs", ["username"])
    op.create_index("ix_admin_login_logs_success", "admin_login_logs", ["success"])
    op.create_index("ix_admin_login_logs_created_at", "admin_login_logs", ["created_at"])
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(96), nullable=False),
        sa.Column("target_type", sa.String(64)), sa.Column("target_id", sa.String(64)),
        sa.Column("before_json", sa.Text()), sa.Column("after_json", sa.Text()), sa.Column("reason", sa.Text()),
        sa.Column("ip_address", sa.String(64)), sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_logs_admin_id", "admin_audit_logs", ["admin_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_target_type", "admin_audit_logs", ["target_type"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_jti_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_refresh_jti_hash", "user_sessions", ["refresh_jti_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])
    op.add_column("letters", sa.Column("content_key_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("chat_messages", sa.Column("content_key_version", sa.Integer(), server_default="1", nullable=False))
    op.drop_column("letters", "content_plain_for_dev")
    op.drop_column("chat_messages", "content_plain_for_dev")


def downgrade() -> None:
    op.add_column("chat_messages", sa.Column("content_plain_for_dev", sa.Text()))
    op.add_column("letters", sa.Column("content_plain_for_dev", sa.Text()))
    op.drop_column("chat_messages", "content_key_version")
    op.drop_column("letters", "content_key_version")
    for table in ("user_sessions", "admin_audit_logs", "admin_login_logs", "admin_sessions", "admin_users"):
        op.drop_table(table)
