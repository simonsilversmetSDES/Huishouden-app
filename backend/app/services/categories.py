"""Categoriebeheer per context (spec §3): toevoegen en (soft-)verwijderen.

Categorieën zijn per context; toevoegen/verwijderen in één context raakt de
andere niet. "Verwijderen" = deactiveren (`active=False`): transacties, budgetten
en historiek verwijzen via FK naar de categorie, dus die blijven intact terwijl
de categorie uit de kiezers en de budgetmatrix verdwijnt. Regels die naar een
verwijderde categorie wijzen worden mee opgeruimd (anders zouden ze nieuwe
transacties een inactieve categorie toekennen).
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category
from app.models.enums import CategoryType


class EmptyCategoryNameError(ValueError):
    """De categorienaam is leeg."""


class DuplicateCategoryError(ValueError):
    """Er bestaat al een actieve categorie met dezelfde naam en type in de context."""


def create_category(db: Session, context_id: int, name: str, type_: CategoryType) -> Category:
    """Categorie toevoegen; reactiveert een eerder gedeactiveerde met dezelfde sleutel."""
    clean = name.strip()
    if not clean:
        raise EmptyCategoryNameError("Categorienaam is leeg")

    existing = db.scalars(
        select(Category).where(
            Category.context_id == context_id,
            Category.type == type_,
            Category.name == clean,
        )
    ).one_or_none()
    if existing is not None:
        if existing.active:
            raise DuplicateCategoryError(f"Categorie '{clean}' bestaat al")
        existing.active = True  # reactiveren i.p.v. botsen met de UniqueConstraint
        db.commit()
        return existing

    max_sort = db.scalar(
        select(func.max(Category.sort_order)).where(Category.context_id == context_id)
    )
    category = Category(
        context_id=context_id,
        name=clean,
        type=type_,
        sort_order=(max_sort or 0) + 1,
        active=True,
    )
    db.add(category)
    db.commit()
    return category


def deactivate_category(db: Session, category: Category) -> None:
    """Categorie deactiveren en de regels die ernaar verwijzen verwijderen."""
    category.active = False
    db.execute(delete(CategorizationRule).where(CategorizationRule.category_id == category.id))
    db.commit()
