"""Add media_urls JSONB column to tweets table.

Revision ID: 056
Revises: 055
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tweets",
        sa.Column("media_urls", JSONB, server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tweets", "media_urls")
