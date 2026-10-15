"""meetings

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15 13:45:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # One-off Meetings of a Project's team (spec #68).
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place", sa.String(length=500), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("ends_at > starts_at", name="ck_meetings_end_after_start"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_project_id", "meetings", ["project_id"])
    # At most one Weekly slot per Project (weekday 0 = Monday, Belgian time),
    # and the dates on which it doesn't take place.
    op.create_table(
        "weekly_slots",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("starts", sa.Time(), nullable=False),
        sa.Column("ends", sa.Time(), nullable=False),
        sa.Column("place", sa.String(length=500), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_weekly_slots_weekday"),
        sa.CheckConstraint("ends > starts", name="ck_weekly_slots_end_after_start"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "weekly_slot_skips",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["weekly_slots.project_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "day"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("weekly_slot_skips")
    op.drop_table("weekly_slots")
    op.drop_index("ix_meetings_project_id", table_name="meetings")
    op.drop_table("meetings")
