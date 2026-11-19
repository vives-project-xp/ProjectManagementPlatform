"""client role

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-19 14:05:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Clients: a fourth Role with an optional Organisation (spec #132, #133).
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('superuser', 'teacher', 'student', 'client')",
    )
    op.add_column("users", sa.Column("organisation", sa.String(120), nullable=True))
    op.create_check_constraint(
        "ck_users_organisation_client",
        "users",
        "organisation IS NULL OR role = 'client'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_users_organisation_client", "users", type_="check")
    op.drop_column("users", "organisation")
    op.execute("DELETE FROM users WHERE role = 'client'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('superuser', 'teacher', 'student')"
    )
