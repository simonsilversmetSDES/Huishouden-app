"""budget_notes: Excel-achtige celnotities op de budgetmatrix (categorie × jaar × maand)

Revision ID: 9e4b2c8f5a17
Revises: 6cd07a71283d
Create Date: 2026-07-10 12:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "9e4b2c8f5a17"
down_revision: Union[str, Sequence[str], None] = "6cd07a71283d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.UniqueConstraint("category_id", "year", "month"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="note_month_range"),
    )


def downgrade() -> None:
    op.drop_table("budget_notes")
