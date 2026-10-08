"""project photo

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 09:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null: no photo. Raised on every upload, so pages can bust caches.
    op.add_column("projects", sa.Column("photo_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("projects", "photo_version")
