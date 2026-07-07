"""security_transactions.fee/tax/total: MoneyCents -> PreciseDecimal (sub-cent TOB)

Revision ID: b7e2f1a3c8d4
Revises: a4c1e7b2d9f0
Create Date: 2026-07-07 10:00:00.000000

De beurstaks (TOB) is sub-cent (bv. 0,259044) en de gemiddelde aankoopprijs
(spec §10 = € 98,240055) vereist die precisie. fee/tax/total gaan van INTEGER
centen naar exacte Decimal-als-TEXT. Er is nog geen beleggingsdata, dus geen
conversie nodig.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2f1a3c8d4"
down_revision: Union[str, Sequence[str], None] = "a4c1e7b2d9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("security_transactions", schema=None) as batch_op:
        batch_op.alter_column("fee", existing_type=sa.Integer(), type_=sa.String())
        batch_op.alter_column("tax", existing_type=sa.Integer(), type_=sa.String())
        batch_op.alter_column("total", existing_type=sa.Integer(), type_=sa.String())


def downgrade() -> None:
    with op.batch_alter_table("security_transactions", schema=None) as batch_op:
        batch_op.alter_column("fee", existing_type=sa.String(), type_=sa.Integer())
        batch_op.alter_column("tax", existing_type=sa.String(), type_=sa.Integer())
        batch_op.alter_column("total", existing_type=sa.String(), type_=sa.Integer())
