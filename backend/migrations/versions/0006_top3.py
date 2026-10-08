"""top 3: open for choice, the round and the choices

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 11:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "projects",
        sa.Column(
            "open_for_choice", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # At most one row: the current Top 3 round (spec #37).
    op.create_table(
        "top3_round",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_top3_round_single"),
    )
    op.create_table(
        "top3_choices",
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_top3_choices_rank"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        # A deleted Project leaves the choice behind as "no longer available".
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("student_id", "rank"),
        sa.UniqueConstraint("student_id", "project_id", name="uq_top3_choices_project"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("top3_choices")
    op.drop_table("top3_round")
    op.drop_column("projects", "open_for_choice")
