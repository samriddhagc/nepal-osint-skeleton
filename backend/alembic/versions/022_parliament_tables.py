"""Add parliament data tables for MP Performance Index.

Revision ID: 022
Revises: 021
Create Date: 2026-01-31

Creates tables for:
- mp_performance: MP profiles with performance scores (cached from parliament.gov.np)
- parliament_bills: Bills with status tracking
- bill_sponsors: Many-to-many for bill sponsors
- parliament_committees: Committee metadata
- committee_memberships: MP committee roles and attendance
- parliament_questions: Parliamentary questions asked/answered
- session_attendance: Daily session attendance records
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create mp_performance table (core MP data with scores)
    op.create_table(
        "mp_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mp_id", sa.String(50), unique=True, nullable=False),  # Parliament website ID

        # Identity
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_ne", sa.String(255)),
        sa.Column("party", sa.String(100)),
        sa.Column("constituency", sa.String(100)),
        sa.Column("province_id", sa.Integer),
        sa.Column("election_type", sa.String(20)),  # 'fptp' or 'pr'
        sa.Column("chamber", sa.String(10)),  # 'hor' or 'na'
        sa.Column("term", sa.String(20)),  # e.g., '2079-2084'
        sa.Column("photo_url", sa.Text),

        # Candidate linking
        sa.Column("linked_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("link_confidence", sa.Float),

        # Legislative Productivity (30%)
        sa.Column("bills_introduced", sa.Integer, default=0),
        sa.Column("bills_passed", sa.Integer, default=0),
        sa.Column("bills_pending", sa.Integer, default=0),
        sa.Column("amendments_proposed", sa.Integer, default=0),
        sa.Column("legislative_score", sa.Float, default=0.0),
        sa.Column("legislative_percentile", sa.Integer),

        # Participation (25%)
        sa.Column("sessions_total", sa.Integer, default=0),
        sa.Column("sessions_attended", sa.Integer, default=0),
        sa.Column("session_attendance_pct", sa.Float),
        sa.Column("voting_participation_pct", sa.Float),
        sa.Column("participation_score", sa.Float, default=0.0),
        sa.Column("participation_percentile", sa.Integer),

        # Accountability (25%)
        sa.Column("questions_asked", sa.Integer, default=0),
        sa.Column("questions_answered", sa.Integer, default=0),
        sa.Column("motions_proposed", sa.Integer, default=0),
        sa.Column("resolutions_proposed", sa.Integer, default=0),
        sa.Column("accountability_score", sa.Float, default=0.0),
        sa.Column("accountability_percentile", sa.Integer),

        # Committee Work (20%)
        sa.Column("committee_memberships", sa.Integer, default=0),
        sa.Column("committee_leadership_roles", sa.Integer, default=0),
        sa.Column("committee_attendance_pct", sa.Float),
        sa.Column("reports_contributed", sa.Integer, default=0),
        sa.Column("committee_score", sa.Float, default=0.0),
        sa.Column("committee_percentile", sa.Integer),

        # Composite Score
        sa.Column("performance_score", sa.Float, default=0.0),
        sa.Column("performance_percentile", sa.Integer),
        sa.Column("performance_tier", sa.String(20)),  # 'top10', 'above_avg', etc.

        # Peer group rankings
        sa.Column("peer_group", sa.String(50)),
        sa.Column("peer_rank", sa.Integer),
        sa.Column("peer_total", sa.Integer),

        # Metadata
        sa.Column("is_minister", sa.Boolean, default=False),
        sa.Column("ministry_portfolio", sa.String(255)),
        sa.Column("is_current_member", sa.Boolean, default=True),

        sa.Column("scraped_at", sa.DateTime(timezone=True)),
        sa.Column("score_updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_mp_performance_name", "mp_performance", ["name_en", "name_ne"])
    op.create_index("idx_mp_performance_linked", "mp_performance", ["linked_candidate_id"])
    op.create_index("idx_mp_performance_score", "mp_performance", ["performance_score"])
    op.create_index("idx_mp_performance_peer", "mp_performance", ["peer_group", "peer_rank"])
    op.create_index("idx_mp_performance_chamber", "mp_performance", ["chamber"])
    op.create_index("idx_mp_performance_party", "mp_performance", ["party"])

    # Create parliament_bills table
    op.create_table(
        "parliament_bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(100), unique=True),  # Bill number from parliament

        sa.Column("title_en", sa.Text, nullable=False),
        sa.Column("title_ne", sa.Text),

        sa.Column("bill_type", sa.String(50)),  # 'government', 'private_member', 'money', 'amendment'
        sa.Column("status", sa.String(50)),  # 'registered', 'first_reading', 'committee', etc.

        sa.Column("presented_date", sa.Date),
        sa.Column("passed_date", sa.Date),

        sa.Column("presenting_mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="SET NULL")),
        sa.Column("ministry", sa.String(200)),  # For govt bills

        sa.Column("summary", sa.Text),
        sa.Column("pdf_url", sa.Text),

        sa.Column("chamber", sa.String(10)),  # 'hor' or 'na'
        sa.Column("term", sa.String(20)),

        sa.Column("scraped_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_bills_status", "parliament_bills", ["status", "presented_date"])
    op.create_index("idx_bills_mp", "parliament_bills", ["presenting_mp_id"])
    op.create_index("idx_bills_chamber", "parliament_bills", ["chamber"])
    op.create_index("idx_bills_type", "parliament_bills", ["bill_type"])

    # Create bill_sponsors table (many-to-many)
    op.create_table(
        "bill_sponsors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parliament_bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sponsor_type", sa.String(20)),  # 'primary', 'co-sponsor', 'supporter'
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_bill_sponsors_bill", "bill_sponsors", ["bill_id"])
    op.create_index("idx_bill_sponsors_mp", "bill_sponsors", ["mp_id"])
    op.create_unique_constraint("uq_bill_sponsors", "bill_sponsors", ["bill_id", "mp_id"])

    # Create parliament_committees table
    op.create_table(
        "parliament_committees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(100), unique=True),

        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_ne", sa.String(255)),

        sa.Column("committee_type", sa.String(50)),  # 'thematic', 'procedural', 'special', 'joint'
        sa.Column("chamber", sa.String(10)),  # 'hor', 'na', 'joint'
        sa.Column("term", sa.String(20)),

        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, default=True),

        sa.Column("total_meetings", sa.Integer, default=0),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_committees_chamber", "parliament_committees", ["chamber"])
    op.create_index("idx_committees_active", "parliament_committees", ["is_active"])

    # Create committee_memberships table
    op.create_table(
        "committee_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("committee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parliament_committees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="CASCADE"), nullable=False),

        sa.Column("role", sa.String(50), nullable=False),  # 'chair', 'vice_chair', 'member'

        sa.Column("meetings_total", sa.Integer, default=0),
        sa.Column("meetings_attended", sa.Integer, default=0),
        sa.Column("attendance_pct", sa.Float),

        sa.Column("joined_date", sa.Date),
        sa.Column("left_date", sa.Date),
        sa.Column("is_current", sa.Boolean, default=True),
    )
    op.create_index("idx_committee_memberships_committee", "committee_memberships", ["committee_id"])
    op.create_index("idx_committee_memberships_mp", "committee_memberships", ["mp_id"])
    op.create_index("idx_committee_memberships_role", "committee_memberships", ["role"])
    op.create_unique_constraint("uq_committee_membership", "committee_memberships", ["committee_id", "mp_id", "joined_date"])

    # Create parliament_questions table
    op.create_table(
        "parliament_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(100), unique=True),

        sa.Column("mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="CASCADE")),

        sa.Column("question_type", sa.String(50)),  # 'zero_hour', 'special_hour', 'written', 'starred'
        sa.Column("question_text", sa.Text),
        sa.Column("question_date", sa.Date),

        sa.Column("answered", sa.Boolean, default=False),
        sa.Column("answered_by_mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="SET NULL")),
        sa.Column("answer_date", sa.Date),

        sa.Column("ministry_addressed", sa.String(200)),

        sa.Column("scraped_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_questions_mp", "parliament_questions", ["mp_id"])
    op.create_index("idx_questions_date", "parliament_questions", ["question_date"])
    op.create_index("idx_questions_type", "parliament_questions", ["question_type"])

    # Create session_attendance table
    op.create_table(
        "session_attendance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mp_performance.id", ondelete="CASCADE")),

        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("session_type", sa.String(50)),  # 'plenary', 'special', 'budget'

        sa.Column("present", sa.Boolean, nullable=False),

        sa.Column("chamber", sa.String(10)),
        sa.Column("term", sa.String(20)),

        sa.Column("scraped_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_attendance_mp", "session_attendance", ["mp_id"])
    op.create_index("idx_attendance_date", "session_attendance", ["session_date"])
    op.create_unique_constraint("uq_session_attendance", "session_attendance", ["mp_id", "session_date", "session_type"])


def downgrade() -> None:
    # Drop session_attendance
    op.drop_constraint("uq_session_attendance", "session_attendance", type_="unique")
    op.drop_index("idx_attendance_date", "session_attendance")
    op.drop_index("idx_attendance_mp", "session_attendance")
    op.drop_table("session_attendance")

    # Drop parliament_questions
    op.drop_index("idx_questions_type", "parliament_questions")
    op.drop_index("idx_questions_date", "parliament_questions")
    op.drop_index("idx_questions_mp", "parliament_questions")
    op.drop_table("parliament_questions")

    # Drop committee_memberships
    op.drop_constraint("uq_committee_membership", "committee_memberships", type_="unique")
    op.drop_index("idx_committee_memberships_role", "committee_memberships")
    op.drop_index("idx_committee_memberships_mp", "committee_memberships")
    op.drop_index("idx_committee_memberships_committee", "committee_memberships")
    op.drop_table("committee_memberships")

    # Drop parliament_committees
    op.drop_index("idx_committees_active", "parliament_committees")
    op.drop_index("idx_committees_chamber", "parliament_committees")
    op.drop_table("parliament_committees")

    # Drop bill_sponsors
    op.drop_constraint("uq_bill_sponsors", "bill_sponsors", type_="unique")
    op.drop_index("idx_bill_sponsors_mp", "bill_sponsors")
    op.drop_index("idx_bill_sponsors_bill", "bill_sponsors")
    op.drop_table("bill_sponsors")

    # Drop parliament_bills
    op.drop_index("idx_bills_type", "parliament_bills")
    op.drop_index("idx_bills_chamber", "parliament_bills")
    op.drop_index("idx_bills_mp", "parliament_bills")
    op.drop_index("idx_bills_status", "parliament_bills")
    op.drop_table("parliament_bills")

    # Drop mp_performance
    op.drop_index("idx_mp_performance_party", "mp_performance")
    op.drop_index("idx_mp_performance_chamber", "mp_performance")
    op.drop_index("idx_mp_performance_peer", "mp_performance")
    op.drop_index("idx_mp_performance_score", "mp_performance")
    op.drop_index("idx_mp_performance_linked", "mp_performance")
    op.drop_index("idx_mp_performance_name", "mp_performance")
    op.drop_table("mp_performance")
