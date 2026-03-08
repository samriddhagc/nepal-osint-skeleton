"""Unified graph rollout support tables, indexes, and connectivity MV.

Revision ID: 050
Revises: 049
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("phases", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_gir_started_at", "graph_ingestion_runs", ["started_at"], unique=False)
    op.create_index("idx_gir_status", "graph_ingestion_runs", ["status"], unique=False)

    op.create_table(
        "graph_ingestion_run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["graph_ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "phase", name="uq_graph_ingestion_run_step"),
    )
    op.create_index("idx_girs_phase", "graph_ingestion_run_steps", ["phase"], unique=False)
    op.create_index("idx_girs_status", "graph_ingestion_run_steps", ["status"], unique=False)
    op.create_index("idx_graph_ingestion_run_steps_run_id", "graph_ingestion_run_steps", ["run_id"], unique=False)

    op.create_index(
        "idx_ge_hop_fwd_current",
        "graph_edges",
        ["source_node_id", "predicate", "target_node_id", "is_current"],
        unique=False,
    )
    op.create_index(
        "idx_ge_hop_rev_current",
        "graph_edges",
        ["target_node_id", "predicate", "source_node_id", "is_current"],
        unique=False,
    )
    op.create_index("idx_ge_valid_from", "graph_edges", ["valid_from"], unique=False)
    op.create_index("idx_ge_valid_to", "graph_edges", ["valid_to"], unique=False)
    op.create_index("idx_ge_last_seen_at", "graph_edges", ["last_seen_at"], unique=False)

    op.execute(
        """
        CREATE MATERIALIZED VIEW graph_domain_connectivity_mv AS
        WITH connected_nodes AS (
            SELECT source_node_id AS node_id
            FROM graph_edges
            WHERE is_current = true
            UNION
            SELECT target_node_id AS node_id
            FROM graph_edges
            WHERE is_current = true
        ),
        domain_counts AS (
            SELECT source_table, COUNT(*) AS total_nodes
            FROM graph_nodes
            WHERE is_canonical = true
            GROUP BY source_table
        ),
        connected_counts AS (
            SELECT gn.source_table, COUNT(*) AS connected_nodes
            FROM graph_nodes gn
            JOIN connected_nodes cn ON cn.node_id = gn.id
            WHERE gn.is_canonical = true
            GROUP BY gn.source_table
        )
        SELECT
            dc.source_table,
            dc.total_nodes,
            COALESCE(cc.connected_nodes, 0) AS connected_nodes,
            CASE
                WHEN dc.total_nodes = 0 THEN 0
                ELSE ROUND((COALESCE(cc.connected_nodes, 0)::numeric / dc.total_nodes::numeric), 6)
            END AS coverage_ratio
        FROM domain_counts dc
        LEFT JOIN connected_counts cc USING (source_table)
        """
    )
    op.create_index(
        "idx_graph_domain_connectivity_mv_source_table",
        "graph_domain_connectivity_mv",
        ["source_table"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_graph_domain_connectivity_mv_source_table", table_name="graph_domain_connectivity_mv")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_domain_connectivity_mv")

    op.drop_index("idx_ge_last_seen_at", table_name="graph_edges")
    op.drop_index("idx_ge_valid_to", table_name="graph_edges")
    op.drop_index("idx_ge_valid_from", table_name="graph_edges")
    op.drop_index("idx_ge_hop_rev_current", table_name="graph_edges")
    op.drop_index("idx_ge_hop_fwd_current", table_name="graph_edges")

    op.drop_index("idx_graph_ingestion_run_steps_run_id", table_name="graph_ingestion_run_steps")
    op.drop_index("idx_girs_status", table_name="graph_ingestion_run_steps")
    op.drop_index("idx_girs_phase", table_name="graph_ingestion_run_steps")
    op.drop_table("graph_ingestion_run_steps")

    op.drop_index("idx_gir_status", table_name="graph_ingestion_runs")
    op.drop_index("idx_gir_started_at", table_name="graph_ingestion_runs")
    op.drop_table("graph_ingestion_runs")
