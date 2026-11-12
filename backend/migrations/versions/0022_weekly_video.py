"""weekly video

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-12 11:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # A video is processed in the background after upload (spec #110, #113).
    op.add_column(
        "weekly_media",
        sa.Column(
            "state", sa.String(length=12), server_default="ready", nullable=False
        ),
    )
    op.add_column("weekly_media", sa.Column("seconds", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_weekly_media_state",
        "weekly_media",
        "state IN ('processing', 'ready', 'failed')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_weekly_media_state", "weekly_media")
    op.drop_column("weekly_media", "seconds")
    op.drop_column("weekly_media", "state")
