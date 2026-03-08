"""Add DFIMS relationship types: funds, implements.

Revision ID: 046
Revises: 045
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE relationship_type ADD VALUE IF NOT EXISTS 'funds'")
    op.execute("ALTER TYPE relationship_type ADD VALUE IF NOT EXISTS 'implements'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; requires recreating the type.
    # This is intentionally left as a no-op since the values are harmless if unused.
    pass
