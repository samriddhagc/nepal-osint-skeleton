"""Investigation case management tables.

Revision ID: 040
Revises: 039
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- investigation_cases --
    op.create_table(
        "investigation_cases",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            comment="open | active | closed | archived",
        ),
        sa.Column(
            "priority",
            sa.String(20),
            nullable=False,
            server_default="medium",
            comment="low | medium | high | critical",
        ),
        sa.Column(
            "created_by",
            UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to",
            UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_investigation_cases_status", "investigation_cases", ["status"])
    op.create_index("ix_investigation_cases_priority", "investigation_cases", ["priority"])
    op.create_index("ix_investigation_cases_created_by", "investigation_cases", ["created_by"])
    op.create_index("ix_investigation_cases_assigned_to", "investigation_cases", ["assigned_to"])

    # -- case_entities --
    op.create_table(
        "case_entities",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "case_id",
            UUID(),
            sa.ForeignKey("investigation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.String(20),
            nullable=False,
            comment="company | person | pan",
        ),
        sa.Column("entity_id", sa.String(200), nullable=False),
        sa.Column("entity_label", sa.String(500), nullable=False),
        sa.Column(
            "added_by",
            UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_case_entities_case_id", "case_entities", ["case_id"])
    op.create_index("ix_case_entities_entity_type", "case_entities", ["entity_type"])

    # -- case_findings --
    op.create_table(
        "case_findings",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "case_id",
            UUID(),
            sa.ForeignKey("investigation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "finding_type",
            sa.String(30),
            nullable=False,
            comment="risk_flag | anomaly | observation | evidence",
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default="info",
            comment="info | low | medium | high | critical",
        ),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", sa.String(200), nullable=True),
        sa.Column(
            "created_by",
            UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_case_findings_case_id", "case_findings", ["case_id"])
    op.create_index("ix_case_findings_severity", "case_findings", ["severity"])

    # -- case_notes --
    op.create_table(
        "case_notes",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "case_id",
            UUID(),
            sa.ForeignKey("investigation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_by",
            UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_case_notes_case_id", "case_notes", ["case_id"])


def downgrade() -> None:
    op.drop_table("case_notes")
    op.drop_table("case_findings")
    op.drop_table("case_entities")
    op.drop_table("investigation_cases")
