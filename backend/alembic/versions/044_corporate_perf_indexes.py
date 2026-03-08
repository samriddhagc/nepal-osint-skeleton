"""Add performance indexes for corporate dashboard queries.

Revision ID: 044
Revises: 043
Create Date: 2026-02-10
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Address clustering and group-by queries
    op.create_index(
        "ix_company_registrations_company_address",
        "company_registrations",
        ["company_address"],
    )
    # Timeline filtering/sorting by AD date
    op.create_index(
        "ix_company_registrations_registration_date_ad",
        "company_registrations",
        ["registration_date_ad"],
    )
    # Risk dashboard filtering (e.g. Non-filer status)
    op.create_index(
        "ix_ird_enrichments_account_status",
        "ird_enrichments",
        ["account_status"],
    )
    # Shared-director lookups and joins
    op.create_index(
        "ix_company_directors_company_id_name_en",
        "company_directors",
        ["company_id", "name_en"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_directors_company_id_name_en",
        table_name="company_directors",
    )
    op.drop_index(
        "ix_ird_enrichments_account_status",
        table_name="ird_enrichments",
    )
    op.drop_index(
        "ix_company_registrations_registration_date_ad",
        table_name="company_registrations",
    )
    op.drop_index(
        "ix_company_registrations_company_address",
        table_name="company_registrations",
    )
