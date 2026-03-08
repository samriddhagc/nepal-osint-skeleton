"""Add fact_check_requests and fact_check_results tables.

Revision ID: 060
Revises: 059
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_check_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "requested_by_id", name="uq_factcheck_story_user"),
    )
    op.create_index("idx_factcheck_req_story", "fact_check_requests", ["story_id"])
    op.create_index("idx_factcheck_req_user", "fact_check_requests", ["requested_by_id"])

    op.create_table(
        "fact_check_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("verdict_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("claims_analyzed", postgresql.JSONB(), nullable=True),
        sa.Column("sources_checked", postgresql.JSONB(), nullable=True),
        sa.Column("key_finding", sa.Text(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", name="uq_factcheck_result_story"),
    )
    op.create_index("idx_factcheck_result_verdict", "fact_check_results", ["verdict"])
    op.create_index("idx_factcheck_result_checked", "fact_check_results", ["checked_at"])
    op.create_index("idx_factcheck_result_story", "fact_check_results", ["story_id"])


def downgrade() -> None:
    op.drop_table("fact_check_results")
    op.drop_table("fact_check_requests")
