"""Add users table for authentication.

Revision ID: 017
Revises: 016
Create Date: 2026-01-29

Creates tables for:
- users: User accounts with role-based access control
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_role enum type
    user_role_enum = postgresql.ENUM(
        "consumer", "analyst", "dev",
        name="user_role",
        create_type=False,
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    # If the table already exists (common in some dev setups), don't fail the entire migration chain.
    # Keep the migration idempotent so alembic can manage the rest of the schema.
    if inspect(op.get_bind()).has_table("users"):
        # Best-effort: add helpful indexes if missing.
        op.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users (is_active)")
        return

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM("consumer", "analyst", "dev", name="user_role", create_type=False),
            nullable=False,
            server_default="consumer",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    op.create_index("idx_users_role", "users", ["role"])
    op.create_index("idx_users_is_active", "users", ["is_active"])


def downgrade() -> None:
    op.drop_index("idx_users_is_active", "users")
    op.drop_index("idx_users_role", "users")
    op.drop_index("idx_users_email", "users")
    op.drop_table("users")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS user_role")
