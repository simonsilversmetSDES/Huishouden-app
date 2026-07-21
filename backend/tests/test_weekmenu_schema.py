"""Fase 1 Weekmenu: schema-constraints en seed-gedrag (leeg-of-niks, idempotent)."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.weekmenu.models import (
    Ingredient,
    Recipe,
    RecipeCategory,
    RecipeDifficulty,
    RecipeIngredient,
    RecipeMoment,
    RecipeTime,
    ShoppingCategory,
    WeekPlanEntry,
)
from app.weekmenu.seed import seed_weekmenu


class TestSeed:
    def test_vult_alle_attribuuttabellen(self, db: Session) -> None:
        seed_weekmenu(db)
        db.commit()
        moments = db.scalars(select(RecipeMoment).order_by(RecipeMoment.sort_order))
        assert [m.name for m in moments] == ["Lunch", "Diner", "Beide"]
        assert len(db.scalars(select(RecipeCategory)).all()) == 8
        assert len(db.scalars(select(RecipeTime)).all()) == 3
        assert len(db.scalars(select(RecipeDifficulty)).all()) == 3
        assert len(db.scalars(select(ShoppingCategory)).all()) == 7

    def test_tweede_run_voegt_niets_toe(self, db: Session) -> None:
        seed_weekmenu(db)
        db.commit()
        seed_weekmenu(db)
        db.commit()
        assert len(db.scalars(select(RecipeCategory)).all()) == 8

    def test_gebruikerswijziging_overleeft_herseed(self, db: Session) -> None:
        seed_weekmenu(db)
        db.commit()
        veggie = db.scalars(select(RecipeCategory).where(RecipeCategory.name == "Veggie")).one()
        veggie.name = "Vegetarisch"
        anders = db.scalars(select(RecipeCategory).where(RecipeCategory.name == "Anders")).one()
        db.delete(anders)
        db.commit()

        seed_weekmenu(db)
        db.commit()
        names = {c.name for c in db.scalars(select(RecipeCategory))}
        assert "Vegetarisch" in names
        assert "Veggie" not in names
        assert "Anders" not in names
        assert len(names) == 7


class TestConstraints:
    def test_normalized_name_uniek(self, db: Session) -> None:
        db.add(Ingredient(name="Ui", normalized_name="ui"))
        db.commit()
        db.add(Ingredient(name="UI", normalized_name="ui"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_weekplan_datum_uniek(self, db: Session) -> None:
        db.add(WeekPlanEntry(date=date(2026, 7, 20), free_text="Diepvries"))
        db.commit()
        db.add(WeekPlanEntry(date=date(2026, 7, 20), free_text="Frietjes"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_recept_verwijderen_ruimt_ingredienten_op(self, db: Session) -> None:
        ingredient = Ingredient(name="Ui", normalized_name="ui")
        recipe = Recipe(title="Soep")
        recipe.ingredients.append(RecipeIngredient(ingredient=ingredient, quantity="2"))
        db.add(recipe)
        db.commit()
        assert len(db.scalars(select(RecipeIngredient)).all()) == 1

        db.delete(recipe)
        db.commit()
        assert db.scalars(select(RecipeIngredient)).all() == []
        # het canonieke ingrediënt zelf blijft bestaan
        assert len(db.scalars(select(Ingredient)).all()) == 1
