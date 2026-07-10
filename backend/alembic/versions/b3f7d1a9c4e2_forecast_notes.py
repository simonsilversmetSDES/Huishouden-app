"""forecast_notes: Excel-achtige celnotities op de vermogensforecast (context × activaklasse × jaar × maand)

Revision ID: b3f7d1a9c4e2
Revises: e1f6a8d4b2c9
Create Date: 2026-07-10 14:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3f7d1a9c4e2"
down_revision: Union[str, Sequence[str], None] = "e1f6a8d4b2c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forecast_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("context_id", sa.Integer(), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("asset_class", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.UniqueConstraint("context_id", "asset_class", "year", "month"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="forecast_note_month_range"),
    )


def downgrade() -> None:
    op.drop_table("forecast_notes")
