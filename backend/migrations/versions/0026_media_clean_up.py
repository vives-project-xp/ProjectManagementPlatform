"""media clean-up

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-19 09:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # When the never-posted Media were deleted, 4 months after the week (#118).
    op.add_column(
        "weekly_updates",
        sa.Column("media_removed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("weekly_updates", "media_removed_at")
