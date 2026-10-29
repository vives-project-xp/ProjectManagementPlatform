"""project archived_at

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-29 11:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # When a Project was archived: its Chat is deleted 6 months later (#98).
    op.add_column(
        "projects",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Projects archived before this existed count from today.
    op.execute("UPDATE projects SET archived_at = now() WHERE status = 'archived'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("projects", "archived_at")
