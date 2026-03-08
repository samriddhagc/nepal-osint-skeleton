"""Add pgvector, embeddings, RL experience, and analysis tables.

Revision ID: 003
Revises: 002
Create Date: 2026-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create story_embeddings table
    op.create_table(
        "story_embeddings",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("embedding", sa.LargeBinary, nullable=True),  # Store as bytes, convert to vector in queries
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
    )

    # Add vector column using raw SQL (pgvector type)
    op.execute("""
        ALTER TABLE story_embeddings
        ADD COLUMN embedding_vector vector(384)
    """)

    # Create HNSW index for fast similarity search
    op.execute("""
        CREATE INDEX idx_story_embeddings_vector
        ON story_embeddings USING hnsw (embedding_vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Create index on text_hash for cache lookup
    op.create_index("idx_story_embeddings_text_hash", "story_embeddings", ["text_hash"])

    # Create story_features table for clustering feature cache
    op.create_table(
        "story_features",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_minhash", postgresql.ARRAY(sa.Integer), nullable=True),
        sa.Column("title_tokens", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("districts", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("constituencies", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("key_terms", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
    )

    # Create experience_records table for RL feedback
    op.create_table(
        "experience_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "experience_type",
            sa.String(30),
            nullable=False,
            comment="CLASSIFICATION|PRIORITY|ANOMALY|SOURCE|TEMPORAL|CLUSTERING",
        ),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", sa.String(50), nullable=True),
        sa.Column("context_features", postgresql.JSONB, nullable=True),
        sa.Column("system_action", sa.String(100), nullable=True),
        sa.Column("human_action", sa.String(100), nullable=True),
        sa.Column("reward", sa.Numeric(4, 2), nullable=True, comment="-1.0 to 1.0"),
        sa.Column("used_in_training", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cluster_id"], ["story_clusters.id"], ondelete="SET NULL"),
    )

    # Create indexes for experience_records
    op.create_index("idx_experience_type", "experience_records", ["experience_type"])
    op.create_index("idx_experience_story_id", "experience_records", ["story_id"])
    op.create_index("idx_experience_used_in_training", "experience_records", ["used_in_training"])
    op.create_index("idx_experience_created_at", "experience_records", ["created_at"])

    # Add analysis fields to story_clusters
    op.add_column(
        "story_clusters",
        sa.Column("bluf", sa.Text, nullable=True, comment="Bottom Line Up Front summary"),
    )
    op.add_column(
        "story_clusters",
        sa.Column("analysis", postgresql.JSONB, nullable=True, comment="Full analysis JSON"),
    )
    op.add_column(
        "story_clusters",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "story_clusters",
        sa.Column("analysis_model", sa.String(100), nullable=True),
    )

    # Create analysis_batches table to track Anthropic batch API requests
    op.create_table(
        "analysis_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("anthropic_batch_id", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            default="pending",
            comment="pending|processing|completed|failed",
        ),
        sa.Column("cluster_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("total_clusters", sa.Integer, nullable=False),
        sa.Column("completed_clusters", sa.Integer, default=0),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("idx_analysis_batches_status", "analysis_batches", ["status"])
    op.create_index("idx_analysis_batches_anthropic_id", "analysis_batches", ["anthropic_batch_id"])

    # Create rl_model_versions table to track model versions
    op.create_table(
        "rl_model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "model_type",
            sa.String(50),
            nullable=False,
            comment="story_classifier|priority_bandit|source_confidence|anomaly_vae|temporal_embedder",
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("accuracy", sa.Numeric(5, 4), nullable=True),
        sa.Column("is_active", sa.Boolean, default=False),
        sa.Column("model_path", sa.String(500), nullable=True),
        sa.Column("training_samples", sa.Integer, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_rl_models_type_active", "rl_model_versions", ["model_type", "is_active"])


def downgrade() -> None:
    # Drop rl_model_versions
    op.drop_index("idx_rl_models_type_active", table_name="rl_model_versions")
    op.drop_table("rl_model_versions")

    # Drop analysis_batches
    op.drop_index("idx_analysis_batches_anthropic_id", table_name="analysis_batches")
    op.drop_index("idx_analysis_batches_status", table_name="analysis_batches")
    op.drop_table("analysis_batches")

    # Drop analysis columns from story_clusters
    op.drop_column("story_clusters", "analysis_model")
    op.drop_column("story_clusters", "analyzed_at")
    op.drop_column("story_clusters", "analysis")
    op.drop_column("story_clusters", "bluf")

    # Drop experience_records indexes and table
    op.drop_index("idx_experience_created_at", table_name="experience_records")
    op.drop_index("idx_experience_used_in_training", table_name="experience_records")
    op.drop_index("idx_experience_story_id", table_name="experience_records")
    op.drop_index("idx_experience_type", table_name="experience_records")
    op.drop_table("experience_records")

    # Drop story_features
    op.drop_table("story_features")

    # Drop story_embeddings
    op.drop_index("idx_story_embeddings_text_hash", table_name="story_embeddings")
    op.execute("DROP INDEX IF EXISTS idx_story_embeddings_vector")
    op.drop_table("story_embeddings")

    # Drop pgvector extension (optional, may want to keep it)
    # op.execute("DROP EXTENSION IF EXISTS vector")
