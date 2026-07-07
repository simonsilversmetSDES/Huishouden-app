"""security_splits: aandelensplitsingen (spec §7)

Revision ID: c3d5a9f21e77
Revises: b7e2f1a3c8d4
Create Date: 2026-07-07 12:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5a9f21e77"
down_revision: Union[str, Sequence[str], None] = "b7e2f1a3c8d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ratio", sa.String(), nullable=False),
        sa.UniqueConstraint("security_id", "date"),
    )


def downgrade() -> None:
    op.drop_table("security_splits")
