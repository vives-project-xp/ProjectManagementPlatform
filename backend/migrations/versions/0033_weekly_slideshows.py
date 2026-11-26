"""weekly slideshows

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-26 13:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The Weekly slideshow (spec #145, #149).
    op.create_table(
        "weekly_slideshows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "reviewed_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refusal_reason", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "state IN ('generating', 'waiting', 'failed', 'refused', 'none')",
            name="ck_weekly_slideshows_state",
        ),
    )
    op.create_table(
        "weekly_slideshow_photos",
        sa.Column(
            "slideshow_id",
            sa.Integer(),
            sa.ForeignKey("weekly_slideshows.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "medium_id",
            sa.Integer(),
            sa.ForeignKey("weekly_media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("weekly_slideshow_photos")
    op.drop_table("weekly_slideshows")
