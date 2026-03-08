"""Company registrations table for OCR (Office of Company Registrar) data.

Revision ID: 035
Revises: 034
Create Date: 2026-02-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_registrations",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("registration_number", sa.Integer(), nullable=False),
        sa.Column("name_nepali", sa.Text()),
        sa.Column("name_english", sa.String(500), nullable=False),
        sa.Column("registration_date_bs", sa.String(20)),
        sa.Column("registration_date_ad", sa.Date()),
        sa.Column("company_type", sa.String(500)),
        sa.Column("company_type_category", sa.String(50)),
        sa.Column("company_address", sa.String(500)),
        sa.Column("district", sa.String(100)),
        sa.Column("province", sa.String(100)),
        sa.Column("last_communication_bs", sa.String(20)),
        sa.Column("raw_data", JSONB),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("external_id", name="uq_company_registrations_external_id"),
    )
    op.create_index("ix_company_registrations_external_id", "company_registrations", ["external_id"])
    op.create_index("ix_company_registrations_registration_number", "company_registrations", ["registration_number"])
    op.create_index("ix_company_registrations_name_english", "company_registrations", ["name_english"])
    op.create_index("ix_company_registrations_company_type_category", "company_registrations", ["company_type_category"])
    op.create_index("ix_company_registrations_district", "company_registrations", ["district"])
    op.create_index("ix_company_registrations_province", "company_registrations", ["province"])


def downgrade() -> None:
    op.drop_table("company_registrations")
