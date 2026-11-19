"""instagram publishing

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-19 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Automatic publishing on Instagram (spec #110, #117).
    op.add_column(
        "post_suggestions",
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "post_suggestions",
        sa.Column("publish_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name in ("publish_error", "published_url"):
        op.add_column(
            "post_suggestions", sa.Column(name, sa.String(500), nullable=True)
        )
    op.create_table(
        "publish_links",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.Integer(),
            sa.ForeignKey("post_suggestions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "medium_id",
            sa.Integer(),
            sa.ForeignKey("weekly_media.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_publish_links_suggestion_id", "publish_links", ["suggestion_id"]
    )
    op.create_table(
        "channel_tokens",
        sa.Column("channel", sa.String(20), primary_key=True),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_error", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("channel_tokens")
    op.drop_index("ix_publish_links_suggestion_id", "publish_links")
    op.drop_table("publish_links")
    for name in ("published_url", "publish_error", "publish_retry_at"):
        op.drop_column("post_suggestions", name)
    op.drop_column("post_suggestions", "publish_attempts")
