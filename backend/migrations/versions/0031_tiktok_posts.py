"""tiktok posts

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-26 10:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Also on TikTok (spec #145, #147).
    op.create_table(
        "tiktok_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.Integer(),
            sa.ForeignKey("post_suggestions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "medium_id",
            sa.Integer(),
            sa.ForeignKey("weekly_media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("privacy_level", sa.String(40), nullable=False),
        sa.Column("allow_comment", sa.Boolean(), nullable=False),
        sa.Column("allow_duet", sa.Boolean(), nullable=False),
        sa.Column("allow_stitch", sa.Boolean(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("publish_id", sa.String(100), nullable=True),
        sa.Column("published_url", sa.String(500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "posted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "state IN ('scheduled', 'published', 'to_post_by_hand', 'posted_by_hand')",
            name="ck_tiktok_posts_state",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("tiktok_posts")
