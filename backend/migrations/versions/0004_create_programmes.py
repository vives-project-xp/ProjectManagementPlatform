"""create programmes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01 15:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "programmes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_programmes_name_lower",
        "programmes",
        [sa.text("lower(name)")],
        unique=True,
    )
    # The list that was fixed in code (ADR 0004), plus any Programme a User
    # already has, so every existing Student keeps a Programme from the list.
    op.execute("INSERT INTO programmes (name) VALUES ('Electronics-ICT')")
    op.execute(
        """
        INSERT INTO programmes (name)
        SELECT DISTINCT programme FROM users
        WHERE programme IS NOT NULL AND lower(programme) <> 'electronics-ict'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_programmes_name_lower", table_name="programmes")
    op.drop_table("programmes")
