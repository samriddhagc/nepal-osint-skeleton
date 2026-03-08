"""Add analyst phone cluster group persistence.

Revision ID: 045
Revises: 044
Create Date: 2026-02-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyst_phone_cluster_groups",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("main_cluster_id", sa.String(length=160), nullable=True),
        sa.Column("clusters", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("edges", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_by_id",
            UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "updated_by_id",
            UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index(
        "ix_analyst_phone_cluster_groups_created_by_id",
        "analyst_phone_cluster_groups",
        ["created_by_id"],
    )
    op.create_index(
        "ix_analyst_phone_cluster_groups_updated_by_id",
        "analyst_phone_cluster_groups",
        ["updated_by_id"],
    )
    op.create_index(
        "ix_analyst_phone_cluster_groups_updated_at",
        "analyst_phone_cluster_groups",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analyst_phone_cluster_groups_updated_at",
        table_name="analyst_phone_cluster_groups",
    )
    op.drop_index(
        "ix_analyst_phone_cluster_groups_updated_by_id",
        table_name="analyst_phone_cluster_groups",
    )
    op.drop_index(
        "ix_analyst_phone_cluster_groups_created_by_id",
        table_name="analyst_phone_cluster_groups",
    )
    op.drop_table("analyst_phone_cluster_groups")
