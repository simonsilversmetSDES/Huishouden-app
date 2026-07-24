"""Database-operaties voor Weekmenu (Fase 2: opslaan; Fase 3: CRUD + ingrediëntenbeheer;
Fase 4: weekplanning)."""

from datetime import date, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.weekmenu import ingredient_categorization
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.ingredient_names import canonicalize_ingredient_name, is_herb
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
    PantryCheckItemOut,
    RecipeCreate,
    RecipeIngredientIn,
    RecipeIngredientOut,
    RecipeOut,
    RecipeUpdate,
    ShoppingListItemCreate,
    ShoppingListItemOut,
    WeekPlanDayIn,
    WeekPlanDayOut,
)
from app.weekmenu.servings import scale_quantity


def normalize_ingredient_name(name: str) -> str:
    """Lowercase + trimmed + enkelvoudige spaties — de dedupe-sleutel uit Fase 1."""
    return " ".join(name.lower().split())


def get_or_create_ingredient(db: Session, name: str) -> tuple[Ingredient, bool]:
    """Canonicaliseer de naam (voorvoegsels weg, synoniemen samengevoegd) en match op
    normalized_name: bestaand → hergebruiken (pantry_type en winkelcategorie blijven
    staan); nieuw → aanmaken met pantry_type = normal. De bool geeft aan of het net is
    aangemaakt (voor de auto-categorisering). De GESCHREVEN naam bewaart de aanroeper
    apart als display_name op de koppelrij."""
    canonical = canonicalize_ingredient_name(name)
    normalized = normalize_ingredient_name(canonical)
    existing = db.scalar(select(Ingredient).where(Ingredient.normalized_name == normalized))
    if existing is not None:
        return existing, False
    # Nieuw kruid/specerij komt meteen als 'herbs' binnen (zelfde detectie als de
    # opschoonmigratie); al de rest start als 'normal'.
    pantry_type = PantryType.HERBS if is_herb(canonical) else PantryType.NORMAL
    ingredient = Ingredient(
        name=canonical, normalized_name=normalized, pantry_type=pantry_type
    )
    db.add(ingredient)
    db.flush()  # id nodig vóór de koppelrijen
    return ingredient, True


def _check_attribute_ids(db: Session, data: RecipeCreate) -> None:
    """Onbekende FK-ids → nette 400 in plaats van een IntegrityError-500."""
    for model, value, label in (
        (RecipeTime, data.time_id, "time_id"),
        (RecipeDifficulty, data.difficulty_id, "difficulty_id"),
    ):
        if value is not None and db.get(model, value) is None:
            raise WeekmenuError(400, "unknown_attribute", f"Onbekende {label}: {value}.")
    for moment_id in data.moment_ids:
        if db.get(RecipeMoment, moment_id) is None:
            raise WeekmenuError(400, "unknown_attribute", f"Onbekende moment_id: {moment_id}.")
    for category_id in data.category_ids:
        if db.get(RecipeCategory, category_id) is None:
            raise WeekmenuError(
                400, "unknown_attribute", f"Onbekende category_id: {category_id}."
            )


def _resolve_categories(db: Session, category_ids: list[int]) -> list[RecipeCategory]:
    """Dedupe met behoud van volgorde; ids zijn al gevalideerd door _check_attribute_ids."""
    unique_ids = list(dict.fromkeys(category_ids))
    return [db.get(RecipeCategory, category_id) for category_id in unique_ids]


def _resolve_moments(db: Session, moment_ids: list[int]) -> list[RecipeMoment]:
    """Dedupe met behoud van volgorde; ids zijn al gevalideerd door _check_attribute_ids."""
    unique_ids = list(dict.fromkeys(moment_ids))
    return [db.get(RecipeMoment, moment_id) for moment_id in unique_ids]


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
                display_name=item.name.strip(),  # geschreven naam blijft in het recept staan
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
        time_id=data.time_id,
        difficulty_id=data.difficulty_id,
        servings=data.servings,
    )
    db.add(recipe)
    recipe.moments = _resolve_moments(db, data.moment_ids)
    recipe.categories = _resolve_categories(db, data.category_ids)
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


def patch_recipe_servings(db: Session, recipe_id: int, servings: int) -> Recipe:
    """Aantal personen bijwerken (stepper op de receptpagina) + ingrediënten lineair
    herschalen t.o.v. het vorige aantal (of 1 als er nog geen bekend was), zodat de
    opgeslagen hoeveelheden altijd bij het getoonde aantal personen blijven horen."""
    recipe = get_recipe(db, recipe_id)
    factor = servings / (recipe.servings or 1)
    if factor != 1:
        for link in recipe.ingredients:
            link.quantity = scale_quantity(link.quantity, factor)
    recipe.servings = servings
    db.commit()
    db.refresh(recipe)
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
    recipe.moments = _resolve_moments(db, data.moment_ids)
    recipe.categories = _resolve_categories(db, data.category_ids)
    recipe.time_id = data.time_id
    recipe.difficulty_id = data.difficulty_id
    recipe.servings = data.servings
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
        in_stock=ingredient.in_stock,
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
            in_stock=ingredient.in_stock,
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
    if "in_stock" in fields:
        assert patch.in_stock is not None  # afgedwongen door schema-validator
        ingredient.in_stock = patch.in_stock
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


