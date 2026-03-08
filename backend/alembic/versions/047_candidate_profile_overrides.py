"""Add candidate_profile_overrides projection table.

Revision ID: 047
Revises: 046
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_profile_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_external_id", sa.String(length=50), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_correction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_correction_id"],
            ["candidate_corrections.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_candidate_profile_overrides_candidate_field",
        "candidate_profile_overrides",
        ["candidate_external_id", "field"],
        unique=True,
    )
    op.create_index(
        "idx_candidate_profile_overrides_active",
        "candidate_profile_overrides",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_candidate_profile_overrides_active", table_name="candidate_profile_overrides")
    op.drop_index("idx_candidate_profile_overrides_candidate_field", table_name="candidate_profile_overrides")
    op.drop_table("candidate_profile_overrides")

