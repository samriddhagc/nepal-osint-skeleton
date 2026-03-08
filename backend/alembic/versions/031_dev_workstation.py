"""Dev workstation tables: audit log, corrections, API metrics, notifications, training runs.

Revision ID: 031
Revises: 030
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Admin Audit Log (7-day retention) ──
    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(100)),
        sa.Column("target_id", sa.String(255)),
        sa.Column("details", JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_audit_log_user", "admin_audit_log", ["user_id"])
    op.create_index("idx_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("idx_audit_log_created", "admin_audit_log", ["created_at"])
    op.create_index("idx_audit_log_target", "admin_audit_log", ["target_type", "target_id"])

    # ── Candidate Corrections (with rollback support) ──
    op.create_table(
        "candidate_corrections",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_external_id", sa.String(50), nullable=False),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("submitted_by", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("reviewed_by", UUID(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
        sa.Column("rolled_back_by", UUID(), sa.ForeignKey("users.id")),
        sa.Column("rollback_reason", sa.Text),
        sa.Column("batch_id", UUID()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_corrections_status", "candidate_corrections", ["status"])
    op.create_index("idx_corrections_candidate", "candidate_corrections", ["candidate_external_id"])
    op.create_index("idx_corrections_submitted_by", "candidate_corrections", ["submitted_by"])
    op.create_index("idx_corrections_batch", "candidate_corrections", ["batch_id"])

    # ── API Metrics (for monitoring dashboard) ──
    op.create_table(
        "api_metrics",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("response_time_ms", sa.Integer, nullable=False),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_api_metrics_endpoint", "api_metrics", ["endpoint", "recorded_at"])
    op.create_index("idx_api_metrics_time", "api_metrics", ["recorded_at"])

    # ── User Notifications (in-app) ──
    op.create_table(
        "user_notifications",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("data", JSONB),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("FALSE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_notifications_user", "user_notifications", ["user_id", "is_read", "created_at"])

    # ── Training Runs (ML training progress tracking) ──
    op.create_table(
        "training_runs",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_name", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("current_epoch", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("total_epochs", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("current_loss", sa.Float),
        sa.Column("best_loss", sa.Float),
        sa.Column("parameters", JSONB),
        sa.Column("reason", sa.Text),
        sa.Column("result_accuracy", sa.Float),
        sa.Column("result_metrics", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("started_by", UUID(), sa.ForeignKey("users.id")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("estimated_duration_sec", sa.Integer),
        sa.Column("result_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_training_runs_model", "training_runs", ["model_name"])
    op.create_index("idx_training_runs_status", "training_runs", ["status"])


def downgrade() -> None:
    op.drop_table("training_runs")
    op.drop_table("user_notifications")
    op.drop_table("api_metrics")
    op.drop_table("candidate_corrections")
    op.drop_table("admin_audit_log")
