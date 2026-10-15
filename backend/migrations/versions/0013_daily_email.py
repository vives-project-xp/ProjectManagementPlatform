"""daily email

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-15 14:05:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The 08:30 Daily email (spec #68): on for everyone unless switched off,
    # and who already got the email of a day.
    op.add_column(
        "users",
        sa.Column(
            "daily_email", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.create_table(
        "daily_emails_sent",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("daily_emails_sent")
    op.drop_column("users", "daily_email")
