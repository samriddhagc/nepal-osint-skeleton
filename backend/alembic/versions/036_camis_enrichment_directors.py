"""CAMIS enrichment columns + company_directors table.

Revision ID: 036
Revises: 035
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add CAMIS enrichment columns to company_registrations --
    op.add_column("company_registrations", sa.Column("camis_company_id", sa.Integer()))
    op.add_column("company_registrations", sa.Column("cro_company_id", sa.String(50)))
    op.add_column("company_registrations", sa.Column("pan", sa.String(20)))
    op.add_column(
        "company_registrations",
        sa.Column("camis_enriched", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("company_registrations", sa.Column("camis_enriched_at", sa.DateTime(timezone=True)))
    op.create_index("ix_company_registrations_pan", "company_registrations", ["pan"])

    # -- Create company_directors table --
    op.create_table(
        "company_directors",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "company_id",
            UUID(),
            sa.ForeignKey("company_registrations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name_en", sa.String(300), nullable=False),
        sa.Column("name_np", sa.String(300)),
        sa.Column("role", sa.String(100)),
        sa.Column("company_name_hint", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pan", sa.String(20)),
        sa.Column("citizenship_no", sa.String(30)),
        sa.Column("appointed_date", sa.Date()),
        sa.Column("resigned_date", sa.Date()),
        sa.Column("raw_data", JSONB),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_company_directors_company_id", "company_directors", ["company_id"])
    op.create_index("ix_company_directors_name_en", "company_directors", ["name_en"])
    op.create_index("ix_company_directors_source", "company_directors", ["source"])
    op.create_index("ix_company_directors_pan", "company_directors", ["pan"])


def downgrade() -> None:
    op.drop_table("company_directors")
    op.drop_index("ix_company_registrations_pan", table_name="company_registrations")
    op.drop_column("company_registrations", "camis_enriched_at")
    op.drop_column("company_registrations", "camis_enriched")
    op.drop_column("company_registrations", "pan")
    op.drop_column("company_registrations", "cro_company_id")
    op.drop_column("company_registrations", "camis_company_id")
