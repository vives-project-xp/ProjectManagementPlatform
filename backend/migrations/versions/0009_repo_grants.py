"""repo grants

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08 15:25:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The GitHub accounts the platform itself invited to a Project's repository,
    # so "Check members" can take their access back later (spec #49).
    op.create_table(
        "repo_grants",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=39), nullable=False),
        sa.CheckConstraint("login = lower(login)", name="ck_repo_grants_login_lower"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "login"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("repo_grants")
