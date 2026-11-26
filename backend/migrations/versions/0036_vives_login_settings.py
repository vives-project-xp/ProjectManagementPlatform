"""vives login settings and break-glass codes

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-26 15:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The VIVES login screen (spec #160, #162).
    op.create_table(
        "vives_login_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issuer_url", sa.String(500)),
        sa.Column("client_id", sa.String(255)),
        sa.Column("client_secret", sa.Text()),
        sa.Column("group_superuser", sa.String(100), nullable=False),
        sa.Column("group_teacher", sa.String(100), nullable=False),
        sa.Column("group_student", sa.String(100), nullable=False),
        sa.Column("group_client", sa.String(100), nullable=False),
        sa.Column("programme_claim", sa.String(100), nullable=False),
        sa.Column("year_claim", sa.String(100), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True)),
        sa.Column(
            "tested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("tested_role", sa.String(20)),
        sa.Column("tested_fingerprint", sa.String(64)),
        sa.Column("enabled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "enabled_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint("id = 1", name="ck_vives_login_single"),
    )
    # Break-glass links (#163).
    op.create_table(
        "break_glass_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("break_glass_codes")
    op.drop_table("vives_login_settings")
