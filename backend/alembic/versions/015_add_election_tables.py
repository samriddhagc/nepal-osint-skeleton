"""Add election system tables.

Revision ID: 015
Revises: 014
Create Date: 2026-01-29

Creates tables for:
- elections: Election metadata (2074, 2079, 2082 BS)
- constituencies: 165 electoral constituencies
- candidates: All candidates per constituency
- user_constituency_watchlist: User-tracked constituencies
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create elections table
    op.create_table(
        "elections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("year_bs", sa.Integer, nullable=False, unique=True),
        sa.Column("year_ad", sa.Integer, nullable=False),
        sa.Column("election_type", sa.String(50), nullable=False, default="parliamentary"),
        sa.Column("status", sa.String(50), nullable=False, default="completed"),
        sa.Column("total_constituencies", sa.Integer, default=165),
        sa.Column("total_registered_voters", sa.Integer),
        sa.Column("total_votes_cast", sa.Integer),
        sa.Column("turnout_pct", sa.Float),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_elections_year_bs", "elections", ["year_bs"])
    op.create_index("idx_elections_status", "elections", ["status"])

    # Create constituencies table
    op.create_table(
        "constituencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("constituency_code", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_ne", sa.String(255)),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("province", sa.String(100), nullable=False),
        sa.Column("province_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("total_registered_voters", sa.Integer),
        sa.Column("total_votes_cast", sa.Integer),
        sa.Column("turnout_pct", sa.Float),
        sa.Column("valid_votes", sa.Integer),
        sa.Column("invalid_votes", sa.Integer),
        sa.Column("winner_candidate_id", postgresql.UUID(as_uuid=True)),  # FK added later
        sa.Column("winner_party", sa.String(255)),
        sa.Column("winner_votes", sa.Integer),
        sa.Column("winner_margin", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_constituencies_election_code", "constituencies", ["election_id", "constituency_code"], unique=True)
    op.create_index("idx_constituencies_election_district", "constituencies", ["election_id", "district"])
    op.create_index("idx_constituencies_election_province", "constituencies", ["election_id", "province_id"])
    op.create_index("idx_constituencies_status", "constituencies", ["status"])
    op.create_index("idx_constituencies_winner_party", "constituencies", ["winner_party"])

    # Create candidates table
    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("constituency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("constituencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_ne", sa.String(255)),
        sa.Column("party", sa.String(255), nullable=False),
        sa.Column("party_ne", sa.String(255)),
        sa.Column("votes", sa.Integer, default=0),
        sa.Column("vote_pct", sa.Float, default=0.0),
        sa.Column("rank", sa.Integer, default=0),
        sa.Column("is_winner", sa.Boolean, default=False),
        sa.Column("photo_url", sa.String(500)),
        sa.Column("age", sa.Integer),
        sa.Column("gender", sa.String(20)),
        sa.Column("education", sa.String(255)),
        sa.Column("education_institution", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_candidates_constituency", "candidates", ["constituency_id"])
    op.create_index("idx_candidates_election_party", "candidates", ["election_id", "party"])
    op.create_index("idx_candidates_external_id", "candidates", ["election_id", "external_id"], unique=True)
    op.create_index("idx_candidates_is_winner", "candidates", ["is_winner"])

    # Add FK from constituencies.winner_candidate_id to candidates.id
    op.create_foreign_key(
        "fk_constituencies_winner_candidate",
        "constituencies",
        "candidates",
        ["winner_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create user watchlist table
    op.create_table(
        "user_constituency_watchlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("constituency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("constituencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_level", sa.String(20), default="medium"),
        sa.Column("notes", sa.Text),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_watchlist_user", "user_constituency_watchlist", ["user_id"])
    op.create_index("idx_watchlist_user_constituency", "user_constituency_watchlist", ["user_id", "constituency_id"], unique=True)
    op.create_index("idx_watchlist_active", "user_constituency_watchlist", ["is_active"])


def downgrade() -> None:
    # Drop user watchlist table
    op.drop_index("idx_watchlist_active", "user_constituency_watchlist")
    op.drop_index("idx_watchlist_user_constituency", "user_constituency_watchlist")
    op.drop_index("idx_watchlist_user", "user_constituency_watchlist")
    op.drop_table("user_constituency_watchlist")

    # Drop FK from constituencies to candidates
    op.drop_constraint("fk_constituencies_winner_candidate", "constituencies", type_="foreignkey")

    # Drop candidates table
    op.drop_index("idx_candidates_is_winner", "candidates")
    op.drop_index("idx_candidates_external_id", "candidates")
    op.drop_index("idx_candidates_election_party", "candidates")
    op.drop_index("idx_candidates_constituency", "candidates")
    op.drop_table("candidates")

    # Drop constituencies table
    op.drop_index("idx_constituencies_winner_party", "constituencies")
    op.drop_index("idx_constituencies_status", "constituencies")
    op.drop_index("idx_constituencies_election_province", "constituencies")
    op.drop_index("idx_constituencies_election_district", "constituencies")
    op.drop_index("idx_constituencies_election_code", "constituencies")
    op.drop_table("constituencies")

    # Drop elections table
    op.drop_index("idx_elections_status", "elections")
    op.drop_index("idx_elections_year_bs", "elections")
    op.drop_table("elections")
