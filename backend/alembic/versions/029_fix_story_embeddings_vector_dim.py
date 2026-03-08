"""Fix story_embeddings.embedding_vector dimension and index.

Revision ID: 029
Revises: 028
Create Date: 2026-02-04

Context:
- Earlier migrations created `embedding_vector vector(384)` (MiniLM era).
- A later auto-generated migration (d040fea4e3bf) accidentally dropped the column because
  the ORM model lacked the mapping at the time.
- The current runtime defaults to multilingual E5-Large embeddings (1024d).

This migration:
- Ensures pgvector extension exists
- Ensures `story_embeddings.embedding_vector` exists with dimension 1024
- Ensures an HNSW cosine index exists (`idx_story_embeddings_vector`)

If the existing column has a different dimension, it is replaced (existing embeddings are discarded).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # pgvector stores the dimension in `pg_attribute.atttypmod` (e.g., 1024 for vector(1024)).
    op.execute(
        """
        DO $$
        DECLARE
          current_dim integer;
        BEGIN
          SELECT NULLIF(a.atttypmod, -1) INTO current_dim
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE c.relname = 'story_embeddings'
            AND a.attname = 'embedding_vector'
            AND a.attnum > 0
            AND NOT a.attisdropped;

          IF current_dim IS NULL THEN
            EXECUTE 'ALTER TABLE story_embeddings ADD COLUMN embedding_vector vector(1024)';
          ELSIF current_dim <> 1024 THEN
            EXECUTE 'DROP INDEX IF EXISTS idx_story_embeddings_vector';
            EXECUTE 'ALTER TABLE story_embeddings DROP COLUMN embedding_vector';
            EXECUTE 'ALTER TABLE story_embeddings ADD COLUMN embedding_vector vector(1024)';
          END IF;

          -- Ensure the HNSW index exists for cosine distance search.
          EXECUTE 'CREATE INDEX IF NOT EXISTS idx_story_embeddings_vector ON story_embeddings USING hnsw (embedding_vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)';
        END
        $$;
        """
    )


def downgrade() -> None:
    # Best-effort downgrade back to 384d (legacy MiniLM).
    op.execute(
        """
        DO $$
        DECLARE
          current_dim integer;
        BEGIN
          SELECT NULLIF(a.atttypmod, -1) INTO current_dim
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          WHERE c.relname = 'story_embeddings'
            AND a.attname = 'embedding_vector'
            AND a.attnum > 0
            AND NOT a.attisdropped;

          IF current_dim IS NULL THEN
            RETURN;
          END IF;

          IF current_dim <> 384 THEN
            EXECUTE 'DROP INDEX IF EXISTS idx_story_embeddings_vector';
            EXECUTE 'ALTER TABLE story_embeddings DROP COLUMN embedding_vector';
            EXECUTE 'ALTER TABLE story_embeddings ADD COLUMN embedding_vector vector(384)';
            EXECUTE 'CREATE INDEX idx_story_embeddings_vector ON story_embeddings USING hnsw (embedding_vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)';
          END IF;
        END
        $$;
        """
    )
