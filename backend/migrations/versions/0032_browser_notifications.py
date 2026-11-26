"""browser notifications

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-26 11:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Browser notifications (spec #145, #148): the switches on My account.
    for name in ("chat_notifications", "tiktok_alerts"):
        op.add_column(
            "users",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for name in ("tiktok_alerts", "chat_notifications"):
        op.drop_column("users", name)
