"""month_notes: vrije-tekstnotitie per dashboardmaand (context × jaar × maand)

Revision ID: c8e1a3f7b6d2
Revises: d4e9a1c6f3b2
Create Date: 2026-07-24 12:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e1a3f7b6d2"
down_revision: Union[str, Sequence[str], None] = "d4e9a1c6f3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "month_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("context_id", sa.Integer(), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.UniqueConstraint("context_id", "year", "month"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="month_note_month_range"),
    )


def downgrade() -> None:
    op.drop_table("month_notes")
