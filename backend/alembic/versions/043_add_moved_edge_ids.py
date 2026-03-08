"""Add moved_edge_ids JSONB column to entity_resolutions.

This column stores the IDs of edges that were re-pointed during a merge
operation, enabling precise reversal during unmerge (CRITICAL-4 fix).
The value is a JSON object: {"outgoing": [uuid,...], "incoming": [uuid,...], "deleted": [uuid,...]}.

Revision ID: 043
Revises: 042
Create Date: 2026-02-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_resolutions",
        sa.Column("moved_edge_ids", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_resolutions", "moved_edge_ids")
