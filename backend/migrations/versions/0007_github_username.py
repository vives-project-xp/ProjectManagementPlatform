"""github username

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 14:05:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("github_username", sa.String(length=39), nullable=True)
    )
    # One GitHub account belongs to one User, whatever the capitalisation.
    op.create_index(
        "uq_users_github_username_lower",
        "users",
        [sa.text("lower(github_username)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_users_github_username_lower", table_name="users")
    op.drop_column("users", "github_username")
