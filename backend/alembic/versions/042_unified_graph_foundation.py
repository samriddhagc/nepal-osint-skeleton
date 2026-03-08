"""Create unified graph foundation tables: districts, graph_nodes, graph_edges,
graph_node_metrics, entity_resolutions.

This migration implements Phase 0 of the NARADA unified graph system as defined
in docs/discuss.md (Round 10 Consensus Design).  It creates five new tables with
comprehensive indexing for forward/reverse hop traversal, temporal range queries,
JSONB GIN indexes, and partial indexes for active/canonical-only filtering.

NOTE: The normalize_district() PostgreSQL function referenced in the design will
be created via a separate migration or implemented as a Python service-layer function
(see app.data.nepal_districts.normalize_district_name for the Python implementation).

Revision ID: 042
Revises: 041
Create Date: 2026-02-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY

# revision identifiers, used by Alembic.
revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. graph_nodes — must be created before districts (FK dependency)
    # ------------------------------------------------------------------
    op.create_table(
        "graph_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("canonical_key", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("title_ne", sa.String(500), nullable=True),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("subtype", sa.String(60), nullable=True),
        sa.Column("tags", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("province", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("properties", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_table", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("canonical_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_canonical", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("resolution_metadata", JSONB, nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("canonical_key", name="uq_gn_canonical_key"),
    )

    # graph_nodes indexes
    op.create_index("idx_gn_node_type", "graph_nodes", ["node_type"])
    op.create_index("idx_gn_district", "graph_nodes", ["district"])
    op.create_index("idx_gn_province", "graph_nodes", ["province"])
    op.create_index("idx_gn_source", "graph_nodes", ["source_table", "source_id"])
    op.create_index("idx_gn_canonical_key", "graph_nodes", ["canonical_key"])
    op.create_index(
        "idx_gn_canonical_node_id",
        "graph_nodes",
        ["canonical_node_id"],
        postgresql_where=sa.text("NOT is_canonical"),
    )
    op.create_index("idx_gn_properties_gin", "graph_nodes", ["properties"], postgresql_using="gin")
    op.create_index("idx_gn_tags_gin", "graph_nodes", ["tags"], postgresql_using="gin")
    op.create_index(
        "idx_gn_lat_lng",
        "graph_nodes",
        ["latitude", "longitude"],
        postgresql_where=sa.text("latitude IS NOT NULL"),
    )
    op.create_index("idx_gn_last_seen_at", "graph_nodes", ["last_seen_at"])

    # ------------------------------------------------------------------
    # 2. districts — reference table for Nepal's 77 districts
    # ------------------------------------------------------------------
    op.create_table(
        "districts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("name_ne", sa.String(100), nullable=True),
        sa.Column("province_id", sa.Integer, nullable=False),
        sa.Column("province_name", sa.String(100), nullable=False),
        sa.Column("headquarters", sa.String(100), nullable=True),
        sa.Column("area_sq_km", sa.Float, nullable=True),
        sa.Column("population_2021", sa.Integer, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("boundary_geojson", JSONB, nullable=True),
        sa.Column("aliases", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "graph_node_id",
            UUID(as_uuid=True),
            sa.ForeignKey("graph_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name_en", name="uq_districts_name_en"),
    )

    op.create_index("idx_districts_province_id", "districts", ["province_id"])
    op.create_index("idx_districts_name_en", "districts", ["name_en"])

    # ------------------------------------------------------------------
    # 3. graph_edges — unified edge table
    # ------------------------------------------------------------------
    op.create_table(
        "graph_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicate", sa.String(80), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("evidence_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("properties", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_table", sa.String(80), nullable=True),
        sa.Column("source_id", sa.String(80), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="candidate"),
        sa.Column("verified_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_node_id",
            "target_node_id",
            "predicate",
            "valid_from",
            name="uq_ge_source_target_predicate_valid_from",
        ),
    )

    # graph_edges indexes
    op.create_index("idx_ge_source_node_id", "graph_edges", ["source_node_id"])
    op.create_index("idx_ge_target_node_id", "graph_edges", ["target_node_id"])
    op.create_index("idx_ge_predicate", "graph_edges", ["predicate"])
    op.create_index("idx_ge_hop_fwd", "graph_edges", ["source_node_id", "predicate", "target_node_id"])
    op.create_index("idx_ge_hop_rev", "graph_edges", ["target_node_id", "predicate", "source_node_id"])
    op.create_index("idx_ge_valid_range", "graph_edges", ["valid_from", "valid_to"])
    op.create_index(
        "idx_ge_current",
        "graph_edges",
        ["source_node_id", "predicate"],
        postgresql_where=sa.text("is_current = true"),
    )
    op.create_index("idx_ge_confidence", "graph_edges", ["confidence"])
    op.create_index("idx_ge_properties_gin", "graph_edges", ["properties"], postgresql_using="gin")

    # ------------------------------------------------------------------
    # 4. graph_node_metrics — precomputed centrality metrics
    # ------------------------------------------------------------------
    op.create_table(
        "graph_node_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_type", sa.String(20), nullable=False),
        sa.Column("degree", sa.Integer, nullable=False, server_default="0"),
        sa.Column("in_degree", sa.Integer, nullable=False, server_default="0"),
        sa.Column("out_degree", sa.Integer, nullable=False, server_default="0"),
        sa.Column("betweenness", sa.Float, nullable=True),
        sa.Column("closeness", sa.Float, nullable=True),
        sa.Column("pagerank", sa.Float, nullable=True),
        sa.Column("cluster_id", sa.Integer, nullable=True),
        sa.Column("clustering_coeff", sa.Float, nullable=True),
        sa.Column("is_hub", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_bridge", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("influence_rank", sa.Integer, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("node_id", "window_type", name="uq_gnm_node_window"),
    )

    op.create_index("idx_gnm_node_id", "graph_node_metrics", ["node_id"])
    op.create_index(
        "idx_gnm_pagerank_alltime",
        "graph_node_metrics",
        [sa.text("pagerank DESC")],
        postgresql_where=sa.text("window_type = 'all_time'"),
    )

    # ------------------------------------------------------------------
    # 5. entity_resolutions — auditable merge tracking
    # ------------------------------------------------------------------
    op.create_table(
        "entity_resolutions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canonical_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merged_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_method", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("is_auto", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("unresolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("unresolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("canonical_node_id", "merged_node_id", name="uq_er_canonical_merged"),
    )

    op.create_index("idx_er_canonical_node_id", "entity_resolutions", ["canonical_node_id"])
    op.create_index("idx_er_merged_node_id", "entity_resolutions", ["merged_node_id"])
    op.create_index("idx_er_match_method", "entity_resolutions", ["match_method"])
    op.create_index(
        "idx_er_active",
        "entity_resolutions",
        ["canonical_node_id"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    # Drop in reverse order of creation to satisfy FK dependencies
    op.drop_table("entity_resolutions")
    op.drop_table("graph_node_metrics")
    op.drop_table("graph_edges")
    op.drop_table("districts")
    op.drop_table("graph_nodes")
