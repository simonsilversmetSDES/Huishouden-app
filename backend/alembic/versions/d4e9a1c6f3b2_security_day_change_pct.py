"""securities.day_change_pct: laatst opgehaalde dagbeweging in noteringsmunt (spec §7)

Broker-conforme dagwinst: last vs previousClose van yfinance, in de noteringsmunt
(dus zonder wisselkoerseffect). Puur additief; NULL voor bestaande rijen.

Revision ID: d4e9a1c6f3b2
Revises: a9d2f5c7b3e1
Create Date: 2026-07-24 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e9a1c6f3b2"
down_revision: str | Sequence[str] | None = "a9d2f5c7b3e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("securities") as batch:
        batch.add_column(sa.Column("day_change_pct", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch:
        batch.drop_column("day_change_pct")
