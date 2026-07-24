"""recipe_ingredient display_name

Voegt ``recipe_ingredients.display_name`` toe: de naam zoals in dát recept geschreven
("verse munt"), terwijl het gelinkte canonieke ingrediënt de opgeschoonde basis is
("munt"). Puur additief, nullable — bestaande rijen krijgen hun display_name in de
opvolgende datamigratie (a9d2f5c7b3e1).

Revision ID: f3b6c1d8e4a2
Revises: c7a1f4e9b2d3
Create Date: 2026-07-24 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.types  # custom types (MoneyCents, PreciseDecimal) in autogenerate


# revision identifiers, used by Alembic.
revision: str = 'f3b6c1d8e4a2'
down_revision: Union[str, Sequence[str], None] = 'c7a1f4e9b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipe_ingredients', sa.Column('display_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('recipe_ingredients', 'display_name')
