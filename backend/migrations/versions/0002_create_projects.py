"""create projects

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01 13:35:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_owner_id", sa.Integer(), nullable=False),
        sa.Column("team_size_min", sa.Integer(), nullable=False),
        sa.Column("team_size_max", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "makers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "team_size_min >= 1 AND team_size_min <= team_size_max",
            name="ck_projects_team_size",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')", name="ck_projects_status"
        ),
        sa.ForeignKeyConstraint(["product_owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_projects_title_lower",
        "projects",
        [sa.text("lower(title)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_projects_title_lower", table_name="projects")
    op.drop_table("projects")
