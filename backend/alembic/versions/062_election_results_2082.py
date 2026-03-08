"""election results 2082

Revision ID: 062
Revises: 061
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "election_candidates_2082",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("state_id", sa.Integer(), nullable=False),
        sa.Column("state_name", sa.String(100), nullable=False),
        sa.Column("district_cd", sa.Integer(), nullable=False),
        sa.Column("district_name", sa.String(100), nullable=False),
        sa.Column("constituency_no", sa.Integer(), nullable=False),
        sa.Column("election_type", sa.String(10), nullable=False, server_default="hor"),
        sa.Column("ecn_candidate_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(255), nullable=False),
        sa.Column("gender", sa.String(20)),
        sa.Column("age", sa.Integer()),
        sa.Column("party_name", sa.String(255), nullable=False),
        sa.Column("party_id", sa.Integer()),
        sa.Column("symbol_name", sa.String(100)),
        sa.Column("symbol_id", sa.Integer()),
        sa.Column("total_vote_received", sa.Integer(), server_default="0"),
        sa.Column("casted_vote", sa.Integer(), server_default="0"),
        sa.Column("total_voters", sa.Integer(), server_default="0"),
        sa.Column("rank", sa.Integer()),
        sa.Column("remarks", sa.Text()),
        sa.Column("is_winner", sa.Boolean(), server_default="false"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_ec2082_district_const", "election_candidates_2082", ["district_cd", "constituency_no", "election_type"])
    op.create_index("idx_ec2082_party", "election_candidates_2082", ["party_name"])
    op.create_index("idx_ec2082_state", "election_candidates_2082", ["state_id"])
    op.create_index("idx_ec2082_ecn_id", "election_candidates_2082", ["ecn_candidate_id"], unique=True)
    op.create_index("idx_ec2082_votes", "election_candidates_2082", ["total_vote_received"])

    op.create_table(
        "election_party_summary_2082",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("election_type", sa.String(10), nullable=False),
        sa.Column("state_id", sa.Integer()),
        sa.Column("party_name", sa.String(255), nullable=False),
        sa.Column("party_id", sa.Integer()),
        sa.Column("seats_won", sa.Integer(), server_default="0"),
        sa.Column("seats_leading", sa.Integer(), server_default="0"),
        sa.Column("total_votes", sa.Integer(), server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_eps2082_type_state", "election_party_summary_2082", ["election_type", "state_id"])
    op.create_index("idx_eps2082_party", "election_party_summary_2082", ["party_name"])

    op.create_table(
        "election_scrape_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("constituencies_scraped", sa.Integer(), server_default="0"),
        sa.Column("candidates_updated", sa.Integer(), server_default="0"),
        sa.Column("error", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("election_scrape_log")
    op.drop_table("election_party_summary_2082")
    op.drop_table("election_candidates_2082")
