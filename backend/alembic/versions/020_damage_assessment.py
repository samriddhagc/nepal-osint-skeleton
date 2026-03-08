"""Damage Assessment schema - assessments, zones, evidence, notes.

Revision ID: 020
Revises: 019
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════════════════════
    # DAMAGE ASSESSMENTS TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "damage_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Event identification
        sa.Column("event_name", sa.String(255), nullable=False, index=True),
        sa.Column("event_description", sa.Text, nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False, index=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False, index=True),

        # Geographic scope
        sa.Column("bbox", postgresql.JSONB, nullable=False),
        sa.Column("districts", postgresql.JSONB, nullable=True),
        sa.Column("center_lat", sa.Float, nullable=False),
        sa.Column("center_lng", sa.Float, nullable=False),

        # Satellite analysis parameters
        sa.Column("baseline_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("post_event_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("post_event_end", sa.DateTime(timezone=True), nullable=True),

        # Aggregate results
        sa.Column("total_area_km2", sa.Float, nullable=True),
        sa.Column("damaged_area_km2", sa.Float, nullable=True),
        sa.Column("damage_percentage", sa.Float, nullable=True),

        # Severity breakdown (km²)
        sa.Column("critical_area_km2", sa.Float, nullable=True, server_default="0"),
        sa.Column("severe_area_km2", sa.Float, nullable=True, server_default="0"),
        sa.Column("moderate_area_km2", sa.Float, nullable=True, server_default="0"),
        sa.Column("minor_area_km2", sa.Float, nullable=True, server_default="0"),

        # Population impact
        sa.Column("affected_population", sa.Integer, nullable=True, server_default="0"),
        sa.Column("displaced_estimate", sa.Integer, nullable=True, server_default="0"),

        # Infrastructure impact
        sa.Column("buildings_affected", sa.Integer, nullable=True, server_default="0"),
        sa.Column("roads_damaged_km", sa.Float, nullable=True, server_default="0"),
        sa.Column("bridges_affected", sa.Integer, nullable=True, server_default="0"),
        sa.Column("utilities_disrupted", sa.Integer, nullable=True, server_default="0"),
        sa.Column("infrastructure_details", postgresql.JSONB, nullable=True),

        # Tile URLs for visualization
        sa.Column("damage_tile_url", sa.Text, nullable=True),
        sa.Column("before_tile_url", sa.Text, nullable=True),
        sa.Column("after_tile_url", sa.Text, nullable=True),
        sa.Column("before_sar_tile_url", sa.Text, nullable=True),
        sa.Column("after_sar_tile_url", sa.Text, nullable=True),
        sa.Column("t_stat_tile_url", sa.Text, nullable=True),

        # Metadata
        sa.Column("status", sa.String(20), nullable=False, server_default="draft", index=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("baseline_images_count", sa.Integer, nullable=True),
        sa.Column("post_images_count", sa.Integer, nullable=True),
        sa.Column("key_findings", postgresql.JSONB, nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),

        # Ownership & verification
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("verified_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Constraints
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="ck_assessment_confidence"),
    )
    op.create_index("idx_assessment_event_date", "damage_assessments", ["event_date", "event_type"])
    op.create_index("idx_assessment_status_date", "damage_assessments", ["status", "created_at"])

    # ═══════════════════════════════════════════════════════════════════════════
    # DAMAGE ZONES TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "damage_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Parent assessment
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("damage_assessments.id", ondelete="CASCADE"), nullable=False, index=True),

        # Zone identification
        sa.Column("zone_name", sa.String(255), nullable=True, index=True),
        sa.Column("zone_type", sa.String(50), nullable=False, server_default="area"),

        # Geometry (GeoJSON format)
        sa.Column("geometry", postgresql.JSONB, nullable=False),
        sa.Column("centroid_lat", sa.Float, nullable=False),
        sa.Column("centroid_lng", sa.Float, nullable=False),
        sa.Column("area_km2", sa.Float, nullable=False),

        # Damage metrics
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("damage_percentage", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),

        # Classification
        sa.Column("land_use", sa.String(50), nullable=True),
        sa.Column("building_type", sa.String(100), nullable=True),
        sa.Column("estimated_population", sa.Integer, nullable=True),

        # Verification
        sa.Column("satellite_detected", sa.Boolean, server_default="true"),
        sa.Column("ground_verified", sa.Boolean, server_default="false"),
        sa.Column("verification_notes", sa.Text, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Constraints
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_zone_confidence"),
        sa.CheckConstraint("damage_percentage >= 0 AND damage_percentage <= 100", name="ck_zone_damage_pct"),
    )
    op.create_index("idx_zone_assessment_severity", "damage_zones", ["assessment_id", "severity"])
    op.create_index("idx_zone_location", "damage_zones", ["centroid_lat", "centroid_lng"])

    # ═══════════════════════════════════════════════════════════════════════════
    # DAMAGE EVIDENCE TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "damage_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Links
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("damage_zones.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("damage_assessments.id", ondelete="CASCADE"), nullable=False, index=True),

        # Source reference
        sa.Column("source_type", sa.String(30), nullable=False, index=True),
        sa.Column("source_id", sa.String(100), nullable=True, index=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_name", sa.String(255), nullable=True),

        # Evidence details
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("media_url", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True, index=True),

        # Location
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),

        # Confidence & verification
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified", index=True),
        sa.Column("verification_notes", sa.Text, nullable=True),

        # Auto-linking metadata
        sa.Column("auto_linked", sa.Boolean, server_default="false"),
        sa.Column("link_confidence", sa.Float, nullable=True),

        # Metadata
        sa.Column("added_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Constraints
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evidence_confidence"),
    )
    op.create_index("idx_evidence_assessment", "damage_evidence", ["assessment_id", "source_type"])
    op.create_index("idx_evidence_timestamp", "damage_evidence", ["timestamp"])

    # ═══════════════════════════════════════════════════════════════════════════
    # ASSESSMENT NOTES TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "assessment_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Links
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("damage_assessments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("damage_zones.id", ondelete="SET NULL"), nullable=True, index=True),

        # Note content
        sa.Column("note_type", sa.String(30), nullable=False, server_default="observation"),
        sa.Column("content", sa.Text, nullable=False),

        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),

        # Author
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),

        # Resolution
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_assessment_note_status", "assessment_notes", ["assessment_id", "status"])
    op.create_index("idx_assessment_note_author", "assessment_notes", ["author_id", "created_at"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("assessment_notes")
    op.drop_table("damage_evidence")
    op.drop_table("damage_zones")
    op.drop_table("damage_assessments")
