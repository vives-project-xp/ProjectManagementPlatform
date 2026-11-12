"""weekly media

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-12 10:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Photos (and from #113 the video) of a Weekly update (spec #110, #112).
    op.create_table(
        "weekly_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekly_update_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "posted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint("kind IN ('photo', 'video')", name="ck_weekly_media_kind"),
        sa.ForeignKeyConstraint(
            ["weekly_update_id"], ["weekly_updates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_weekly_media_weekly_update_id", "weekly_media", ["weekly_update_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("weekly_media")
