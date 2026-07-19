"""Database-operaties voor Weekmenu (Fase 2: recept opslaan met ingrediënt-matching)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.weekmenu.errors import WeekmenuError
from app.weekmenu.models import (
    Ingredient,
    PantryType,
    Recipe,
    RecipeCategory,
    RecipeDifficulty,
    RecipeIngredient,
    RecipeMoment,
    RecipeTime,
)
from app.weekmenu.schemas import RecipeCreate, RecipeIngredientOut, RecipeOut


def normalize_ingredient_name(name: str) -> str:
    """Lowercase + trimmed + enkelvoudige spaties — de dedupe-sleutel uit Fase 1."""
    return " ".join(name.lower().split())


def get_or_create_ingredient(db: Session, name: str) -> Ingredient:
    """Match op normalized_name: bestaand → hergebruiken (pantry_type en
    winkelcategorie blijven staan); nieuw → aanmaken met pantry_type = normal."""
    normalized = normalize_ingredient_name(name)
    existing = db.scalar(select(Ingredient).where(Ingredient.normalized_name == normalized))
    if existing is not None:
        return existing
    ingredient = Ingredient(
        name=name.strip(), normalized_name=normalized, pantry_type=PantryType.NORMAL
    )
    db.add(ingredient)
    db.flush()  # id nodig vóór de koppelrijen
    return ingredient


def _check_attribute_ids(db: Session, data: RecipeCreate) -> None:
    """Onbekende FK-ids → nette 400 in plaats van een IntegrityError-500."""
    for model, value, label in (
        (RecipeMoment, data.moment_id, "moment_id"),
        (RecipeCategory, data.category_id, "category_id"),
        (RecipeTime, data.time_id, "time_id"),
        (RecipeDifficulty, data.difficulty_id, "difficulty_id"),
    ):
        if value is not None and db.get(model, value) is None:
            raise WeekmenuError(400, "unknown_attribute", f"Onbekende {label}: {value}.")


def create_recipe(db: Session, data: RecipeCreate, photo_path: str | None) -> Recipe:
    """Recept + koppelrijen in één commit; dubbele ingrediënten binnen het recept
    worden samengevoegd tot één koppelrij (eerste hoeveelheid wint)."""
    _check_attribute_ids(db, data)
    recipe = Recipe(
        title=data.title.strip(),
        description=data.description,
        photo_path=photo_path,
        source_url=data.source_url,
        moment_id=data.moment_id,
        category_id=data.category_id,
        time_id=data.time_id,
        difficulty_id=data.difficulty_id,
    )
    db.add(recipe)

    seen_ingredient_ids: set[int] = set()
    for item in data.ingredients:
        ingredient = get_or_create_ingredient(db, item.name)
        if ingredient.id in seen_ingredient_ids:
            continue
        seen_ingredient_ids.add(ingredient.id)
        recipe.ingredients.append(
            RecipeIngredient(
                ingredient=ingredient,
                quantity=item.quantity,
                unit=item.unit,
                note=item.note,
            )
        )
    db.commit()
    db.refresh(recipe)
    return recipe


def recipe_to_out(recipe: Recipe) -> RecipeOut:
    """Handmatige serialisatie: naam + pantry_type komen van het canonieke ingrediënt."""
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        photo_path=recipe.photo_path,
        source_url=recipe.source_url,
        moment_id=recipe.moment_id,
        category_id=recipe.category_id,
        time_id=recipe.time_id,
        difficulty_id=recipe.difficulty_id,
        ingredients=[
            RecipeIngredientOut(
                id=link.id,
                ingredient_id=link.ingredient_id,
                name=link.ingredient.name,
                pantry_type=link.ingredient.pantry_type,
                quantity=link.quantity,
                unit=link.unit,
                note=link.note,
            )
            for link in recipe.ingredients
        ],
    )
