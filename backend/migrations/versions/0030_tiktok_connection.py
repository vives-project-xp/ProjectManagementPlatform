"""tiktok connection

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-26 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTINGS = [
    ("tiktok_weekdays", JSONB(), sa.text("'[0, 1, 2, 3, 4]'::jsonb")),
    ("tiktok_times", JSONB(), sa.text("'[\"17:00\"]'::jsonb")),
    ("slideshow_weekday", sa.SmallInteger(), sa.text("4")),
    ("slideshow_time", sa.Time(), sa.text("'18:00'")),
    ("slideshow_cutoff_weekday", sa.SmallInteger(), sa.text("4")),
    ("slideshow_cutoff_time", sa.Time(), sa.text("'12:00'")),
]


def upgrade() -> None:
    """Upgrade schema."""
    # TikTok (spec #145, #146): Posting times and the Slideshow cut-off.
    for name, kind, default in SETTINGS:
        op.add_column(
            "social_settings",
            sa.Column(name, kind, nullable=False, server_default=default),
        )
    op.create_check_constraint(
        "ck_social_settings_slideshow_weekdays",
        "social_settings",
        "slideshow_weekday BETWEEN 0 AND 6 "
        "AND slideshow_cutoff_weekday BETWEEN 0 AND 6",
    )
    # The TikTok account's tokens.
    op.add_column("channel_tokens", sa.Column("refresh_token", sa.Text()))
    op.add_column(
        "channel_tokens",
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column("channel_tokens", sa.Column("account_name", sa.String(200)))
    op.add_column(
        "channel_tokens", sa.Column("connected_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    """Downgrade schema."""
    for name in ("connected_at", "account_name", "refresh_expires_at", "refresh_token"):
        op.drop_column("channel_tokens", name)
    op.drop_constraint(
        "ck_social_settings_slideshow_weekdays", "social_settings", type_="check"
    )
    for name, _, _ in reversed(SETTINGS):
        op.drop_column("social_settings", name)