def _week_day_out(day: date, entry: WeekPlanEntry | None) -> WeekPlanDayOut:
    if entry is None:
        return WeekPlanDayOut(
            date=day,
            recipe_id=None,
            recipe_title=None,
            recipe_photo_path=None,
            free_text=None,
            checked=False,
            servings=None,
        )
    return WeekPlanDayOut(
        date=day,
        recipe_id=entry.recipe_id,
        recipe_title=entry.recipe.title if entry.recipe else None,
        recipe_photo_path=entry.recipe.photo_path if entry.recipe else None,
        free_text=entry.free_text,
        checked=entry.checked,
        servings=entry.servings,
    )


def get_week(db: Session, start: date) -> list[WeekPlanDayOut]:
    """Zeven dagen vanaf ``start``; dagen zonder rij worden als lege dag
    gesynthetiseerd (de tabel hoeft niet vooraf gevuld te zijn)."""
    end = start + timedelta(days=6)
    entries = {
        entry.date: entry
        for entry in db.scalars(
            select(WeekPlanEntry).where(WeekPlanEntry.date.between(start, end))
        )
    }
    return [
        _week_day_out(start + timedelta(days=offset), entries.get(start + timedelta(days=offset)))
        for offset in range(7)
    ]


def upsert_week_day(db: Session, day: date, data: WeekPlanDayIn) -> WeekPlanDayOut:
    """Get-or-create op datum; zet de drie velden zoals meegegeven."""
    if data.recipe_id is not None and db.get(Recipe, data.recipe_id) is None:
        raise WeekmenuError(400, "unknown_attribute", f"Onbekend recipe_id: {data.recipe_id}.")

    entry = db.scalar(select(WeekPlanEntry).where(WeekPlanEntry.date == day))
    if entry is None:
        entry = WeekPlanEntry(date=day)
        db.add(entry)

    entry.recipe_id = data.recipe_id
    entry.free_text = data.free_text
    entry.checked = data.checked
    entry.servings = data.servings
    db.commit()
    db.refresh(entry)
    return _week_day_out(day, entry)


VOORRAADKAST_CATEGORY_NAME = "Voorraadkast"
KRUIDEN_CATEGORY_NAME = "Kruiden"
OVERIG_CATEGORY_NAME = "Overig"

# pantry_type → naam van de winkelcategorie waaronder die groep altijd gegroepeerd
# wordt in de boodschappenlijst (weergave-override; het ingrediënt z'n eigen
# shopping_category_id blijft ongemoeid). Bestaat die categorie niet, dan valt de
# terugval-keten in _resolve_shopping_category_id gewoon door.
_PANTRY_TYPE_CATEGORY_OVERRIDE = {
    PantryType.PANTRY: VOORRAADKAST_CATEGORY_NAME,
    PantryType.HERBS: KRUIDEN_CATEGORY_NAME,
}

# pantry_types met een "op voorraad"-toggle: ze verschijnen pas op de boodschappenlijst
# zodra in_stock is uitgezet, en hebben elk hun eigen "Nodig uit …"-checklist.
STOCKABLE_PANTRY_TYPES = (PantryType.PANTRY, PantryType.HERBS)


def _resolve_shopping_category_id(db: Session, ingredient: Ingredient) -> int:
    """Terugval-keten voor de NOT NULL category_id op ShoppingListItem.

    ``pantry_type == PANTRY`` groepeert altijd onder "Voorraadkast" en ``HERBS`` onder
    "Kruiden" (weergave-override — ``ingredient.shopping_category_id`` blijft ongemoeid).
    Bestaat die categorie niet meer (verwijderd via Beheer), dan valt terug op het
    ingrediënt z'n eigen categorie, dan op "Overig", dan op de eerste categorie op
    ``sort_order``. Is er geen enkele ``shopping_category`` meer over, dan kan de rij niet
    opgeslagen worden.
    """

    def _by_name(name: str) -> ShoppingCategory | None:
        return db.scalar(select(ShoppingCategory).where(ShoppingCategory.name == name))

    override_name = _PANTRY_TYPE_CATEGORY_OVERRIDE.get(ingredient.pantry_type)
    if override_name is not None:
        override_category = _by_name(override_name)
        if override_category is not None:
            return override_category.id

    if ingredient.shopping_category_id is not None:
        return ingredient.shopping_category_id

    fallback = _by_name(OVERIG_CATEGORY_NAME)
    if fallback is not None:
        return fallback.id

    first = db.scalar(select(ShoppingCategory).order_by(ShoppingCategory.sort_order))
    if first is not None:
        return first.id

    raise WeekmenuError(
        409,
        "no_shopping_categories",
        "Er is geen winkelcategorie ingesteld — maak er minstens één aan in Beheer.",
    )


