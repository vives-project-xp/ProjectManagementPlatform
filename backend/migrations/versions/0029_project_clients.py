"""project clients

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-19 14:50:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Clients following Projects, with the Client Product Owner label (#134).
    op.create_table(
        "project_clients",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "client_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "is_client_product_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_project_clients_client_id", "project_clients", ["client_id"])
    op.create_index(
        "uq_project_clients_one_client_product_owner",
        "project_clients",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_client_product_owner"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("project_clients")
