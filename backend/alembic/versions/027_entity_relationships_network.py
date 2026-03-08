"""Entity relationships and network metrics for Palantir-grade intelligence.

This migration enables entity network analysis:
- entity_relationships: Co-mention relationships between entities
- entity_network_metrics: PageRank, centrality, clustering metrics

Revision ID: 027
Revises: 026
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create relationship_type ENUM
    op.execute("""
        CREATE TYPE relationship_type AS ENUM (
            'co_mention',
            'party_affiliation',
            'committee_member',
            'family',
            'business_partner',
            'political_ally',
            'political_opponent',
            'predecessor_successor'
        )
    """)

    # Create window_type ENUM for metrics
    op.execute("""
        CREATE TYPE metric_window_type AS ENUM ('24h', '7d', '30d', '90d', 'all_time')
    """)

    # Create entity_relationships table
    op.create_table(
        "entity_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("political_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("political_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship_type",
            postgresql.ENUM(
                'co_mention', 'party_affiliation', 'committee_member', 'family',
                'business_partner', 'political_ally', 'political_opponent',
                'predecessor_successor',
                name="relationship_type",
                create_type=False
            ),
            nullable=False,
            server_default="co_mention",
        ),
        # Co-mention metrics
        sa.Column("co_mention_count", sa.Integer, server_default="0"),
        sa.Column("strength_score", sa.Float, nullable=True),  # 0-1 normalized score
        sa.Column("confidence", sa.Float, nullable=True),  # 0-1 confidence in relationship
        # Temporal tracking
        sa.Column("first_co_mention_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_co_mention_at", sa.DateTime(timezone=True), nullable=True),
        # Additional context
        sa.Column("evidence_story_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("verified_by", sa.String(100), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Unique constraint on source-target-type
        sa.UniqueConstraint("source_entity_id", "target_entity_id", "relationship_type", name="uq_entity_relationship"),
    )

    # Indexes for entity_relationships
    op.create_index("idx_er_source", "entity_relationships", ["source_entity_id"])
    op.create_index("idx_er_target", "entity_relationships", ["target_entity_id"])
    op.create_index("idx_er_type", "entity_relationships", ["relationship_type"])
    op.create_index("idx_er_strength", "entity_relationships", ["strength_score"])
    op.create_index("idx_er_co_mention_count", "entity_relationships", ["co_mention_count"])
    op.create_index("idx_er_last_co_mention", "entity_relationships", ["last_co_mention_at"])
    op.create_index("idx_er_source_type", "entity_relationships", ["source_entity_id", "relationship_type"])

    # Create entity_network_metrics table - precomputed graph metrics
    op.create_table(
        "entity_network_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("political_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "window_type",
            postgresql.ENUM('24h', '7d', '30d', '90d', 'all_time', name="metric_window_type", create_type=False),
            nullable=False,
        ),
        # Centrality metrics
        sa.Column("degree_centrality", sa.Float, nullable=True),
        sa.Column("in_degree_centrality", sa.Float, nullable=True),
        sa.Column("out_degree_centrality", sa.Float, nullable=True),
        sa.Column("betweenness_centrality", sa.Float, nullable=True),
        sa.Column("closeness_centrality", sa.Float, nullable=True),
        sa.Column("eigenvector_centrality", sa.Float, nullable=True),
        sa.Column("pagerank_score", sa.Float, nullable=True),
        # Clustering
        sa.Column("cluster_id", sa.Integer, nullable=True),
        sa.Column("clustering_coefficient", sa.Float, nullable=True),
        # Influence indicators
        sa.Column("is_hub", sa.Boolean, server_default="false"),
        sa.Column("is_authority", sa.Boolean, server_default="false"),
        sa.Column("is_bridge", sa.Boolean, server_default="false"),
        sa.Column("influence_rank", sa.Integer, nullable=True),
        # Connection stats
        sa.Column("total_connections", sa.Integer, server_default="0"),
        sa.Column("incoming_connections", sa.Integer, server_default="0"),
        sa.Column("outgoing_connections", sa.Integer, server_default="0"),
        # Computation metadata
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("computation_version", sa.String(20), nullable=True),
        # Unique constraint on entity + window
        sa.UniqueConstraint("entity_id", "window_type", name="uq_entity_window_metrics"),
    )

    # Indexes for entity_network_metrics
    op.create_index("idx_enm_entity", "entity_network_metrics", ["entity_id"])
    op.create_index("idx_enm_window", "entity_network_metrics", ["window_type"])
    op.create_index("idx_enm_pagerank", "entity_network_metrics", ["window_type", "pagerank_score"])
    op.create_index("idx_enm_influence_rank", "entity_network_metrics", ["window_type", "influence_rank"])
    op.create_index("idx_enm_cluster", "entity_network_metrics", ["window_type", "cluster_id"])
    op.create_index("idx_enm_hub", "entity_network_metrics", ["is_hub"])
    op.create_index("idx_enm_bridge", "entity_network_metrics", ["is_bridge"])

    # Create entity_communities table for cluster/community metadata
    op.create_table(
        "entity_communities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cluster_id", sa.Integer, nullable=False),
        sa.Column(
            "window_type",
            postgresql.ENUM('24h', '7d', '30d', '90d', 'all_time', name="metric_window_type", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=True),  # Auto-generated or manual name
        sa.Column("description", sa.Text, nullable=True),
        # Community characteristics
        sa.Column("member_count", sa.Integer, server_default="0"),
        sa.Column("density", sa.Float, nullable=True),
        sa.Column("modularity_contribution", sa.Float, nullable=True),
        # Representative entities
        sa.Column("central_entity_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("dominant_party", sa.String(100), nullable=True),
        sa.Column("dominant_entity_type", sa.String(50), nullable=True),
        # Timestamps
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Unique constraint
        sa.UniqueConstraint("cluster_id", "window_type", name="uq_community_window"),
    )

    # Indexes for entity_communities
    op.create_index("idx_ec_cluster", "entity_communities", ["cluster_id"])
    op.create_index("idx_ec_window", "entity_communities", ["window_type"])
    op.create_index("idx_ec_dominant_party", "entity_communities", ["dominant_party"])


def downgrade() -> None:
    # Drop tables
    op.drop_table("entity_communities")
    op.drop_table("entity_network_metrics")
    op.drop_table("entity_relationships")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS metric_window_type")
    op.execute("DROP TYPE IF EXISTS relationship_type")
