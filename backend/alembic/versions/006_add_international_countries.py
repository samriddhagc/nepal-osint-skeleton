"""Add international_countries to story_features

Revision ID: 006
Revises: 005
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add international_countries column to story_features
    op.add_column(
        "story_features",
        sa.Column(
            "international_countries",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="International countries/cities mentioned",
        ),
    )


def downgrade() -> None:
    op.drop_column("story_features", "international_countries")
