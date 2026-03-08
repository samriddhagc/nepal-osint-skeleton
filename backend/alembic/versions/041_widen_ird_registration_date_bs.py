"""Widen ird_enrichments.registration_date_bs from VARCHAR(20) to VARCHAR(50).

IRD returns values like '2075.09.04(RT DATE: 2078.04.01)' which are 31 chars.

Revision ID: 041
Revises: 040
Create Date: 2026-02-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "ird_enrichments",
        "registration_date_bs",
        type_=sa.String(50),
        existing_type=sa.String(20),
    )


def downgrade() -> None:
    op.alter_column(
        "ird_enrichments",
        "registration_date_bs",
        type_=sa.String(20),
        existing_type=sa.String(50),
    )
