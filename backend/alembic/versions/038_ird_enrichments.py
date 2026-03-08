"""IRD PAN enrichment table with privacy-preserving phone hashing.

Revision ID: 038
Revises: 037
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add IRD enrichment flag to company_registrations --
    op.add_column(
        "company_registrations",
        sa.Column("ird_enriched", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "company_registrations",
        sa.Column("ird_enriched_at", sa.DateTime(timezone=True)),
    )

    # -- Create ird_enrichments table --
    op.create_table(
        "ird_enrichments",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "company_id",
            UUID(),
            sa.ForeignKey("company_registrations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # PAN (public tax identifier -- safe to store)
        sa.Column("pan", sa.String(20), nullable=False),
        # Business details (public, non-sensitive)
        sa.Column("taxpayer_name_en", sa.String(500)),
        sa.Column("taxpayer_name_np", sa.String(500)),
        sa.Column("account_type", sa.String(10)),      # e.g. "10"
        sa.Column("account_status", sa.String(200)),     # "A" = active, or "Non-filer: ..."
        sa.Column("registration_date_bs", sa.String(20)),  # BS date e.g. "2077.09.10"
        sa.Column("filing_period", sa.String(5)),       # "Y" = yearly
        sa.Column("tax_office", sa.String(300)),
        sa.Column("is_personal", sa.String(5)),         # "N" = company, "Y" = individual
        # Location (coarse -- district/ward level only, NOT full address)
        sa.Column("ward_no", sa.String(10)),
        sa.Column("vdc_municipality", sa.String(200)),
        # Privacy-preserving hashed fields (HMAC-SHA256)
        # These enable connection detection without storing raw PII
        sa.Column("phone_hash", sa.String(64)),         # HMAC-SHA256 of normalised phone
        sa.Column("mobile_hash", sa.String(64)),        # HMAC-SHA256 of normalised mobile
        # Tax clearance info
        sa.Column("latest_tax_clearance_fy", sa.String(20)),  # e.g. "2080.081"
        sa.Column("tax_clearance_verified", sa.Boolean()),
        # Full raw response (minus PII fields) for future use
        sa.Column("raw_data_sanitised", JSONB),
        # Timestamps
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # Indexes
    op.create_index("ix_ird_enrichments_pan", "ird_enrichments", ["pan"], unique=True)
    op.create_index("ix_ird_enrichments_company_id", "ird_enrichments", ["company_id"])
    op.create_index("ix_ird_enrichments_phone_hash", "ird_enrichments", ["phone_hash"])
    op.create_index("ix_ird_enrichments_mobile_hash", "ird_enrichments", ["mobile_hash"])


def downgrade() -> None:
    op.drop_table("ird_enrichments")
    op.drop_column("company_registrations", "ird_enriched_at")
    op.drop_column("company_registrations", "ird_enriched")
