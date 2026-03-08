"""Tactical enrichments table for story-level tactical classification.

Revision ID: 061
Revises: 060
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tactical_enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tactical_type", sa.String(40), nullable=False),
        sa.Column("tactical_subtype", sa.String(60), nullable=True),
        sa.Column("municipality", sa.String(100), nullable=True),
        sa.Column("ward", sa.Integer, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("tactical_context", sa.Text, nullable=True),
        sa.Column("actors", postgresql.JSONB, server_default="[]"),
        sa.Column("confidence", sa.String(10), server_default="MEDIUM"),
        sa.Column(
            "enriched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("model_used", sa.String(50), server_default="haiku"),
    )
    op.create_index("ix_tactical_enrichments_type", "tactical_enrichments", ["tactical_type"])
    op.create_index("ix_tactical_enrichments_enriched_at", "tactical_enrichments", ["enriched_at"])


def downgrade() -> None:
    op.drop_index("ix_tactical_enrichments_enriched_at")
    op.drop_index("ix_tactical_enrichments_type")
    op.drop_table("tactical_enrichments")