def _format_quantity_part(quantity: str | None, unit: str | None) -> str | None:
    part = f"{quantity or ''} {unit or ''}".strip()
    return part or None


def _pick_display_name(display_names: list[str | None], canonical_name: str) -> str:
    """Toon de geschreven vorm als alle bijdragen dezelfde gebruiken; bij verschillende
    geschreven vormen op dezelfde canonieke basis → de canonieke naam (keuze Simon)."""
    distinct = {name for name in display_names if name}
    if len(distinct) == 1:
        return next(iter(distinct))
    return canonical_name


def _week_ingredient_contributions(
    db: Session, start: date
) -> dict[int, list[tuple[str | None, str | None]]]:
    """Per ingrediënt (behalve ``always_home``) de losse bijdragen voor deze week als
    (hoeveelheid-deel, geschreven naam). Eenzelfde recept dat 2× gepland staat, telt 2×
    mee. Bewust GEEN samenvoeging/optelling over eenheden heen — zie
    ``sync_and_get_shopping_list``."""
    end = start + timedelta(days=6)
    entries = db.scalars(
        select(WeekPlanEntry).where(
            WeekPlanEntry.date.between(start, end), WeekPlanEntry.recipe_id.is_not(None)
        )
    )
    contributions: dict[int, list[tuple[str | None, str | None]]] = {}
    for entry in entries:
        for link in entry.recipe.ingredients:
            if link.ingredient.pantry_type == PantryType.ALWAYS_HOME:
                continue
            contributions.setdefault(link.ingredient_id, []).append(
                (_format_quantity_part(link.quantity, link.unit), link.display_name)
            )
    return contributions


def get_pantry_check(
    db: Session, start: date, pantry_type: PantryType = PantryType.PANTRY
) -> list[PantryCheckItemOut]:
    """De volledige "Nodig uit …"-checklist voor één afvinkbaar voorraadtype: alle
    ingrediënten van dat type (``PANTRY`` → "Nodig uit voorraadkast", ``HERBS`` → "Nodig
    uit kruidenkast") die ergens in een recept van deze week zitten, ongeacht
    ``in_stock`` — dit is een leesfunctie, ze muteert niets. De gebruiker duidt hier aan
    wat er niet (meer) op voorraad is; ``sync_and_get_shopping_list`` neemt dat vervolgens
    over in de boodschappenlijst."""
    contributions = _week_ingredient_contributions(db, start)
    items: list[PantryCheckItemOut] = []
    for ingredient_id, parts in contributions.items():
        ingredient = db.get(Ingredient, ingredient_id)
        assert ingredient is not None  # FK garandeert bestaan
        if ingredient.pantry_type != pantry_type:
            continue
        quantity = " + ".join(q for q, _ in parts if q is not None) or None
        items.append(
            PantryCheckItemOut(
                ingredient_id=ingredient_id,
                name=_pick_display_name([d for _, d in parts], ingredient.name),
                quantity=quantity,
                in_stock=ingredient.in_stock,
            )
        )
    items.sort(key=lambda item: item.name.lower())
    return items


def _shopping_item_out(db: Session, item: ShoppingListItem) -> ShoppingListItemOut:
    """``in_stock`` zit niet op ShoppingListItem zelf — komt van het gekoppelde
    ingrediënt (enkel gezet voor automatische items, `None` voor handmatige)."""
    in_stock = None
    if item.ingredient_id is not None:
        ingredient = db.get(Ingredient, item.ingredient_id)
        in_stock = ingredient.in_stock if ingredient is not None else None
    return ShoppingListItemOut(
        id=item.id,
        name=item.name,
        category_id=item.category_id,
        checked=item.checked,
        manually_added=item.manually_added,
        quantity=item.quantity,
        ingredient_id=item.ingredient_id,
        in_stock=in_stock,
    )


