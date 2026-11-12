"""social settings and weekly updates

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-12 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The one row of social media settings (spec #110, #111).
    op.create_table(
        "social_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_weekday", sa.SmallInteger(), nullable=True),
        sa.Column("upload_time", sa.Time(), nullable=True),
        sa.Column(
            "instagram_weekdays",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "instagram_times", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("fixed_hashtags", sa.String(length=500), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_social_settings_single"),
        sa.CheckConstraint(
            "upload_weekday BETWEEN 0 AND 6", name="ck_social_settings_weekday"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # One Weekly update per Project per Upload week.
    op.create_table(
        "weekly_updates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("edited_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "closes_at", name="uq_weekly_updates_project_week"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("weekly_updates")
    op.drop_table("social_settings")
