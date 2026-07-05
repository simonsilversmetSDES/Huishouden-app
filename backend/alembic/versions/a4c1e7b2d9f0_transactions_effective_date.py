"""transactions.effective_date: budgetmaand-datum (Excel "Effective Date")

Revision ID: a4c1e7b2d9f0
Revises: defd059dcd0f
Create Date: 2026-07-05 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c1e7b2d9f0'
down_revision: Union[str, Sequence[str], None] = 'defd059dcd0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Kolom toevoegen, bestaande rijen backfillen met date, dan verplicht maken."""
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('effective_date', sa.Date(), nullable=True))
    op.execute('UPDATE transactions SET effective_date = date')
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('effective_date', nullable=False, existing_type=sa.Date())
        batch_op.create_index(
            batch_op.f('ix_transactions_effective_date'), ['effective_date'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_effective_date'))
        batch_op.drop_column('effective_date')
