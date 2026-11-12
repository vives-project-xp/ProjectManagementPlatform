"""suggestion review

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-12 15:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The Review of a Post suggestion (spec #110, #115).
    op.add_column(
        "post_suggestions", sa.Column("reviewed_by_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "post_suggestions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "post_suggestions",
        sa.Column("refusal_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_post_suggestions_reviewed_by_id_users",
        "post_suggestions",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_post_suggestions_reviewed_by_id_users", "post_suggestions")
    op.drop_column("post_suggestions", "refusal_reason")
    op.drop_column("post_suggestions", "reviewed_at")
    op.drop_column("post_suggestions", "reviewed_by_id")
