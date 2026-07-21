"""SQLAlchemy-modellen voor Weekmenu (WEEKMENU_BUILD.md Fase 1).

Gebruikt de gedeelde ``Base`` (zelfde metadata + naming conventions als Financiën);
deze module wordt geïmporteerd in ``app/models/__init__.py`` zodat Alembic-autogenerate
en de test-``create_all`` de tabellen zien. Alle FK's verwijzen uitsluitend naar
weekmenu-tabellen — nul koppeling met Financiën.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import str_enum


class PantryType(StrEnum):
    ALWAYS_HOME = "always_home"  # nooit op de boodschappenlijst (peper, zout, olijfolie)
    PANTRY = "pantry"  # onder "Voorraadkast", afvinkbaar
    NORMAL = "normal"


class RecipeMoment(Base):
    __tablename__ = "recipe_moments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RecipeCategory(Base):
    __tablename__ = "recipe_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    color: Mapped[str] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RecipeTime(Base):
    __tablename__ = "recipe_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RecipeDifficulty(Base):
    __tablename__ = "recipe_difficulties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ShoppingCategory(Base):
    __tablename__ = "shopping_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    color: Mapped[str] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Ingredient(Base):
    """Canonieke ingrediëntenlijst; dedupe op normalized_name (lowercase + trimmed)."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String, unique=True)
    pantry_type: Mapped[PantryType] = mapped_column(
        str_enum(PantryType, "pantry_type"), default=PantryType.NORMAL
    )
    shopping_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("shopping_categories.id")
    )
    # Enkel betekenisvol bij pantry_type == PANTRY: staat het nog in de kast, of
    # moet het aangevuld worden op de eerstvolgende boodschappenlijst?
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)

    shopping_category: Mapped[ShoppingCategory | None] = relationship()


recipe_category_links = Table(
    "recipe_category_links",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id"), primary_key=True),
    Column("category_id", ForeignKey("recipe_categories.id"), primary_key=True),
)


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)  # bereidingsstappen
    photo_path: Mapped[str | None] = mapped_column(String)  # enkel bestandsnaam (uuid)
    source_url: Mapped[str | None] = mapped_column(String)
    servings: Mapped[int | None] = mapped_column(Integer)
    moment_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_moments.id"))
    time_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_times.id"))
    difficulty_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_difficulties.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    moment: Mapped[RecipeMoment | None] = relationship()
    categories: Mapped[list["RecipeCategory"]] = relationship(
        secondary=recipe_category_links, order_by=RecipeCategory.sort_order
    )
    time: Mapped[RecipeTime | None] = relationship()
    difficulty: Mapped[RecipeDifficulty | None] = relationship()
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )

    @property
    def category_ids(self) -> list[int]:
        return [category.id for category in self.categories]


class RecipeIngredient(Base):
    """Koppeltabel recept ↔ ingrediënt; quantity als tekst ("500", "1/2") uit de parsers."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[str | None] = mapped_column(String)
    unit: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship()


class WeekPlanEntry(Base):
    """Eén invulling per dag: een recept óf vrije tekst (validatie Python-zijdig)."""

    __tablename__ = "week_plan_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    free_text: Mapped[str | None] = mapped_column(String)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Aantal personen voor DEZE dag; los van recipe.servings (bv. gasten die week).
    servings: Mapped[int | None] = mapped_column(Integer)

    recipe: Mapped[Recipe | None] = relationship()


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(ForeignKey("shopping_categories.id"))
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    manually_added: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bron-link ("MENU"-label): gezet wanneer het item uit een weekmenu-recept komt.
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id"))
    # Samengevoegde weergavetekst (bv. "200 g + 1 stuk"); zie crud.py
    # sync_and_get_shopping_list voor de combineer-aanpak (Fase 5).
    quantity: Mapped[str | None] = mapped_column(String)

    category: Mapped[ShoppingCategory] = relationship()
