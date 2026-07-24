"""Seed voor de weekmenu-attribuut- en winkelcategorietabellen.

Bewust strikter idempotent dan de Financiën-seed (die matcht op naam): elke tabel
wordt alleen gevuld als ze volledig leeg is. De waarden zijn via het beheerscherm
hernoem- én verwijderbaar; match-op-naam zou verwijderde of hernoemde rijen bij
elke herstart terugzetten.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.weekmenu.models import (
    RecipeCategory,
    RecipeDifficulty,
    RecipeMoment,
    RecipeTime,
    ShoppingCategory,
)

MOMENTS = ["Lunch", "Diner"]

# (naam, kleur) — startpalet, aanpasbaar via het beheerscherm.
RECIPE_CATEGORIES = [
    ("Vis", "#3b82f6"),
    ("Vlees", "#ef4444"),
    ("Veggie", "#22c55e"),
    ("Pasta", "#f59e0b"),
    ("Soep", "#f97316"),
    ("Salade", "#84cc16"),
    ("Oven", "#a855f7"),
    ("Anders", "#6b7280"),
]

TIMES = ["Snel", "Gemiddeld", "Lang"]

DIFFICULTIES = ["Makkelijk", "Gemiddeld", "Moeilijk"]

SHOPPING_CATEGORIES = [
    ("Groenten & Fruit", "#22c55e"),
    ("Vlees & Vis", "#ef4444"),
    ("Zuivel", "#38bdf8"),
    ("Voorraadkast", "#f59e0b"),
    ("Kruiden", "#14b8a6"),
    ("Diepvries", "#6366f1"),
    ("Drank", "#a855f7"),
    ("Overig", "#6b7280"),
]


def _table_empty(db: Session, model: type) -> bool:
    return db.scalars(select(model).limit(1)).first() is None


def seed_weekmenu(db: Session) -> None:
    """Vult lege attribuut-/winkelcategorietabellen; raakt bestaande rijen nooit aan."""
    if _table_empty(db, RecipeMoment):
        for order, name in enumerate(MOMENTS):
            db.add(RecipeMoment(name=name, sort_order=order))
    if _table_empty(db, RecipeCategory):
        for order, (name, color) in enumerate(RECIPE_CATEGORIES):
            db.add(RecipeCategory(name=name, color=color, sort_order=order))
    if _table_empty(db, RecipeTime):
        for order, name in enumerate(TIMES):
            db.add(RecipeTime(name=name, sort_order=order))
    if _table_empty(db, RecipeDifficulty):
        for order, name in enumerate(DIFFICULTIES):
            db.add(RecipeDifficulty(name=name, sort_order=order))
    if _table_empty(db, ShoppingCategory):
        for order, (name, color) in enumerate(SHOPPING_CATEGORIES):
            db.add(ShoppingCategory(name=name, color=color, sort_order=order))
