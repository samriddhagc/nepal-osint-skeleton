"""Add graph_corrections workflow table.

Revision ID: 049
Revises: 048
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("applied_change", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["edge_id"], ["graph_edges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_id"], ["graph_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rolled_back_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_graph_corrections_action", "graph_corrections", ["action"], unique=False)
    op.create_index("idx_graph_corrections_edge_id", "graph_corrections", ["edge_id"], unique=False)
    op.create_index("idx_graph_corrections_node_id", "graph_corrections", ["node_id"], unique=False)
    op.create_index("idx_graph_corrections_status", "graph_corrections", ["status"], unique=False)
    op.create_index(
        "idx_graph_corrections_status_submitted",
        "graph_corrections",
        ["status", "submitted_at"],
        unique=False,
    )
    op.create_index("idx_graph_corrections_submitted_by", "graph_corrections", ["submitted_by"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_graph_corrections_submitted_by", table_name="graph_corrections")
    op.drop_index("idx_graph_corrections_status_submitted", table_name="graph_corrections")
    op.drop_index("idx_graph_corrections_status", table_name="graph_corrections")
    op.drop_index("idx_graph_corrections_node_id", table_name="graph_corrections")
    op.drop_index("idx_graph_corrections_edge_id", table_name="graph_corrections")
    op.drop_index("idx_graph_corrections_action", table_name="graph_corrections")
    op.drop_table("graph_corrections")

