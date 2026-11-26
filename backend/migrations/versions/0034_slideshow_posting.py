"""slideshow posting

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-26 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "state IN ('generating', 'waiting', 'failed', 'refused', 'none')"
NEW = (
    "state IN ('generating', 'waiting', 'failed', 'refused', 'none', "
    "'scheduled', 'in_inbox', 'to_post_by_hand', 'posted', 'dropped')"
)


def upgrade() -> None:
    """Upgrade schema."""
    # Posting the Weekly slideshow (spec #145, #150).
    op.drop_constraint("ck_weekly_slideshows_state", "weekly_slideshows", type_="check")
    op.create_check_constraint("ck_weekly_slideshows_state", "weekly_slideshows", NEW)
    for name in ("queued_at", "scheduled_for", "publish_retry_at", "posted_at"):
        op.add_column("weekly_slideshows", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column(
        "weekly_slideshows",
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("weekly_slideshows", sa.Column("publish_error", sa.String(500)))
    op.add_column("weekly_slideshows", sa.Column("publish_id", sa.String(100)))
    op.add_column(
        "weekly_slideshows",
        sa.Column(
            "posted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )
    # Publish links for the slideshow's photos.
    op.alter_column("publish_links", "suggestion_id", nullable=True)
    op.add_column(
        "publish_links",
        sa.Column(
            "slideshow_id",
            sa.Integer(),
            sa.ForeignKey("weekly_slideshows.id", ondelete="CASCADE"),
        ),
    )
    op.create_index("ix_publish_links_slideshow_id", "publish_links", ["slideshow_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_publish_links_slideshow_id", "publish_links")
    op.drop_column("publish_links", "slideshow_id")
    op.execute("DELETE FROM publish_links WHERE suggestion_id IS NULL")
    op.alter_column("publish_links", "suggestion_id", nullable=False)
    for name in (
        "posted_by_id",
        "publish_id",
        "publish_error",
        "publish_attempts",
        "posted_at",
        "publish_retry_at",
        "scheduled_for",
        "queued_at",
    ):
        op.drop_column("weekly_slideshows", name)
    op.execute(
        "UPDATE weekly_slideshows SET state = 'refused' WHERE state IN "
        "('scheduled', 'in_inbox', 'to_post_by_hand', 'posted', 'dropped')"
    )
    op.drop_constraint("ck_weekly_slideshows_state", "weekly_slideshows", type_="check")
    op.create_check_constraint("ck_weekly_slideshows_state", "weekly_slideshows", OLD)
