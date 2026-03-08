"""Add persistent procurement contractor -> OCR company linkage table.

Revision ID: 051
Revises: 050
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "procurement_company_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contractor_name", sa.String(length=500), nullable=False),
        sa.Column("contractor_name_normalized", sa.String(length=500), nullable=False),
        sa.Column("contractor_name_compact", sa.String(length=500), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_status", sa.String(length=20), nullable=False, server_default="unmatched"),
        sa.Column("match_type", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_margin", sa.Float(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["company_registrations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contractor_name", name="uq_procurement_company_links_contractor_name"),
    )

    op.create_index(
        "idx_procurement_company_links_company_id",
        "procurement_company_links",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "idx_procurement_company_links_status",
        "procurement_company_links",
        ["match_status"],
        unique=False,
    )
    op.create_index(
        "idx_procurement_company_links_norm",
        "procurement_company_links",
        ["contractor_name_normalized"],
        unique=False,
    )
    op.create_index(
        "idx_procurement_company_links_compact",
        "procurement_company_links",
        ["contractor_name_compact"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_procurement_company_links_compact", table_name="procurement_company_links")
    op.drop_index("idx_procurement_company_links_norm", table_name="procurement_company_links")
    op.drop_index("idx_procurement_company_links_status", table_name="procurement_company_links")
    op.drop_index("idx_procurement_company_links_company_id", table_name="procurement_company_links")
    op.drop_table("procurement_company_links")
