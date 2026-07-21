"""backfill pantry type voorraadkast

Data-only correctie: ingrediënten die de AI-classificatie (zie
ingredient_categorization.py) al naar de winkelcategorie "Voorraadkast" stuurde,
kregen daarbij geen pantry_type mee — dat blijft bij aanmaak altijd 'normal'
(get_or_create_ingredient). Daardoor sloegen ze de "Nodig uit
voorraadkast"-checklist over en stonden ze gewoon in de hoofdlijst (gemeld door
Simon, screenshot 21/07/2026). Enkel pantry_type='normal' → 'pantry' zetten;
'always_home' NIET aanraken — dat zijn bewust nooit-te-kopen items (zout, olie,
kruiden, wijn) die toevallig ook in "Voorraadkast" geclassificeerd zaten.

Revision ID: 788b69c8db41
Revises: 835d05468274
Create Date: 2026-07-21 01:33:24.707187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.types  # custom types (MoneyCents, PreciseDecimal) in autogenerate


# revision identifiers, used by Alembic.
revision: str = '788b69c8db41'
down_revision: Union[str, Sequence[str], None] = '835d05468274'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Zet pantry_type op 'pantry' voor elk ingrediënt met winkelcategorie
    "Voorraadkast" dat nog op de default 'normal' staat."""
    op.execute(
        sa.text(
            """
            UPDATE ingredients
            SET pantry_type = 'pantry'
            WHERE pantry_type = 'normal'
              AND shopping_category_id = (
                  SELECT id FROM shopping_categories WHERE name = 'Voorraadkast'
              )
            """
        )
    )


def downgrade() -> None:
    """Data-only correctie, niet zinvol terug te draaien (we weten niet meer welke
    rijen vóór de upgrade al 'pantry' waren versus net gecorrigeerd)."""
    pass
