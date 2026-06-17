"""phase7 notificationchannel LOG value

Revision ID: 029aed573f60
Revises: 4a175e31e136
Create Date: 2026-06-17 17:11:07.344118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '029aed573f60'
down_revision: Union[str, Sequence[str], None] = '4a175e31e136'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Offline fallback channel for the Phase 7 notification fan-out. Postgres-only;
    # on SQLite the channel column is plain VARCHAR.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notificationchannel ADD VALUE IF NOT EXISTS 'LOG'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot drop a single enum value; 'LOG' is left in place (harmless).
    pass
