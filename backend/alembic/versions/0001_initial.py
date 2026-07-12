"""initial explicit schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("phone_hash", sa.String(length=128), nullable=False),
        sa.Column("phone_ciphertext", sa.Text(), nullable=False),
        sa.Column("anonymous_name", sa.String(length=32), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("emotion", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("phone_hash", name="uq_users_phone_hash"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_phone_hash", "users", ["phone_hash"])

    op.create_table(
        "letters",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("content_ciphertext", sa.Text(), nullable=False),
        sa.Column("content_plain_for_dev", sa.Text(), nullable=True),
        sa.Column("emotion", sa.String(length=32), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("seal_days", sa.Integer(), nullable=True),
        sa.Column("release_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salvaged_by", sa.Integer(), nullable=True),
        sa.Column("salvaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroy_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["salvaged_by"], ["users.id"]),
    )
    for col in ["id", "author_id", "emotion", "city", "status", "release_at", "salvaged_by", "destroy_at", "risk_level"]:
        op.create_index(f"ix_letters_{col}", "letters", [col])

    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("letter_id", sa.Integer(), nullable=False),
        sa.Column("user_a_id", sa.Integer(), nullable=False),
        sa.Column("user_b_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["letter_id"], ["letters.id"]),
        sa.ForeignKeyConstraint(["user_a_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_b_id"], ["users.id"]),
        sa.UniqueConstraint("letter_id", name="uq_chat_room_letter_id"),
    )
    for col in ["id", "letter_id", "user_a_id", "user_b_id", "status", "expired_at"]:
        op.create_index(f"ix_chat_rooms_{col}", "chat_rooms", [col])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("content_ciphertext", sa.Text(), nullable=False),
        sa.Column("content_plain_for_dev", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("risk_flag", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
    )
    for col in ["id", "room_id", "sender_id"]:
        op.create_index(f"ix_chat_messages_{col}", "chat_messages", [col])

    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("letter_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["letter_id"], ["letters.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"]),
    )
    for col in ["id", "reporter_id", "target_user_id", "letter_id", "room_id", "message_id", "status"]:
        op.create_index(f"ix_complaints_{col}", "complaints", [col])

    op.create_table(
        "punishments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_punishments_id", "punishments", ["id"])
    op.create_index("ix_punishments_user_id", "punishments", ["user_id"])
    op.create_index("ix_punishments_type", "punishments", ["type"])

    op.create_table(
        "sensitive_words",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("word", name="uq_sensitive_words_word"),
    )
    op.create_index("ix_sensitive_words_id", "sensitive_words", ["id"])
    op.create_index("ix_sensitive_words_word", "sensitive_words", ["word"])

    op.create_table(
        "system_configs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("config_key", name="uq_system_configs_config_key"),
    )
    op.create_index("ix_system_configs_id", "system_configs", ["id"])
    op.create_index("ix_system_configs_config_key", "system_configs", ["config_key"])


def downgrade() -> None:
    op.drop_index("ix_system_configs_config_key", table_name="system_configs")
    op.drop_index("ix_system_configs_id", table_name="system_configs")
    op.drop_table("system_configs")

    op.drop_index("ix_sensitive_words_word", table_name="sensitive_words")
    op.drop_index("ix_sensitive_words_id", table_name="sensitive_words")
    op.drop_table("sensitive_words")

    op.drop_index("ix_punishments_type", table_name="punishments")
    op.drop_index("ix_punishments_user_id", table_name="punishments")
    op.drop_index("ix_punishments_id", table_name="punishments")
    op.drop_table("punishments")

    for col in ["status", "message_id", "room_id", "letter_id", "target_user_id", "reporter_id", "id"]:
        op.drop_index(f"ix_complaints_{col}", table_name="complaints")
    op.drop_table("complaints")

    for col in ["sender_id", "room_id", "id"]:
        op.drop_index(f"ix_chat_messages_{col}", table_name="chat_messages")
    op.drop_table("chat_messages")

    for col in ["expired_at", "status", "user_b_id", "user_a_id", "letter_id", "id"]:
        op.drop_index(f"ix_chat_rooms_{col}", table_name="chat_rooms")
    op.drop_table("chat_rooms")

    for col in ["risk_level", "destroy_at", "salvaged_by", "release_at", "status", "city", "emotion", "author_id", "id"]:
        op.drop_index(f"ix_letters_{col}", table_name="letters")
    op.drop_table("letters")

    op.drop_index("ix_users_phone_hash", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