def sync_and_get_shopping_list(db: Session, start: date) -> list[ShoppingListItemOut]:
    """Synct de automatische (niet-handmatige) items tegen de recepten van deze week en
    geeft de volledige lijst (handmatig + automatisch) terug.

    Ongewijzigd blijvende items behouden hun ``checked``-status; niet langer benodigde
    automatische items verdwijnen. Er is maar één actieve lijst (geen geschiedenis per
    week) — een andere ``start`` opvragen hersynct het automatische deel naar díe week.
    Categorieën worden eerst allemaal opgelost vóórdat er iets gewijzigd wordt, zodat een
    ontbrekende winkelcategorie (zie ``_resolve_shopping_category_id``) niet halverwege
    een gedeeltelijke wijziging achterlaat.

    Een afvinkbaar voorraad-ingrediënt (``pantry_type`` in ``STOCKABLE_PANTRY_TYPES``:
    ``PANTRY`` of ``HERBS``) komt hier enkel in terecht als ``in_stock`` is uitgezet —
    zolang het nog op voorraad staat, hoort het niet op de boodschappenlijst maar enkel in
    de bijhorende "Nodig uit …"-checklist (zie ``get_pantry_check``). Dat voorkomt dat de
    lijst vol komt te staan met dingen die je toch al hebt.
    """
    contributions = _week_ingredient_contributions(db, start)

    resolved: dict[int, tuple[str, int, str | None]] = {}
    for ingredient_id, parts in contributions.items():
        ingredient = db.get(Ingredient, ingredient_id)
        assert ingredient is not None  # FK garandeert bestaan
        if ingredient.pantry_type in STOCKABLE_PANTRY_TYPES and ingredient.in_stock:
            continue
        category_id = _resolve_shopping_category_id(db, ingredient)
        quantity = " + ".join(q for q, _ in parts if q is not None) or None
        name = _pick_display_name([d for _, d in parts], ingredient.name)
        resolved[ingredient_id] = (name, category_id, quantity)

    existing = {
        item.ingredient_id: item
        for item in db.scalars(
            select(ShoppingListItem).where(ShoppingListItem.manually_added.is_(False))
        )
    }

    for ingredient_id, (name, category_id, quantity) in resolved.items():
        item = existing.get(ingredient_id)
        if item is None:
            db.add(
                ShoppingListItem(
                    name=name,
                    category_id=category_id,
                    manually_added=False,
                    ingredient_id=ingredient_id,
                    quantity=quantity,
                )
            )
        else:
            item.name = name
            item.category_id = category_id
            item.quantity = quantity

    stale_ids = set(existing) - set(resolved)
    if stale_ids:
        db.execute(delete(ShoppingListItem).where(ShoppingListItem.ingredient_id.in_(stale_ids)))

    db.commit()

    items = db.scalars(
        select(ShoppingListItem)
        .join(ShoppingCategory)
        .order_by(ShoppingCategory.sort_order, func.lower(ShoppingListItem.name))
    )
    return [_shopping_item_out(db, item) for item in items]


def create_manual_shopping_item(
    db: Session, data: ShoppingListItemCreate
) -> ShoppingListItemOut:
    if db.get(ShoppingCategory, data.category_id) is None:
        raise WeekmenuError(
            400, "unknown_attribute", f"Onbekende category_id: {data.category_id}."
        )
    item = ShoppingListItem(
        name=data.name.strip(),
        category_id=data.category_id,
        quantity=data.quantity,
        manually_added=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _shopping_item_out(db, item)


def patch_shopping_list_item(db: Session, item_id: int, checked: bool) -> ShoppingListItemOut:
    item = db.get(ShoppingListItem, item_id)
    if item is None:
        raise WeekmenuError(404, "not_found", "Boodschappen-item niet gevonden.")
    item.checked = checked
    db.commit()
    db.refresh(item)
    return _shopping_item_out(db, item)


def delete_shopping_list_item(db: Session, item_id: int) -> None:
    item = db.get(ShoppingListItem, item_id)
    if item is None:
        raise WeekmenuError(404, "not_found", "Boodschappen-item niet gevonden.")
    db.delete(item)
    db.commit()


def recipe_to_out(recipe: Recipe) -> RecipeOut:
    """Handmatige serialisatie: ``name`` is de geschreven naam (display_name, met
    terugval op de canonieke ingrediëntnaam voor oude data); pantry_type komt van het
    canonieke ingrediënt."""
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        photo_path=recipe.photo_path,
        source_url=recipe.source_url,
        moment_ids=recipe.moment_ids,
        category_ids=recipe.category_ids,
        time_id=recipe.time_id,
        difficulty_id=recipe.difficulty_id,
        servings=recipe.servings,
        ingredients=[
            RecipeIngredientOut(
                id=link.id,
                ingredient_id=link.ingredient_id,
                name=link.display_name or link.ingredient.name,
                pantry_type=link.ingredient.pantry_type,
                quantity=link.quantity,
                unit=link.unit,
                note=link.note,
            )
            for link in recipe.ingredients
        ],
    )
