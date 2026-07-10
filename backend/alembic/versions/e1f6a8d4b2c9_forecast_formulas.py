"""forecast_formulas: aangepaste forecast-formules per context × activaklasse (× cel)

Revision ID: e1f6a8d4b2c9
Revises: 9e4b2c8f5a17
Create Date: 2026-07-10 12:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f6a8d4b2c9"
down_revision: Union[str, Sequence[str], None] = "9e4b2c8f5a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forecast_formulas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("context_id", sa.Integer(), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("asset_class", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("formula", sa.String(), nullable=False),
        sa.UniqueConstraint("context_id", "asset_class", "year", "month"),
        sa.CheckConstraint("month BETWEEN 0 AND 12", name="forecast_month_range"),
        sa.CheckConstraint("(year = 0) = (month = 0)", name="forecast_default_sentinel"),
    )


def downgrade() -> None:
    op.drop_table("forecast_formulas")
