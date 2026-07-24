"""canonicaliseer ingrediënten en kruiden

Eenmalige opschoning van de bestaande ingrediëntenlijst (data-only):

1. ``recipe_ingredients.display_name`` vullen met de HUIDIGE (geschreven) ingrediëntnaam,
   zodat recepten "verse munt", "dikke wortelen" enz. blijven tonen.
2. De canonieke ingrediënten samenvoegen: elke naam wordt gecanonicaliseerd (voorvoegsels
   weg + synoniemen, zie ingredient_names.py). Ingrediënten met dezelfde canonieke basis
   worden samengevoegd tot één rij; recept- en boodschappenlijst-verwijzingen hangen mee
   om (geen data-verlies), de dubbele rijen verdwijnen.
3. Kruiden/specerijen krijgen voorraadtype 'herbs' en — indien de winkelcategorie
   "Kruiden" bestaat — die winkelcategorie.

LET OP — eerst op een KOPIE draaien en het resultaat controleren (CLAUDE.md):

    SELECT name, pantry_type FROM ingredients ORDER BY name;

Draait defensief: onbekende namen (bv. op prod) worden gewoon prefix-gestript en, indien
geen synoniem, ongemoeid gelaten. Op een verse installatie (geen ingrediënten) is dit een
no-op.

Revision ID: a9d2f5c7b3e1
Revises: f3b6c1d8e4a2
Create Date: 2026-07-24 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.types  # custom types (MoneyCents, PreciseDecimal) in autogenerate
from app.weekmenu.ingredient_names import canonicalize_ingredient_name, is_herb


# revision identifiers, used by Alembic.
revision: str = 'a9d2f5c7b3e1'
down_revision: Union[str, Sequence[str], None] = 'f3b6c1d8e4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KRUIDEN_CATEGORY_NAME = "Kruiden"


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def upgrade() -> None:
    bind = op.get_bind()

    # 1. display_name backfill met de huidige (geschreven) naam.
    bind.execute(sa.text(
        "UPDATE recipe_ingredients SET display_name = ("
        "  SELECT name FROM ingredients WHERE ingredients.id = recipe_ingredients.ingredient_id"
        ") WHERE display_name IS NULL"
    ))

    # 2. Canonieke merge.
    rows = bind.execute(sa.text("SELECT id, name FROM ingredients")).fetchall()
    link_counts = dict(bind.execute(sa.text(
        "SELECT ingredient_id, COUNT(*) FROM recipe_ingredients GROUP BY ingredient_id"
    )).fetchall())

    # canon_norm → lijst van (id, canon_display)
    groups: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        canon_display = canonicalize_ingredient_name(row.name)
        groups.setdefault(_norm(canon_display), []).append((row.id, canon_display))

    for canon_norm, members in groups.items():
        # Keeper: bestaand ingrediënt dat al op de canonieke sleutel staat (minimale
        # hernoeming); anders het meest-gebruikte, dan het laagste id.
        member_ids = [mid for mid, _ in members]
        current_norms = dict(bind.execute(
            sa.text(
                "SELECT id, normalized_name FROM ingredients WHERE id IN ("
                + ",".join(str(i) for i in member_ids) + ")"
            )
        ).fetchall())
        keeper_id = next((mid for mid in member_ids if current_norms.get(mid) == canon_norm), None)
        if keeper_id is None:
            keeper_id = max(member_ids, key=lambda mid: (link_counts.get(mid, 0), -mid))
        keeper_display = next(disp for mid, disp in members if mid == keeper_id)

        # Overige leden omhangen en verwijderen.
        for mid in member_ids:
            if mid == keeper_id:
                continue
            bind.execute(
                sa.text("UPDATE recipe_ingredients SET ingredient_id = :k WHERE ingredient_id = :m"),
                {"k": keeper_id, "m": mid},
            )
            bind.execute(
                sa.text("UPDATE shopping_list_items SET ingredient_id = :k WHERE ingredient_id = :m"),
                {"k": keeper_id, "m": mid},
            )
            bind.execute(sa.text("DELETE FROM ingredients WHERE id = :m"), {"m": mid})

        # Keeper naar de canonieke naam zetten.
        bind.execute(
            sa.text("UPDATE ingredients SET name = :name, normalized_name = :norm WHERE id = :id"),
            {"name": keeper_display, "norm": canon_norm, "id": keeper_id},
        )

    # 3. Kruiden toewijzen (op de canonieke namen).
    kruiden_id = bind.execute(
        sa.text("SELECT id FROM shopping_categories WHERE name = :name"),
        {"name": KRUIDEN_CATEGORY_NAME},
    ).scalar()

    for row in bind.execute(sa.text("SELECT id, name FROM ingredients")).fetchall():
        if not is_herb(row.name):
            continue
        if kruiden_id is not None:
            bind.execute(
                sa.text(
                    "UPDATE ingredients SET pantry_type = 'herbs', "
                    "shopping_category_id = :cat WHERE id = :id"
                ),
                {"cat": kruiden_id, "id": row.id},
            )
        else:
            bind.execute(
                sa.text("UPDATE ingredients SET pantry_type = 'herbs' WHERE id = :id"),
                {"id": row.id},
            )


def downgrade() -> None:
    """Data-only opschoning; samenvoegingen en canonicalisatie zijn niet reconstrueerbaar.
    De display_name-kolom zelf verdwijnt via de schema-downgrade (f3b6c1d8e4a2)."""
    pass
