"""phase11 notificationchannel WHATSAPP value

Revision ID: a1f2c3d4e5f6
Revises: 029aed573f60
Create Date: 2026-06-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '029aed573f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # WhatsApp (WAHA) notification channel for the Phase 11 automation. Postgres-only;
    # on SQLite the channel column is plain VARCHAR.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notificationchannel ADD VALUE IF NOT EXISTS 'WHATSAPP'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot drop a single enum value; 'WHATSAPP' is left in place (harmless).
    pass
