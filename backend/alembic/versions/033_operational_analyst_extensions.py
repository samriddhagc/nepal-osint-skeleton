"""Operational analyst extensions: AOIs, persisted reports, trade constraints.

Revision ID: 033
Revises: 032
Create Date: 2026-02-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyst_aois",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("geometry", JSONB),
        sa.Column("tags", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_analyst_aois_owner_user_id", "analyst_aois", ["owner_user_id"])

    op.create_table(
        "analyst_reports",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(80), nullable=False),
        sa.Column("time_window_hours", sa.Integer(), nullable=False, server_default=sa.text("168")),
        sa.Column("aoi_id", UUID(), sa.ForeignKey("analyst_aois.id", ondelete="SET NULL")),
        sa.Column("generated_by", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("generated_with_llm", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(40), nullable=False, server_default="completed"),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("metrics_json", JSONB),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_analyst_reports_report_type", "analyst_reports", ["report_type"])
    op.create_index("ix_analyst_reports_aoi_id", "analyst_reports", ["aoi_id"])
    op.create_index("ix_analyst_reports_generated_by", "analyst_reports", ["generated_by"])
    op.create_index("ix_analyst_reports_status", "analyst_reports", ["status"])

    op.create_table(
        "analyst_report_citations",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(), sa.ForeignKey("analyst_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_ref_id", UUID(), sa.ForeignKey("kb_evidence_refs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_hash", sa.String(64), nullable=False),
        sa.Column("citation_order", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("report_id", "claim_hash", "citation_order", name="uq_report_claim_citation_order"),
    )
    op.create_index("ix_analyst_report_citations_report_id", "analyst_report_citations", ["report_id"])
    op.create_index("ix_analyst_report_citations_evidence_ref_id", "analyst_report_citations", ["evidence_ref_id"])
    op.create_index("ix_analyst_report_citations_claim_hash", "analyst_report_citations", ["claim_hash"])

    op.create_unique_constraint("uq_trade_report_source_hash", "trade_reports", ["source_hash"])
    op.drop_constraint("uq_trade_fact_report_record", "trade_facts", type_="unique")
    op.create_unique_constraint(
        "uq_trade_fact_report_record",
        "trade_facts",
        ["report_id", "table_name", "record_key", "direction"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_trade_fact_report_record", "trade_facts", type_="unique")
    op.create_unique_constraint(
        "uq_trade_fact_report_record",
        "trade_facts",
        ["report_id", "table_name", "record_key"],
    )
    op.drop_constraint("uq_trade_report_source_hash", "trade_reports", type_="unique")

    op.drop_table("analyst_report_citations")
    op.drop_table("analyst_reports")
    op.drop_table("analyst_aois")
