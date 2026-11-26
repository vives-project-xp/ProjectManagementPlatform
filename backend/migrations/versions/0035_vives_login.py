"""vives login

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-26 15:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # VIVES login through Authentik (spec #160, #161).
    op.add_column("users", sa.Column("authentik_sub", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_authentik_sub", "users", ["authentik_sub"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_users_authentik_sub", "users", type_="unique")
    op.drop_column("users", "authentik_sub")
