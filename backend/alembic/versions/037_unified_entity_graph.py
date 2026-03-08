"""Unified entity graph - canonical hub linking.

Add enrichment columns to political_entities and linked_entity_id FK to
candidates, mp_performance, ministerial_positions, company_directors.

Revision ID: 037
Revises: 036
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add enrichment columns to political_entities --
    op.add_column("political_entities", sa.Column("biography", sa.Text()))
    op.add_column("political_entities", sa.Column("biography_source", sa.String(500)))
    op.add_column("political_entities", sa.Column("education", sa.String(255)))
    op.add_column("political_entities", sa.Column("education_institution", sa.String(255)))
    op.add_column("political_entities", sa.Column("age", sa.Integer()))
    op.add_column("political_entities", sa.Column("gender", sa.String(20)))
    op.add_column("political_entities", sa.Column("former_parties", JSONB))
    op.add_column("political_entities", sa.Column("current_position", sa.String(255)))
    op.add_column("political_entities", sa.Column("position_history", JSONB))

    # -- Add linked_entity_id FK to candidates --
    op.add_column(
        "candidates",
        sa.Column(
            "linked_entity_id",
            UUID(),
            sa.ForeignKey("political_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("candidates", sa.Column("entity_link_confidence", sa.Float()))
    op.create_index("ix_candidates_linked_entity_id", "candidates", ["linked_entity_id"])

    # -- Add linked_entity_id FK to mp_performance --
    op.add_column(
        "mp_performance",
        sa.Column(
            "linked_entity_id",
            UUID(),
            sa.ForeignKey("political_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("mp_performance", sa.Column("entity_link_confidence", sa.Float()))
    op.create_index("ix_mp_performance_linked_entity_id", "mp_performance", ["linked_entity_id"])

    # -- Add linked_entity_id FK to ministerial_positions --
    op.add_column(
        "ministerial_positions",
        sa.Column(
            "linked_entity_id",
            UUID(),
            sa.ForeignKey("political_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("ministerial_positions", sa.Column("entity_link_confidence", sa.Float()))
    op.create_index(
        "ix_ministerial_positions_linked_entity_id",
        "ministerial_positions",
        ["linked_entity_id"],
    )

    # -- Add linked_entity_id FK to company_directors --
    op.add_column(
        "company_directors",
        sa.Column(
            "linked_entity_id",
            UUID(),
            sa.ForeignKey("political_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("company_directors", sa.Column("entity_link_confidence", sa.Float()))
    op.create_index(
        "ix_company_directors_linked_entity_id",
        "company_directors",
        ["linked_entity_id"],
    )


def downgrade() -> None:
    # -- company_directors --
    op.drop_index("ix_company_directors_linked_entity_id", table_name="company_directors")
    op.drop_column("company_directors", "entity_link_confidence")
    op.drop_column("company_directors", "linked_entity_id")

    # -- ministerial_positions --
    op.drop_index("ix_ministerial_positions_linked_entity_id", table_name="ministerial_positions")
    op.drop_column("ministerial_positions", "entity_link_confidence")
    op.drop_column("ministerial_positions", "linked_entity_id")

    # -- mp_performance --
    op.drop_index("ix_mp_performance_linked_entity_id", table_name="mp_performance")
    op.drop_column("mp_performance", "entity_link_confidence")
    op.drop_column("mp_performance", "linked_entity_id")

    # -- candidates --
    op.drop_index("ix_candidates_linked_entity_id", table_name="candidates")
    op.drop_column("candidates", "entity_link_confidence")
    op.drop_column("candidates", "linked_entity_id")

    # -- political_entities --
    op.drop_column("political_entities", "position_history")
    op.drop_column("political_entities", "current_position")
    op.drop_column("political_entities", "former_parties")
    op.drop_column("political_entities", "gender")
    op.drop_column("political_entities", "age")
    op.drop_column("political_entities", "education_institution")
    op.drop_column("political_entities", "education")
    op.drop_column("political_entities", "biography_source")
    op.drop_column("political_entities", "biography")
