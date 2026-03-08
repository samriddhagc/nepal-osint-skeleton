"""Add province_anomaly_runs and province_anomalies tables.

Tables for the lightweight Province Anomaly Agent that classifies
stories/tweets by province and runs a single Sonnet call per cycle.

Revision ID: 053
Revises: 052
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "province_anomaly_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("stories_analyzed", sa.Integer, server_default="0"),
        sa.Column("tweets_analyzed", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("model_used", sa.String(50), server_default="sonnet"),
    )

    op.create_table(
        "province_anomalies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("province_anomaly_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("province_id", sa.Integer, nullable=False),
        sa.Column("province_name", sa.String(50), nullable=False),
        sa.Column("threat_level", sa.String(20), nullable=False, server_default="LOW"),
        sa.Column("threat_trajectory", sa.String(20), nullable=False, server_default="STABLE"),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("political", sa.Text, nullable=True),
        sa.Column("economic", sa.Text, nullable=True),
        sa.Column("security", sa.Text, nullable=True),
        sa.Column("anomalies", JSONB, server_default="[]"),
        sa.Column("story_count", sa.Integer, server_default="0"),
        sa.Column("tweet_count", sa.Integer, server_default="0"),
        sa.Column("key_sources", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_province_anomalies_run_id", "province_anomalies", ["run_id"])
    op.create_index("ix_province_anomaly_runs_status", "province_anomaly_runs", ["status", sa.text("completed_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_province_anomaly_runs_status", table_name="province_anomaly_runs")
    op.drop_index("ix_province_anomalies_run_id", table_name="province_anomalies")
    op.drop_table("province_anomalies")
    op.drop_table("province_anomaly_runs")
