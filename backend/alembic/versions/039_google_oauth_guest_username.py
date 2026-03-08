"""Add Google OAuth, guest login, and username columns to users table.

Revision ID: 039
Revises: 038
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make password_hash nullable (Google/guest users have no password)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)

    # Add new columns
    op.add_column("users", sa.Column("username", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(20), nullable=False, server_default="local"),
    )
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))

    # Create unique indexes
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    # Backfill existing users: username from email prefix (part before @)
    op.execute(
        """
        UPDATE users
        SET username = LOWER(SPLIT_PART(email, '@', 1))
        WHERE username IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "google_id")
    op.drop_column("users", "username")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
