"""project repository

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 14:55:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null: use the name suggested from the title.
    op.add_column(
        "projects", sa.Column("repo_name", sa.String(length=100), nullable=True)
    )
    # Set once the repository exists on GitHub; the id survives a rename there.
    op.add_column(
        "projects", sa.Column("github_repo_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("github_repo_url", sa.String(length=300), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("projects", "github_repo_url")
    op.drop_column("projects", "github_repo_id")
    op.drop_column("projects", "repo_name")
