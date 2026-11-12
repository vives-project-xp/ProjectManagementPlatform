"""post suggestions

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-12 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # One Post suggestion per Weekly update (spec #110, #114).
    op.create_table(
        "post_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekly_update_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("chosen_medium_id", sa.Integer(), nullable=True),
        sa.Column("ranking", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('generating', 'waiting', 'failed', 'refused', 'scheduled', "
            "'published', 'to_post_by_hand', 'posted_by_hand')",
            name="ck_post_suggestions_state",
        ),
        sa.ForeignKeyConstraint(
            ["weekly_update_id"], ["weekly_updates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["chosen_medium_id"], ["weekly_media.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("weekly_update_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("post_suggestions")
