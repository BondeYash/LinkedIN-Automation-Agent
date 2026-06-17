"""phase6 quality gates: review_notes + needs_review status

Revision ID: 4a175e31e136
Revises: 3be64b334355
Create Date: 2026-06-17 17:00:45.562658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a175e31e136'
down_revision: Union[str, Sequence[str], None] = '3be64b334355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New quality-gate value on the existing poststatus enum (Postgres native
    # enum). IF NOT EXISTS keeps re-runs safe; on SQLite this is a no-op since the
    # column is plain VARCHAR there.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE poststatus ADD VALUE IF NOT EXISTS 'NEEDS_REVIEW'")

    # Quality-gate findings for a flagged draft (NULL when the gates passed clean).
    op.add_column(
        "generated_posts",
        sa.Column("review_notes", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("generated_posts", "review_notes")
    # Note: Postgres cannot drop a single enum value; 'NEEDS_REVIEW' is left in
    # place on downgrade (harmless — nothing references it once rows are gone).
