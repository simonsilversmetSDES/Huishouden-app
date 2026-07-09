"""loan/woning: extra leningvelden + investeringen en eigen inbreng (spec §8)

Voegt woningwaardering-velden toe aan loans (basiswaarde/-jaar, indexatie), maakt
monthly_payment optioneel (None → berekend via annuïteit), vervangt de ongebruikte
property_value_estimate door berekening, en voegt de tabellen property_investments
en loan_contributions toe.

Revision ID: a7f3c2d1e9b0
Revises: f2a9c4e6b8d1
Create Date: 2026-07-08 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7f3c2d1e9b0"
down_revision: str | Sequence[str] | None = "f2a9c4e6b8d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("loans") as batch:
        batch.add_column(sa.Column("property_base_value", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("property_base_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("indexation_rate", sa.String(), nullable=True))
        batch.alter_column("monthly_payment", existing_type=sa.Integer(), nullable=True)
        batch.drop_column("property_value_estimate")

    op.create_table(
        "property_investments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("loan_id", sa.Integer(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("added_value", sa.Integer(), nullable=False),
    )
    op.create_table(
        "loan_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("loan_id", sa.Integer(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("context_id", sa.Integer(), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("loan_contributions")
    op.drop_table("property_investments")
    with op.batch_alter_table("loans") as batch:
        batch.add_column(sa.Column("property_value_estimate", sa.Integer(), nullable=True))
        batch.alter_column("monthly_payment", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("indexation_rate")
        batch.drop_column("property_base_year")
        batch.drop_column("property_base_value")
