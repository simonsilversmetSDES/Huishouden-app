"""Database-operaties voor Weekmenu (Fase 2: opslaan; Fase 3: CRUD + ingrediëntenbeheer)."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.weekmenu import ingredient_categorization
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
    ShoppingCategory,
    ShoppingListItem,
    WeekPlanEntry,
)
from app.weekmenu.schemas import (
    IngredientOut,
    IngredientPatch,
    RecipeCreate,
    RecipeIngredientIn,
    RecipeIngredientOut,
    RecipeOut,
    RecipeUpdate,
)


def normalize_ingredient_name(name: str) -> str:
    """Lowercase + trimmed + enkelvoudige spaties — de dedupe-sleutel uit Fase 1."""
    return " ".join(name.lower().split())


def get_or_create_ingredient(db: Session, name: str) -> tuple[Ingredient, bool]:
    """Match op normalized_name: bestaand → hergebruiken (pantry_type en
    winkelcategorie blijven staan); nieuw → aanmaken met pantry_type = normal.
    De bool geeft aan of het net is aangemaakt (voor de auto-categorisering)."""
    normalized = normalize_ingredient_name(name)
    existing = db.scalar(select(Ingredient).where(Ingredient.normalized_name == normalized))
    if existing is not None:
        return existing, False
    ingredient = Ingredient(
        name=name.strip(), normalized_name=normalized, pantry_type=PantryType.NORMAL
    )
    db.add(ingredient)
    db.flush()  # id nodig vóór de koppelrijen
    return ingredient, True


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


def _build_ingredient_links(
    db: Session, items: list[RecipeIngredientIn]
) -> tuple[list[RecipeIngredient], list[Ingredient]]:
    """Koppelrijen voor een recept; dubbele ingrediënten binnen het recept worden
    samengevoegd tot één koppelrij (eerste hoeveelheid wint). Geeft ook de net
    aangemaakte (nog niet bestaande) ingrediënten terug, voor de auto-categorisering."""
    links: list[RecipeIngredient] = []
    new_ingredients: list[Ingredient] = []
    seen_ingredient_ids: set[int] = set()
    for item in items:
        ingredient, created = get_or_create_ingredient(db, item.name)
        if created:
            new_ingredients.append(ingredient)
        if ingredient.id in seen_ingredient_ids:
            continue
        seen_ingredient_ids.add(ingredient.id)
        links.append(
            RecipeIngredient(
                ingredient=ingredient,
                quantity=item.quantity,
                unit=item.unit,
                note=item.note,
            )
        )
    return links, new_ingredients


def _auto_categorize_new_ingredients(
    db: Session, new_ingredients: list[Ingredient], settings: Settings
) -> None:
    """Vraag voor elk NIEUW ingrediënt in dit request een winkelcategorie aan Claude
    (niet-fataal — zie ingredient_categorization.py). Bestaande ingrediënten worden
    hier nooit aan getoetst, ook niet als ze nog geen categorie hebben."""
    if not new_ingredients:
        return
    categories = list(db.scalars(select(ShoppingCategory)))
    if not categories:
        return
    mapping = ingredient_categorization.classify_ingredients(
        [i.name for i in new_ingredients], categories, settings
    )
    if not mapping:
        return
    for ingredient in new_ingredients:
        category_id = mapping.get(ingredient.name)
        if category_id is not None:
            ingredient.shopping_category_id = category_id
    db.commit()


def create_recipe(
    db: Session, data: RecipeCreate, photo_path: str | None, settings: Settings
) -> Recipe:
    """Recept + koppelrijen in één commit; nieuwe ingrediënten krijgen daarna best-effort
    een winkelcategorie via Claude (aparte, niet-fatale stap — zie hierboven)."""
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
    links, new_ingredients = _build_ingredient_links(db, data.ingredients)
    recipe.ingredients = links
    db.commit()
    db.refresh(recipe)
    _auto_categorize_new_ingredients(db, new_ingredients, settings)
    return recipe


def list_recipes(db: Session) -> list[Recipe]:
    return list(db.scalars(select(Recipe).order_by(func.lower(Recipe.title))))


def get_recipe(db: Session, recipe_id: int) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise WeekmenuError(404, "not_found", "Recept niet gevonden.")
    return recipe


def update_recipe(
    db: Session,
    recipe_id: int,
    data: RecipeUpdate,
    new_photo_path: str | None,
    settings: Settings,
) -> tuple[Recipe, str | None]:
    """Volledige vervanging van scalars + ingrediëntenlijst (delete-orphan ruimt de
    oude koppelrijen op; canonieke ingrediënten blijven altijd bestaan). Ingrediënten
    die door deze PUT voor het eerst worden aangemaakt, krijgen daarna best-effort een
    winkelcategorie (zie _auto_categorize_new_ingredients); al bestaande ingrediënten
    worden — ook zonder categorie — nooit opnieuw geclassificeerd.

    Geeft naast het recept de OUDE bestandsnaam terug die de router — ná de commit —
    van schijf mag verwijderen (None als de foto ongemoeid blijft). Bij een mislukte
    nieuwe opslag (new_photo_path is None zonder remove_photo) blijft de oude foto staan.
    """
    recipe = get_recipe(db, recipe_id)
    _check_attribute_ids(db, data)

    recipe.title = data.title.strip()
    recipe.description = data.description
    recipe.source_url = data.source_url
    recipe.moment_id = data.moment_id
    recipe.category_id = data.category_id
    recipe.time_id = data.time_id
    recipe.difficulty_id = data.difficulty_id
    links, new_ingredients = _build_ingredient_links(db, data.ingredients)
    recipe.ingredients = links

    photo_to_delete: str | None = None
    if new_photo_path is not None:
        photo_to_delete = recipe.photo_path
        recipe.photo_path = new_photo_path
    elif data.remove_photo:
        photo_to_delete = recipe.photo_path
        recipe.photo_path = None

    db.commit()
    db.refresh(recipe)
    _auto_categorize_new_ingredients(db, new_ingredients, settings)
    return recipe, photo_to_delete


def delete_recipe(db: Session, recipe_id: int) -> str | None:
    """Verwijder een recept + koppelrijen en ruim referenties expliciet op (SQLite
    dwingt FK's niet overal af — hangende referenties zouden Fase 4/5 stil corrumperen):
    weekplan-rijen verdwijnen mee (een rij zonder recept én zonder vrije tekst schendt
    de invariant), boodschappen-items verliezen enkel hun MENU-herkomst.

    Geeft de bestandsnaam van de foto terug zodat de router die van schijf verwijdert.
    """
    recipe = get_recipe(db, recipe_id)
    photo_path = recipe.photo_path
    db.execute(delete(WeekPlanEntry).where(WeekPlanEntry.recipe_id == recipe_id))
    db.execute(
        update(ShoppingListItem)
        .where(ShoppingListItem.recipe_id == recipe_id)
        .values(recipe_id=None)
    )
    db.delete(recipe)
    db.commit()
    return photo_path


def _ingredient_out(db: Session, ingredient: Ingredient) -> IngredientOut:
    recipe_count = db.scalar(
        select(func.count())
        .select_from(RecipeIngredient)
        .where(RecipeIngredient.ingredient_id == ingredient.id)
    )
    return IngredientOut(
        id=ingredient.id,
        name=ingredient.name,
        pantry_type=ingredient.pantry_type,
        shopping_category_id=ingredient.shopping_category_id,
        recipe_count=recipe_count or 0,
    )


def list_ingredients(db: Session) -> list[IngredientOut]:
    """Alle ingrediënten met het aantal recepten dat ze gebruikt (beheerscherm)."""
    rows = db.execute(
        select(Ingredient, func.count(RecipeIngredient.id))
        .outerjoin(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .group_by(Ingredient.id)
        .order_by(func.lower(Ingredient.name))
    ).all()
    return [
        IngredientOut(
            id=ingredient.id,
            name=ingredient.name,
            pantry_type=ingredient.pantry_type,
            shopping_category_id=ingredient.shopping_category_id,
            recipe_count=count,
        )
        for ingredient, count in rows
    ]


def patch_ingredient(db: Session, ingredient_id: int, patch: IngredientPatch) -> IngredientOut:
    """Gedeeltelijke update; alleen expliciet meegestuurde velden wijzigen."""
    ingredient = db.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise WeekmenuError(404, "not_found", "Ingrediënt niet gevonden.")

    fields = patch.model_fields_set
    if "name" in fields:
        assert patch.name is not None  # afgedwongen door schema-validator
        name = patch.name.strip()
        normalized = normalize_ingredient_name(name)
        clash = db.scalar(
            select(Ingredient).where(
                Ingredient.normalized_name == normalized, Ingredient.id != ingredient_id
            )
        )
        if clash is not None:
            raise WeekmenuError(
                409, "duplicate_ingredient", f"Er bestaat al een ingrediënt '{clash.name}'."
            )
        ingredient.name = name
        ingredient.normalized_name = normalized
    if "pantry_type" in fields:
        assert patch.pantry_type is not None  # afgedwongen door schema-validator
        ingredient.pantry_type = patch.pantry_type
    if "shopping_category_id" in fields:
        if (
            patch.shopping_category_id is not None
            and db.get(ShoppingCategory, patch.shopping_category_id) is None
        ):
            raise WeekmenuError(
                400,
                "unknown_attribute",
                f"Onbekende shopping_category_id: {patch.shopping_category_id}.",
            )
        ingredient.shopping_category_id = patch.shopping_category_id

    db.commit()
    db.refresh(ingredient)
    return _ingredient_out(db, ingredient)


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
