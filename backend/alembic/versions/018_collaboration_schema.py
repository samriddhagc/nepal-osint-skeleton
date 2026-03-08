"""Collaboration schema - teams, cases, verification, watchlists, analyst metrics.

Revision ID: 018
Revises: 017
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUM types
    op.execute("CREATE TYPE team_role AS ENUM ('owner', 'admin', 'member', 'viewer')")
    op.execute("CREATE TYPE case_status AS ENUM ('draft', 'active', 'review', 'closed', 'archived')")
    op.execute("CREATE TYPE case_priority AS ENUM ('critical', 'high', 'medium', 'low')")
    op.execute("CREATE TYPE case_visibility AS ENUM ('public', 'team', 'private')")
    op.execute("CREATE TYPE evidence_type AS ENUM ('story', 'entity', 'document', 'link', 'note')")
    op.execute("CREATE TYPE verification_status AS ENUM ('pending', 'verified', 'rejected', 'needs_info', 'expired')")
    op.execute("CREATE TYPE verifiable_type AS ENUM ('story', 'entity', 'entity_link', 'case_evidence', 'classification', 'location')")
    op.execute("CREATE TYPE vote_choice AS ENUM ('agree', 'disagree', 'abstain', 'needs_info')")
    op.execute("CREATE TYPE watchlist_scope AS ENUM ('personal', 'team', 'public')")
    op.execute("CREATE TYPE watchable_type AS ENUM ('entity', 'keyword', 'location', 'organization', 'person', 'topic')")
    op.execute("CREATE TYPE alert_frequency AS ENUM ('realtime', 'hourly', 'daily', 'weekly')")
    op.execute("CREATE TYPE activity_type AS ENUM ('case_created', 'case_updated', 'case_closed', 'evidence_added', 'case_comment', 'verification_requested', 'verification_voted', 'verification_resolved', 'entity_created', 'entity_updated', 'entity_linked', 'story_annotated', 'story_categorized', 'story_flagged', 'mention_sent', 'mention_received', 'team_joined', 'watchlist_created', 'watchlist_match', 'note_created', 'login')")
    op.execute("CREATE TYPE annotation_type AS ENUM ('highlight', 'comment', 'tag', 'correction', 'link', 'flag')")
    op.execute("CREATE TYPE annotatable_type AS ENUM ('story', 'entity', 'document', 'case')")
    op.execute("CREATE TYPE note_visibility AS ENUM ('private', 'team', 'public')")

    # Create teams table
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("specialization", sa.String(50), nullable=True),
        sa.Column("is_public", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("settings", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_teams_name", "teams", ["name"])
    op.create_index("idx_teams_slug", "teams", ["slug"])

    # Create team_memberships table
    op.create_table(
        "team_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", postgresql.ENUM("owner", "admin", "member", "viewer", name="team_role", create_type=False), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )
    op.create_index("idx_team_memberships_team", "team_memberships", ["team_id"])
    op.create_index("idx_team_memberships_user", "team_memberships", ["user_id"])
    op.create_index("idx_team_memberships_user_active", "team_memberships", ["user_id", "is_active"])

    # Create cases table
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", postgresql.ENUM("draft", "active", "review", "closed", "archived", name="case_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("priority", postgresql.ENUM("critical", "high", "medium", "low", name="case_priority", create_type=False), nullable=False, server_default="medium"),
        sa.Column("visibility", postgresql.ENUM("public", "team", "private", name="case_visibility", create_type=False), nullable=False, server_default="public"),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hypothesis", sa.Text, nullable=True),
        sa.Column("conclusion", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_cases_title", "cases", ["title"])
    op.create_index("idx_cases_status", "cases", ["status"])
    op.create_index("idx_cases_priority", "cases", ["priority"])
    op.create_index("idx_cases_visibility", "cases", ["visibility"])
    op.create_index("idx_cases_created_by", "cases", ["created_by_id"])
    op.create_index("idx_cases_assigned_to", "cases", ["assigned_to_id"])
    op.create_index("idx_cases_team", "cases", ["team_id"])
    op.create_index("idx_cases_status_priority", "cases", ["status", "priority"])
    op.create_index("idx_cases_created_by_status", "cases", ["created_by_id", "status"])
    op.create_index("idx_cases_team_status", "cases", ["team_id", "status"])

    # Create case_evidence table
    op.create_table(
        "case_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", postgresql.ENUM("story", "entity", "document", "link", "note", name="evidence_type", create_type=False), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("reference_url", sa.Text, nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("relevance_notes", sa.Text, nullable=True),
        sa.Column("is_key_evidence", sa.Boolean, default=False),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("added_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_case_evidence_case", "case_evidence", ["case_id"])
    op.create_index("idx_case_evidence_type", "case_evidence", ["evidence_type"])
    op.create_index("idx_case_evidence_type_ref", "case_evidence", ["evidence_type", "reference_id"])

    # Create case_comments table
    op.create_table(
        "case_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_comment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mentions", postgresql.JSONB, nullable=True),
        sa.Column("is_edited", sa.Boolean, default=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_case_comments_case", "case_comments", ["case_id"])
    op.create_index("idx_case_comments_parent", "case_comments", ["parent_comment_id"])
    op.create_index("idx_case_comments_author", "case_comments", ["author_id"])

    # Create verification_requests table
    op.create_table(
        "verification_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_type", postgresql.ENUM("story", "entity", "entity_link", "case_evidence", "classification", "location", name="verifiable_type", create_type=False), nullable=False),
        sa.Column("item_id", sa.String(100), nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        sa.Column("source_urls", postgresql.JSONB, nullable=True),
        sa.Column("status", postgresql.ENUM("pending", "verified", "rejected", "needs_info", "expired", name="verification_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("required_votes", sa.Integer, nullable=False, server_default="3"),
        sa.Column("consensus_threshold", sa.Float, nullable=False, server_default="0.67"),
        sa.Column("priority", sa.String(20), nullable=True, server_default="normal"),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_verdict", sa.String(50), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("agree_count", sa.Integer, server_default="0"),
        sa.Column("disagree_count", sa.Integer, server_default="0"),
        sa.Column("abstain_count", sa.Integer, server_default="0"),
        sa.Column("needs_info_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_verification_item", "verification_requests", ["item_type", "item_id"])
    op.create_index("idx_verification_status", "verification_requests", ["status"])
    op.create_index("idx_verification_status_created", "verification_requests", ["status", "created_at"])
    op.create_index("idx_verification_pending_priority", "verification_requests", ["status", "priority", "created_at"])
    op.create_index("idx_verification_requested_by", "verification_requests", ["requested_by_id"])

    # Create verification_votes table
    op.create_table(
        "verification_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("choice", postgresql.ENUM("agree", "disagree", "abstain", "needs_info", name="vote_choice", create_type=False), nullable=False),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("supporting_evidence", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", "voter_id", name="uq_verification_vote"),
    )
    op.create_index("idx_verification_votes_request", "verification_votes", ["request_id"])
    op.create_index("idx_verification_votes_voter", "verification_votes", ["voter_id"])

    # Create watchlists table
    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scope", postgresql.ENUM("personal", "team", "public", name="watchlist_scope", create_type=False), nullable=False, server_default="personal"),
        sa.Column("alert_frequency", postgresql.ENUM("realtime", "hourly", "daily", "weekly", name="alert_frequency", create_type=False), nullable=False, server_default="daily"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("min_relevance_score", sa.Float, nullable=True),
        sa.Column("categories_filter", postgresql.JSONB, nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_match_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_matches", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_watchlist_name", "watchlists", ["name"])
    op.create_index("idx_watchlist_scope", "watchlists", ["scope"])
    op.create_index("idx_watchlist_owner", "watchlists", ["owner_id"])
    op.create_index("idx_watchlist_owner_active", "watchlists", ["owner_id", "is_active"])
    op.create_index("idx_watchlist_team_active", "watchlists", ["team_id", "is_active"])

    # Create watchlist_items table
    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", postgresql.ENUM("entity", "keyword", "location", "organization", "person", "topic", name="watchable_type", create_type=False), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("aliases", postgresql.JSONB, nullable=True),
        sa.Column("case_sensitive", sa.Boolean, default=False),
        sa.Column("exact_match", sa.Boolean, default=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("match_count", sa.Integer, server_default="0"),
        sa.Column("last_match_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "item_type", "value", name="uq_watchlist_item"),
    )
    op.create_index("idx_watchlist_items_watchlist", "watchlist_items", ["watchlist_id"])
    op.create_index("idx_watchlist_item_type", "watchlist_items", ["item_type"])
    op.create_index("idx_watchlist_item_value", "watchlist_items", ["value"])
    op.create_index("idx_watchlist_item_type_value", "watchlist_items", ["item_type", "value"])

    # Create watchlist_matches table
    op.create_table(
        "watchlist_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlist_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_story_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("matched_text", sa.Text, nullable=True),
        sa.Column("match_context", sa.Text, nullable=True),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("is_alerted", sa.Boolean, default=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_dismissed", sa.Boolean, default=False),
        sa.Column("dismissed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_watchlist_match_watchlist", "watchlist_matches", ["watchlist_id"])
    op.create_index("idx_watchlist_match_item", "watchlist_matches", ["item_id"])
    op.create_index("idx_watchlist_match_story", "watchlist_matches", ["matched_story_id"])
    op.create_index("idx_watchlist_match_alert", "watchlist_matches", ["watchlist_id", "is_alerted"])

    # Create analyst_metrics table
    op.create_table(
        "analyst_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("total_cases", sa.Integer, server_default="0"),
        sa.Column("cases_closed", sa.Integer, server_default="0"),
        sa.Column("evidence_added", sa.Integer, server_default="0"),
        sa.Column("comments_posted", sa.Integer, server_default="0"),
        sa.Column("verifications_requested", sa.Integer, server_default="0"),
        sa.Column("verifications_voted", sa.Integer, server_default="0"),
        sa.Column("verifications_correct", sa.Integer, server_default="0"),
        sa.Column("verification_accuracy", sa.Float, nullable=True),
        sa.Column("entities_created", sa.Integer, server_default="0"),
        sa.Column("entities_updated", sa.Integer, server_default="0"),
        sa.Column("entity_links_created", sa.Integer, server_default="0"),
        sa.Column("stories_annotated", sa.Integer, server_default="0"),
        sa.Column("notes_created", sa.Integer, server_default="0"),
        sa.Column("mentions_sent", sa.Integer, server_default="0"),
        sa.Column("mentions_received", sa.Integer, server_default="0"),
        sa.Column("active_days", sa.Integer, server_default="0"),
        sa.Column("current_streak", sa.Integer, server_default="0"),
        sa.Column("longest_streak", sa.Integer, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("badges", postgresql.JSONB, nullable=True),
        sa.Column("reputation_score", sa.Integer, server_default="0"),
        sa.Column("threat_score", sa.Integer, server_default="0"),
        sa.Column("economic_score", sa.Integer, server_default="0"),
        sa.Column("political_score", sa.Integer, server_default="0"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_analyst_metrics_user", "analyst_metrics", ["user_id"])
    op.create_index("idx_analyst_metrics_reputation", "analyst_metrics", ["reputation_score"])
    op.create_index("idx_analyst_metrics_accuracy", "analyst_metrics", ["verification_accuracy"])

    # Create analyst_activities table
    op.create_table(
        "analyst_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", postgresql.ENUM("case_created", "case_updated", "case_closed", "evidence_added", "case_comment", "verification_requested", "verification_voted", "verification_resolved", "entity_created", "entity_updated", "entity_linked", "story_annotated", "story_categorized", "story_flagged", "mention_sent", "mention_received", "team_joined", "watchlist_created", "watchlist_match", "note_created", "login", name="activity_type", create_type=False), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("is_public", sa.Boolean, default=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mentioned_user_ids", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("idx_activity_user", "analyst_activities", ["user_id"])
    op.create_index("idx_activity_user_created", "analyst_activities", ["user_id", "created_at"])
    op.create_index("idx_activity_team_created", "analyst_activities", ["team_id", "created_at"])
    op.create_index("idx_activity_type_created", "analyst_activities", ["activity_type", "created_at"])
    op.create_index("idx_activity_target", "analyst_activities", ["target_type", "target_id"])

    # Create annotations table
    op.create_table(
        "annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", postgresql.ENUM("story", "entity", "document", "case", name="annotatable_type", create_type=False), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("annotation_type", postgresql.ENUM("highlight", "comment", "tag", "correction", "link", "flag", name="annotation_type", create_type=False), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("start_offset", sa.Integer, nullable=True),
        sa.Column("end_offset", sa.Integer, nullable=True),
        sa.Column("selected_text", sa.Text, nullable=True),
        sa.Column("linked_type", sa.String(50), nullable=True),
        sa.Column("linked_id", sa.String(100), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility", postgresql.ENUM("private", "team", "public", name="note_visibility", create_type=False), nullable=False, server_default="public"),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_resolved", sa.Boolean, default=False),
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_annotation_target", "annotations", ["target_type", "target_id"])
    op.create_index("idx_annotation_author", "annotations", ["author_id", "created_at"])
    op.create_index("idx_annotation_type", "annotations", ["annotation_type"])

    # Create analyst_notes table
    op.create_table(
        "analyst_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("linked_items", postgresql.JSONB, nullable=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility", postgresql.ENUM("private", "team", "public", name="note_visibility", create_type=False), nullable=False, server_default="private"),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_pinned", sa.Boolean, default=False),
        sa.Column("is_archived", sa.Boolean, default=False),
        sa.Column("mentions", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_note_title", "analyst_notes", ["title"])
    op.create_index("idx_note_author", "analyst_notes", ["author_id"])
    op.create_index("idx_note_author_archived", "analyst_notes", ["author_id", "is_archived"])
    op.create_index("idx_note_team_archived", "analyst_notes", ["team_id", "is_archived"])
    op.create_index("idx_note_case", "analyst_notes", ["case_id"])

    # Create source_reliability table
    op.create_table(
        "source_reliability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False, unique=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("reliability_rating", sa.String(1), nullable=False, server_default="E"),
        sa.Column("credibility_rating", sa.Integer, nullable=False, server_default="5"),
        sa.Column("confidence_score", sa.Integer, nullable=False, server_default="50"),
        sa.Column("total_stories", sa.Integer, server_default="0"),
        sa.Column("verified_true", sa.Integer, server_default="0"),
        sa.Column("verified_false", sa.Integer, server_default="0"),
        sa.Column("corrections_needed", sa.Integer, server_default="0"),
        sa.Column("total_ratings", sa.Integer, server_default="0"),
        sa.Column("average_user_rating", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("last_rated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_source_reliability_source", "source_reliability", ["source_id"])
    op.create_index("idx_source_reliability_rating", "source_reliability", ["reliability_rating", "confidence_score"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("source_reliability")
    op.drop_table("analyst_notes")
    op.drop_table("annotations")
    op.drop_table("analyst_activities")
    op.drop_table("analyst_metrics")
    op.drop_table("watchlist_matches")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_table("verification_votes")
    op.drop_table("verification_requests")
    op.drop_table("case_comments")
    op.drop_table("case_evidence")
    op.drop_table("cases")
    op.drop_table("team_memberships")
    op.drop_table("teams")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS note_visibility")
    op.execute("DROP TYPE IF EXISTS annotatable_type")
    op.execute("DROP TYPE IF EXISTS annotation_type")
    op.execute("DROP TYPE IF EXISTS activity_type")
    op.execute("DROP TYPE IF EXISTS alert_frequency")
    op.execute("DROP TYPE IF EXISTS watchable_type")
    op.execute("DROP TYPE IF EXISTS watchlist_scope")
    op.execute("DROP TYPE IF EXISTS vote_choice")
    op.execute("DROP TYPE IF EXISTS verifiable_type")
    op.execute("DROP TYPE IF EXISTS verification_status")
    op.execute("DROP TYPE IF EXISTS evidence_type")
    op.execute("DROP TYPE IF EXISTS case_visibility")
    op.execute("DROP TYPE IF EXISTS case_priority")
    op.execute("DROP TYPE IF EXISTS case_status")
    op.execute("DROP TYPE IF EXISTS team_role")
