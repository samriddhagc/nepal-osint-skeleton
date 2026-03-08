"""Government contracts table for Bolpatra e-GP procurement data.

Revision ID: 034
Revises: 033
Create Date: 2026-02-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "govt_contracts",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("ifb_number", sa.String(200), nullable=False),
        sa.Column("project_name", sa.Text(), nullable=False),
        sa.Column("procuring_entity", sa.String(500), nullable=False),
        sa.Column("procurement_type", sa.String(50), nullable=False),
        sa.Column("contract_award_date", sa.Date()),
        sa.Column("contract_amount_npr", sa.Float()),
        sa.Column("contractor_name", sa.String(500), nullable=False),
        sa.Column("district", sa.String(100)),
        sa.Column("province", sa.Integer()),
        sa.Column("fiscal_year_bs", sa.String(20)),
        sa.Column("source_url", sa.String(500)),
        sa.Column("raw_data", JSONB),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("external_id", name="uq_govt_contracts_external_id"),
    )
    op.create_index("ix_govt_contracts_external_id", "govt_contracts", ["external_id"])
    op.create_index("ix_govt_contracts_ifb_number", "govt_contracts", ["ifb_number"])
    op.create_index("ix_govt_contracts_procuring_entity", "govt_contracts", ["procuring_entity"])
    op.create_index("ix_govt_contracts_procurement_type", "govt_contracts", ["procurement_type"])
    op.create_index("ix_govt_contracts_contractor_name", "govt_contracts", ["contractor_name"])
    op.create_index("ix_govt_contracts_award_date", "govt_contracts", ["contract_award_date"])
    op.create_index("ix_govt_contracts_district", "govt_contracts", ["district"])
    op.create_index("ix_govt_contracts_fiscal_year_bs", "govt_contracts", ["fiscal_year_bs"])


def downgrade() -> None:
    op.drop_table("govt_contracts")
