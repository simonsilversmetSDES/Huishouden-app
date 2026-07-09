"""security.is_benchmark: markeer een effect als referentie-index voor de rendementsvergelijking (spec §7-uitbreiding)

Revision ID: 6cd07a71283d
Revises: c9d2e5f4a3b7
Create Date: 2026-07-09 12:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "6cd07a71283d"
down_revision: Union[str, Sequence[str], None] = "c9d2e5f4a3b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "securities",
        sa.Column("is_benchmark", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_column("is_benchmark")
