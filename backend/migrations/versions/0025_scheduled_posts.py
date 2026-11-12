"""scheduled posts

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-12 15:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Posting a reviewed suggestion and posting it by hand (spec #110, #116).
    for name in ("queued_at", "scheduled_for", "posted_at"):
        op.add_column(
            "post_suggestions",
            sa.Column(name, sa.DateTime(timezone=True), nullable=True),
        )
    op.add_column(
        "post_suggestions", sa.Column("posted_by_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_post_suggestions_posted_by_id_users",
        "post_suggestions",
        "users",
        ["posted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_post_suggestions_posted_by_id_users", "post_suggestions")
    for name in ("posted_by_id", "posted_at", "scheduled_for", "queued_at"):
        op.drop_column("post_suggestions", name)
