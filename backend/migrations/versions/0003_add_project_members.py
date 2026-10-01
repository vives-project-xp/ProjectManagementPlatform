"""add project members

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_project_id_projects", "users", "projects", ["project_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_users_project_student", "users", "project_id IS NULL OR role = 'student'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_users_project_student", "users", type_="check")
    op.drop_constraint("fk_users_project_id_projects", "users", type_="foreignkey")
    op.drop_column("users", "project_id")
