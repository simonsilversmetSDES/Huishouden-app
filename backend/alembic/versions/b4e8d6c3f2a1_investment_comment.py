"""property_investments.comment: vrije toelichting bij een investering (spec §8)

Bv. "Meerwaarde door keuken (50% aankoopprijs keuken)".

Revision ID: b4e8d6c3f2a1
Revises: a7f3c2d1e9b0
Create Date: 2026-07-08 21:30:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4e8d6c3f2a1"
down_revision: str | Sequence[str] | None = "a7f3c2d1e9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("property_investments") as batch:
        batch.add_column(sa.Column("comment", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("property_investments") as batch:
        batch.drop_column("comment")
