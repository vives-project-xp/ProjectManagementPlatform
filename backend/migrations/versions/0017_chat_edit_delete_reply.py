"""chat edit, delete and reply

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-29 09:45:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Replies, edits and soft deletes of Chat messages (spec #91), and a number
    # for every change so open Chats can ask what changed.
    op.execute("CREATE SEQUENCE chat_revision")
    op.add_column(
        "chat_messages", sa.Column("reply_to_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "chat_messages",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing messages are numbered in the order they were sent.
    op.add_column(
        "chat_messages",
        sa.Column(
            "revision",
            sa.BigInteger(),
            server_default=sa.text("nextval('chat_revision')"),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE chat_messages SET revision = numbered.n FROM ("
        " SELECT id, nextval('chat_revision') AS n FROM"
        " (SELECT id FROM chat_messages ORDER BY id) AS ordered) AS numbered"
        " WHERE chat_messages.id = numbered.id"
    )
    op.alter_column("chat_messages", "revision", nullable=False)
    op.create_foreign_key(
        "chat_messages_reply_to_id_fkey",
        "chat_messages",
        "chat_messages",
        ["reply_to_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_chat_messages_project_revision",
        "chat_messages",
        ["project_id", "revision"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chat_messages_project_revision", table_name="chat_messages")
    op.drop_constraint(
        "chat_messages_reply_to_id_fkey", "chat_messages", type_="foreignkey"
    )
    op.drop_column("chat_messages", "revision")
    op.drop_column("chat_messages", "deleted_at")
    op.drop_column("chat_messages", "edited_at")
    op.drop_column("chat_messages", "reply_to_id")
    op.execute("DROP SEQUENCE chat_revision")
