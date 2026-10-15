"""trello boards

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15 09:20:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # A Project's own Trello Workspace and board, once they exist (spec #61).
    op.add_column(
        "projects",
        sa.Column("trello_workspace_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "projects", sa.Column("trello_board_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("trello_board_url", sa.String(length=300), nullable=True)
    )
    # The Trello members the platform itself invited, and for which User and
    # email, so "Check members" knows who is who and whom it may remove.
    op.create_table(
        "trello_grants",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("trello_member_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_id", "trello_member_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("trello_grants")
    op.drop_column("projects", "trello_board_url")
    op.drop_column("projects", "trello_board_id")
    op.drop_column("projects", "trello_workspace_id")
