"""Connected analyst graph, trade intelligence, PWTT evidence, and hypotheses.

Revision ID: 032
Revises: 031
Create Date: 2026-02-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PGEnum

# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    analyst_verification_status = PGEnum(
        "unverified",
        "candidate",
        "verified",
        "rejected",
        name="analyst_verification_status",
    )
    analyst_source_classification = PGEnum(
        "official",
        "independent",
        "unknown",
        name="analyst_source_classification",
    )
    trade_direction = PGEnum("import", "export", "total", name="trade_direction")
    damage_run_status = PGEnum("queued", "running", "completed", "failed", name="damage_run_status")
    provenance_owner_type = PGEnum(
        "object",
        "link",
        "trade_anomaly",
        "damage_finding",
        "hypothesis",
        name="provenance_owner_type",
    )
    hypothesis_status = PGEnum(
        "open",
        "supported",
        "contradicted",
        "inconclusive",
        name="hypothesis_status",
    )
    hypothesis_evidence_relation = PGEnum(
        "supports",
        "contradicts",
        "context",
        name="hypothesis_evidence_relation",
    )

    bind = op.get_bind()
    analyst_verification_status.create(bind, checkfirst=True)
    analyst_source_classification.create(bind, checkfirst=True)
    trade_direction.create(bind, checkfirst=True)
    damage_run_status.create(bind, checkfirst=True)
    provenance_owner_type.create(bind, checkfirst=True)
    hypothesis_status.create(bind, checkfirst=True)
    hypothesis_evidence_relation.create(bind, checkfirst=True)

    # Re-bind as existing named types so table creation does not attempt CREATE TYPE again.
    analyst_verification_status = PGEnum(
        "unverified",
        "candidate",
        "verified",
        "rejected",
        name="analyst_verification_status",
        create_type=False,
    )
    analyst_source_classification = PGEnum(
        "official",
        "independent",
        "unknown",
        name="analyst_source_classification",
        create_type=False,
    )
    trade_direction = PGEnum("import", "export", "total", name="trade_direction", create_type=False)
    damage_run_status = PGEnum(
        "queued",
        "running",
        "completed",
        "failed",
        name="damage_run_status",
        create_type=False,
    )
    provenance_owner_type = PGEnum(
        "object",
        "link",
        "trade_anomaly",
        "damage_finding",
        "hypothesis",
        name="provenance_owner_type",
        create_type=False,
    )
    hypothesis_status = PGEnum(
        "open",
        "supported",
        "contradicted",
        "inconclusive",
        name="hypothesis_status",
        create_type=False,
    )
    hypothesis_evidence_relation = PGEnum(
        "supports",
        "contradicts",
        "context",
        name="hypothesis_evidence_relation",
        create_type=False,
    )

    op.create_table(
        "kb_objects",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("object_type", sa.String(60), nullable=False),
        sa.Column("canonical_key", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("attributes", JSONB),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verification_status", analyst_verification_status, nullable=False, server_default="candidate"),
        sa.Column("created_by_id", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("canonical_key", name="uq_kb_objects_canonical_key"),
    )
    op.create_index("ix_kb_objects_object_type", "kb_objects", ["object_type"])
    op.create_index("ix_kb_objects_canonical_key", "kb_objects", ["canonical_key"])
    op.create_index("ix_kb_objects_verification_status", "kb_objects", ["verification_status"])

    op.create_table(
        "kb_links",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_object_id", UUID(), sa.ForeignKey("kb_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_object_id", UUID(), sa.ForeignKey("kb_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicate", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verification_status", analyst_verification_status, nullable=False, server_default="candidate"),
        sa.Column("metadata", JSONB),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("source_object_id", "target_object_id", "predicate", name="uq_kb_links_pair_predicate"),
    )
    op.create_index("ix_kb_links_source_object_id", "kb_links", ["source_object_id"])
    op.create_index("ix_kb_links_target_object_id", "kb_links", ["target_object_id"])
    op.create_index("ix_kb_links_predicate", "kb_links", ["predicate"])
    op.create_index("ix_kb_links_verification_status", "kb_links", ["verification_status"])

    op.create_table(
        "kb_evidence_refs",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_type", provenance_owner_type, nullable=False),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("evidence_id", sa.String(100)),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_key", sa.String(255)),
        sa.Column("source_name", sa.String(255)),
        sa.Column("source_classification", analyst_source_classification, nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("excerpt", sa.Text()),
        sa.Column("metadata", JSONB),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_kb_evidence_refs_owner_type", "kb_evidence_refs", ["owner_type"])
    op.create_index("ix_kb_evidence_refs_owner_id", "kb_evidence_refs", ["owner_id"])
    op.create_index("ix_kb_evidence_refs_evidence_type", "kb_evidence_refs", ["evidence_type"])
    op.create_index("ix_kb_evidence_refs_evidence_id", "kb_evidence_refs", ["evidence_id"])
    op.create_index("ix_kb_evidence_refs_source_key", "kb_evidence_refs", ["source_key"])
    op.create_index("ix_kb_evidence_refs_source_classification", "kb_evidence_refs", ["source_classification"])

    op.create_table(
        "trade_reports",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fiscal_year_bs", sa.String(20), nullable=False),
        sa.Column("upto_month", sa.String(30), nullable=False),
        sa.Column("month_ordinal", sa.Integer(), nullable=False),
        sa.Column("report_title", sa.String(500)),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("coverage_text", sa.Text()),
        sa.Column("coverage_start_ad", sa.DateTime(timezone=True)),
        sa.Column("coverage_end_ad", sa.DateTime(timezone=True)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("fiscal_year_bs", "month_ordinal", "file_path", name="uq_trade_report_file_window"),
    )
    op.create_index("ix_trade_reports_fiscal_year_bs", "trade_reports", ["fiscal_year_bs"])
    op.create_index("ix_trade_reports_upto_month", "trade_reports", ["upto_month"])
    op.create_index("ix_trade_reports_month_ordinal", "trade_reports", ["month_ordinal"])

    op.create_table(
        "trade_facts",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(), sa.ForeignKey("trade_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(80), nullable=False),
        sa.Column("direction", trade_direction, nullable=False),
        sa.Column("hs_code", sa.String(20)),
        sa.Column("commodity_description", sa.Text()),
        sa.Column("partner_country", sa.String(200)),
        sa.Column("customs_office", sa.String(200)),
        sa.Column("unit", sa.String(30)),
        sa.Column("quantity", sa.Float()),
        sa.Column("value_npr_thousands", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("revenue_npr_thousands", sa.Float()),
        sa.Column("cumulative_value_npr_thousands", sa.Float()),
        sa.Column("delta_value_npr_thousands", sa.Float()),
        sa.Column("record_key", sa.String(255), nullable=False),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("report_id", "table_name", "record_key", name="uq_trade_fact_report_record"),
    )
    op.create_index("ix_trade_facts_report_id", "trade_facts", ["report_id"])
    op.create_index("ix_trade_facts_table_name", "trade_facts", ["table_name"])
    op.create_index("ix_trade_facts_direction", "trade_facts", ["direction"])
    op.create_index("ix_trade_facts_hs_code", "trade_facts", ["hs_code"])
    op.create_index("ix_trade_facts_partner_country", "trade_facts", ["partner_country"])
    op.create_index("ix_trade_facts_customs_office", "trade_facts", ["customs_office"])
    op.create_index("ix_trade_facts_record_key", "trade_facts", ["record_key"])

    op.create_table(
        "trade_anomalies",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trade_fact_id", UUID(), sa.ForeignKey("trade_facts.id", ondelete="SET NULL")),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("dimension_key", sa.String(255), nullable=False),
        sa.Column("fiscal_year_bs", sa.String(20), nullable=False),
        sa.Column("month_ordinal", sa.Integer(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("expected_value", sa.Float()),
        sa.Column("baseline_mean", sa.Float()),
        sa.Column("baseline_std", sa.Float()),
        sa.Column("deviation_pct", sa.Float()),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("verification_status", analyst_verification_status, nullable=False, server_default="candidate"),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_trade_anomalies_trade_fact_id", "trade_anomalies", ["trade_fact_id"])
    op.create_index("ix_trade_anomalies_dimension", "trade_anomalies", ["dimension"])
    op.create_index("ix_trade_anomalies_dimension_key", "trade_anomalies", ["dimension_key"])
    op.create_index("ix_trade_anomalies_fiscal_year_bs", "trade_anomalies", ["fiscal_year_bs"])
    op.create_index("ix_trade_anomalies_month_ordinal", "trade_anomalies", ["month_ordinal"])
    op.create_index("ix_trade_anomalies_verification_status", "trade_anomalies", ["verification_status"])
    op.create_index(
        "idx_trade_anomaly_dimension_window",
        "trade_anomalies",
        ["dimension", "dimension_key", "fiscal_year_bs", "month_ordinal"],
    )

    op.create_table(
        "damage_runs",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(), sa.ForeignKey("damage_assessments.id", ondelete="SET NULL")),
        sa.Column("case_id", UUID(), sa.ForeignKey("cases.id", ondelete="SET NULL")),
        sa.Column("algorithm_name", sa.String(120), nullable=False),
        sa.Column("algorithm_version", sa.String(80), nullable=False),
        sa.Column("status", damage_run_status, nullable=False, server_default="queued"),
        sa.Column("aoi_geojson", JSONB, nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True)),
        sa.Column("run_params", JSONB),
        sa.Column("initiated_by_id", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("summary", JSONB),
        sa.Column("verification_status", analyst_verification_status, nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_damage_runs_assessment_id", "damage_runs", ["assessment_id"])
    op.create_index("ix_damage_runs_case_id", "damage_runs", ["case_id"])
    op.create_index("ix_damage_runs_status", "damage_runs", ["status"])

    op.create_table(
        "damage_artifacts",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(), sa.ForeignKey("damage_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(80), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("metadata", JSONB),
        sa.Column("source_classification", analyst_source_classification, nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_damage_artifacts_run_id", "damage_artifacts", ["run_id"])
    op.create_index("ix_damage_artifacts_artifact_type", "damage_artifacts", ["artifact_type"])
    op.create_index("ix_damage_artifacts_source_classification", "damage_artifacts", ["source_classification"])

    op.create_table(
        "damage_findings",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(), sa.ForeignKey("damage_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("geometry", JSONB),
        sa.Column("metrics", JSONB),
        sa.Column("district", sa.String(120)),
        sa.Column("customs_office", sa.String(200)),
        sa.Column("route_name", sa.String(200)),
        sa.Column("verification_status", analyst_verification_status, nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_damage_findings_run_id", "damage_findings", ["run_id"])
    op.create_index("ix_damage_findings_finding_type", "damage_findings", ["finding_type"])
    op.create_index("ix_damage_findings_severity", "damage_findings", ["severity"])
    op.create_index("ix_damage_findings_district", "damage_findings", ["district"])
    op.create_index("ix_damage_findings_customs_office", "damage_findings", ["customs_office"])
    op.create_index("ix_damage_findings_route_name", "damage_findings", ["route_name"])
    op.create_index("ix_damage_findings_verification_status", "damage_findings", ["verification_status"])

    op.create_table(
        "case_hypotheses",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", UUID(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", hypothesis_status, nullable=False, server_default="open"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_by_id", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by_id", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_case_hypotheses_case_id", "case_hypotheses", ["case_id"])
    op.create_index("ix_case_hypotheses_status", "case_hypotheses", ["status"])
    op.create_index("ix_case_hypotheses_created_by_id", "case_hypotheses", ["created_by_id"])

    op.create_table(
        "hypothesis_evidence_links",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("hypothesis_id", UUID(), sa.ForeignKey("case_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_ref_id", UUID(), sa.ForeignKey("kb_evidence_refs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", hypothesis_evidence_relation, nullable=False, server_default="context"),
        sa.Column("weight", sa.Float()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by_id", UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("hypothesis_id", "evidence_ref_id", name="uq_hypothesis_evidence_ref"),
    )
    op.create_index("ix_hypothesis_evidence_links_hypothesis_id", "hypothesis_evidence_links", ["hypothesis_id"])
    op.create_index("ix_hypothesis_evidence_links_evidence_ref_id", "hypothesis_evidence_links", ["evidence_ref_id"])
    op.create_index("ix_hypothesis_evidence_links_relation_type", "hypothesis_evidence_links", ["relation_type"])


def downgrade() -> None:
    op.drop_table("hypothesis_evidence_links")
    op.drop_table("case_hypotheses")
    op.drop_table("damage_findings")
    op.drop_table("damage_artifacts")
    op.drop_table("damage_runs")
    op.drop_table("trade_anomalies")
    op.drop_table("trade_facts")
    op.drop_table("trade_reports")
    op.drop_table("kb_evidence_refs")
    op.drop_table("kb_links")
    op.drop_table("kb_objects")

    op.execute("DROP TYPE IF EXISTS hypothesis_evidence_relation")
    op.execute("DROP TYPE IF EXISTS hypothesis_status")
    op.execute("DROP TYPE IF EXISTS provenance_owner_type")
    op.execute("DROP TYPE IF EXISTS damage_run_status")
    op.execute("DROP TYPE IF EXISTS trade_direction")
    op.execute("DROP TYPE IF EXISTS analyst_source_classification")
    op.execute("DROP TYPE IF EXISTS analyst_verification_status")
