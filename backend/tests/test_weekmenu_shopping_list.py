"""Boodschappenlijst (Fase 5): GET synct de automatische items tegen de week,
POST/PATCH/DELETE beheren handmatige items en het afvinken. GET /pantry-check is de
"Nodig uit voorraadkast"-checklist: pantry-ingrediënten komen pas in de
boodschappenlijst als ze daar als 'niet op voorraad' aangevinkt zijn."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu.models import Ingredient, PantryType, ShoppingCategory, ShoppingListItem

LIST_URL = "/api/weekmenu/shopping-list"
ITEMS_URL = "/api/weekmenu/shopping-list/items"
MONDAY = date(2026, 7, 20)  # ma 20/07/2026


def _category(db: Session, name: str, sort_order: int = 0) -> ShoppingCategory:
    category = ShoppingCategory(name=name, color="#22c55e", sort_order=sort_order)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def _ingredient(
    db: Session,
    name: str,
    pantry_type: PantryType = PantryType.NORMAL,
    shopping_category_id: int | None = None,
) -> Ingredient:
    ingredient = Ingredient(
        name=name,
        normalized_name=name.lower(),
        pantry_type=pantry_type,
        shopping_category_id=shopping_category_id,
    )
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def _create_recipe(
    client: TestClient, title: str, ingredients: list[dict]
) -> int:
    resp = client.post(
        "/api/weekmenu/recipes", json={"title": title, "ingredients": ingredients}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _plan_day(client: TestClient, day: date, recipe_id: int) -> None:
    resp = client.put(f"/api/weekmenu/week/{day.isoformat()}", json={"recipe_id": recipe_id})
    assert resp.status_code == 200


# --- GET /shopping-list — synchronisatie ---


def test_lege_week_geeft_lege_lijst(logged_in: TestClient) -> None:
    resp = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()})
    assert resp.status_code == 200
    assert resp.json() == []


def test_always_home_verschijnt_nooit(logged_in: TestClient, db: Session) -> None:
    category = _category(db, "Voorraadkast")
    _ingredient(db, "Zout", pantry_type=PantryType.ALWAYS_HOME, shopping_category_id=category.id)
    recipe_id = _create_recipe(
        logged_in, "Pastasaus", [{"name": "Zout", "quantity": "1", "unit": "snuf"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert data == []


def test_pantry_ingredient_op_voorraad_verschijnt_niet_in_boodschappenlijst(
    logged_in: TestClient, db: Session
) -> None:
    """in_stock=True (default) betekent 'heb ik nog' — hoort niet in de lijst, enkel
    in de 'Nodig uit voorraadkast'-checklist (zie GET /pantry-check)."""
    _category(db, "Voorraadkast")
    _ingredient(db, "Couscous", pantry_type=PantryType.PANTRY)
    recipe_id = _create_recipe(
        logged_in, "Couscousschotel", [{"name": "Couscous", "quantity": "200", "unit": "g"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert data == []


def test_pantry_ingredient_die_nodig_is_gaat_naar_voorraadkast_ondanks_eigen_categorie(
    logged_in: TestClient, db: Session
) -> None:
    groenten = _category(db, "Groenten & Fruit", sort_order=0)
    voorraad = _category(db, "Voorraadkast", sort_order=1)
    ingredient = _ingredient(
        db, "Couscous", pantry_type=PantryType.PANTRY, shopping_category_id=groenten.id
    )
    recipe_id = _create_recipe(
        logged_in, "Couscousschotel", [{"name": "Couscous", "quantity": "200", "unit": "g"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    resp = logged_in.patch(f"/api/weekmenu/ingredients/{ingredient.id}", json={"in_stock": False})
    assert resp.status_code == 200

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["name"] == "Couscous"
    assert data[0]["category_id"] == voorraad.id
    assert data[0]["quantity"] == "200 g"
    assert data[0]["manually_added"] is False
    assert data[0]["ingredient_id"] == ingredient.id
    assert data[0]["in_stock"] is False


def test_pantry_terug_op_voorraad_verdwijnt_weer_uit_lijst(
    logged_in: TestClient, db: Session
) -> None:
    _category(db, "Voorraadkast")
    ingredient = _ingredient(db, "Bloem", pantry_type=PantryType.PANTRY)
    recipe_id = _create_recipe(
        logged_in, "Pannenkoeken", [{"name": "Bloem", "quantity": "300", "unit": "g"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    logged_in.patch(f"/api/weekmenu/ingredients/{ingredient.id}", json={"in_stock": False})
    assert len(logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()) == 1

    resp = logged_in.patch(f"/api/weekmenu/ingredients/{ingredient.id}", json={"in_stock": True})
    assert resp.status_code == 200

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert data == []


def test_normal_ingredient_zonder_categorie_valt_terug_op_overig(
    logged_in: TestClient, db: Session
) -> None:
    overig = _category(db, "Overig", sort_order=5)
    _ingredient(db, "Mosterd", shopping_category_id=None)
    recipe_id = _create_recipe(
        logged_in, "Vinaigrette", [{"name": "Mosterd", "quantity": None, "unit": None}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["category_id"] == overig.id
    assert data[0]["quantity"] is None


def test_zelfde_ingredient_in_twee_recepten_wordt_samengevoegd_met_plus(
    logged_in: TestClient, db: Session
) -> None:
    _category(db, "Groenten & Fruit")
    _ingredient(db, "Ui")
    recipe_a = _create_recipe(
        logged_in, "Soep", [{"name": "Ui", "quantity": "1", "unit": "stuk"}]
    )
    recipe_b = _create_recipe(
        logged_in, "Stoofpotje", [{"name": "Ui", "quantity": "2", "unit": "stuks"}]
    )
    _plan_day(logged_in, MONDAY, recipe_a)
    _plan_day(logged_in, date(2026, 7, 21), recipe_b)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["quantity"] == "1 stuk + 2 stuks"


def test_zelfde_recept_twee_dagen_telt_dubbel(logged_in: TestClient, db: Session) -> None:
    _category(db, "Groenten & Fruit")
    _ingredient(db, "Knoflook")
    recipe_id = _create_recipe(
        logged_in, "Pasta aglio olio", [{"name": "Knoflook", "quantity": "2", "unit": "tenen"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)
    _plan_day(logged_in, date(2026, 7, 23), recipe_id)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["quantity"] == "2 tenen + 2 tenen"


def test_checked_blijft_behouden_over_meerdere_gets(logged_in: TestClient, db: Session) -> None:
    _category(db, "Zuivel")
    _ingredient(db, "Melk")
    recipe_id = _create_recipe(
        logged_in, "Pannenkoeken", [{"name": "Melk", "quantity": "500", "unit": "ml"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    first = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    item_id = first[0]["id"]
    patch_resp = logged_in.patch(f"{ITEMS_URL}/{item_id}", json={"checked": True})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["checked"] is True

    second = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert second[0]["id"] == item_id
    assert second[0]["checked"] is True


def test_item_verdwijnt_zodra_recept_niet_meer_gepland_staat(
    logged_in: TestClient, db: Session
) -> None:
    _category(db, "Zuivel")
    _ingredient(db, "Boter")
    recipe_id = _create_recipe(
        logged_in, "Taart", [{"name": "Boter", "quantity": "100", "unit": "g"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)
    assert len(logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()) == 1

    # Dag leegmaken (recept verwijderen uit de weekplanning)
    resp = logged_in.put(
        f"/api/weekmenu/week/{MONDAY.isoformat()}",
        json={"recipe_id": None, "free_text": None, "checked": False},
    )
    assert resp.status_code == 200

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert data == []


def test_shopping_list_vereist_login(client: TestClient) -> None:
    assert client.get(LIST_URL, params={"start": MONDAY.isoformat()}).status_code == 401


# --- GET /pantry-check — "Nodig uit voorraadkast" ---

PANTRY_CHECK_URL = "/api/weekmenu/pantry-check"


def test_pantry_check_toont_zowel_op_voorraad_als_nodig(
    logged_in: TestClient, db: Session
) -> None:
    _category(db, "Voorraadkast")
    op_voorraad = _ingredient(db, "Rijst", pantry_type=PantryType.PANTRY)
    nodig = _ingredient(db, "Pasta", pantry_type=PantryType.PANTRY)
    recipe_id = _create_recipe(
        logged_in,
        "Combo",
        [
            {"name": "Rijst", "quantity": "200", "unit": "g"},
            {"name": "Pasta", "quantity": "300", "unit": "g"},
        ],
    )
    _plan_day(logged_in, MONDAY, recipe_id)
    logged_in.patch(f"/api/weekmenu/ingredients/{nodig.id}", json={"in_stock": False})

    data = logged_in.get(PANTRY_CHECK_URL, params={"start": MONDAY.isoformat()}).json()
    by_id = {row["ingredient_id"]: row for row in data}
    assert len(data) == 2
    assert by_id[op_voorraad.id]["in_stock"] is True
    assert by_id[op_voorraad.id]["quantity"] == "200 g"
    assert by_id[nodig.id]["in_stock"] is False


def test_pantry_check_sluit_always_home_en_normal_uit(
    logged_in: TestClient, db: Session
) -> None:
    _category(db, "Voorraadkast")
    _ingredient(db, "Zout", pantry_type=PantryType.ALWAYS_HOME)
    _ingredient(db, "Ui", pantry_type=PantryType.NORMAL)
    recipe_id = _create_recipe(
        logged_in,
        "Soep",
        [
            {"name": "Zout", "quantity": "1", "unit": "snuf"},
            {"name": "Ui", "quantity": "1", "unit": "stuk"},
        ],
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    data = logged_in.get(PANTRY_CHECK_URL, params={"start": MONDAY.isoformat()}).json()
    assert data == []


def test_pantry_check_lege_week(logged_in: TestClient) -> None:
    resp = logged_in.get(PANTRY_CHECK_URL, params={"start": MONDAY.isoformat()})
    assert resp.status_code == 200
    assert resp.json() == []


def test_pantry_check_vereist_login(client: TestClient) -> None:
    assert client.get(PANTRY_CHECK_URL, params={"start": MONDAY.isoformat()}).status_code == 401


# --- GET /herbs-check — "Nodig uit kruidenkast" (zelfde principe als pantry-check) ---

HERBS_CHECK_URL = "/api/weekmenu/herbs-check"


def test_herbs_en_pantry_check_zijn_gescheiden_lijsten(
    logged_in: TestClient, db: Session
) -> None:
    """PANTRY-ingrediënten horen enkel in /pantry-check, HERBS enkel in /herbs-check."""
    _category(db, "Voorraadkast")
    _category(db, "Kruiden", sort_order=1)
    _ingredient(db, "Rijst", pantry_type=PantryType.PANTRY)
    _ingredient(db, "Basilicum", pantry_type=PantryType.HERBS)
    recipe_id = _create_recipe(
        logged_in,
        "Risotto",
        [
            {"name": "Rijst", "quantity": "200", "unit": "g"},
            {"name": "Basilicum", "quantity": "1", "unit": "bosje"},
        ],
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    pantry = logged_in.get(PANTRY_CHECK_URL, params={"start": MONDAY.isoformat()}).json()
    herbs = logged_in.get(HERBS_CHECK_URL, params={"start": MONDAY.isoformat()}).json()
    assert [row["name"] for row in pantry] == ["Rijst"]
    assert [row["name"] for row in herbs] == ["Basilicum"]


def test_herbs_op_voorraad_verschijnt_niet_in_boodschappenlijst(
    logged_in: TestClient, db: Session
) -> None:
    """HERBS gedraagt zich als PANTRY: op voorraad (default) → niet op de lijst."""
    _category(db, "Kruiden")
    _ingredient(db, "Oregano", pantry_type=PantryType.HERBS)
    recipe_id = _create_recipe(
        logged_in, "Pizza", [{"name": "Oregano", "quantity": "1", "unit": "el"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    assert logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json() == []


def test_herbs_nodig_gaat_naar_kruiden_categorie_ondanks_eigen_categorie(
    logged_in: TestClient, db: Session
) -> None:
    """Weergave-override: een HERBS-ingrediënt dat nodig is, groepeert onder "Kruiden"
    ongeacht z'n eigen winkelcategorie — analoog aan PANTRY → "Voorraadkast"."""
    groenten = _category(db, "Groenten & Fruit", sort_order=0)
    kruiden = _category(db, "Kruiden", sort_order=1)
    ingredient = _ingredient(
        db, "Peterselie", pantry_type=PantryType.HERBS, shopping_category_id=groenten.id
    )
    recipe_id = _create_recipe(
        logged_in, "Tabouleh", [{"name": "Peterselie", "quantity": "1", "unit": "bosje"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    resp = logged_in.patch(f"/api/weekmenu/ingredients/{ingredient.id}", json={"in_stock": False})
    assert resp.status_code == 200

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["name"] == "Peterselie"
    assert data[0]["category_id"] == kruiden.id
    assert data[0]["in_stock"] is False


def test_herbs_check_vereist_login(client: TestClient) -> None:
    assert client.get(HERBS_CHECK_URL, params={"start": MONDAY.isoformat()}).status_code == 401


# --- Boodschappenlijst toont de geschreven vorm (canonieke basis bij conflict) ---


def test_shopping_list_toont_geschreven_vorm(logged_in: TestClient, db: Session) -> None:
    _category(db, "Overig")
    recipe_id = _create_recipe(
        logged_in, "Stoofpot", [{"name": "dikke wortelen", "quantity": "3", "unit": "stuks"}]
    )
    _plan_day(logged_in, MONDAY, recipe_id)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1
    assert data[0]["name"] == "dikke wortelen"  # geschreven vorm, niet canoniek "wortelen"


def test_shopping_list_canonieke_basis_bij_conflict(logged_in: TestClient, db: Session) -> None:
    _category(db, "Overig")
    a = _create_recipe(logged_in, "A", [{"name": "wortels", "quantity": "2", "unit": "stuks"}])
    b = _create_recipe(
        logged_in,
        "B",
        [{"name": "dikke wortelen", "quantity": "3", "unit": "stuks"}],
    )
    _plan_day(logged_in, MONDAY, a)
    _plan_day(logged_in, date(2026, 7, 21), b)

    data = logged_in.get(LIST_URL, params={"start": MONDAY.isoformat()}).json()
    assert len(data) == 1  # beide vallen onder canoniek "wortelen"
    assert data[0]["name"] == "wortelen"  # verschillende geschreven vormen → canonieke basis


# --- Handmatige items ---


def test_post_handmatig_item(logged_in: TestClient, db: Session) -> None:
    category = _category(db, "Overig")
    resp = logged_in.post(
        ITEMS_URL, json={"name": "Afwasmiddel", "category_id": category.id, "quantity": "1 fles"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Afwasmiddel"
    assert data["manually_added"] is True
    assert data["checked"] is False
    assert data["quantity"] == "1 fles"
    assert data["ingredient_id"] is None
    assert data["in_stock"] is None


def test_post_handmatig_item_onbekende_categorie_geeft_400(logged_in: TestClient) -> None:
    resp = logged_in.post(ITEMS_URL, json={"name": "Afwasmiddel", "category_id": 999})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_attribute"


def test_post_handmatig_item_lege_naam_geeft_422(logged_in: TestClient, db: Session) -> None:
    category = _category(db, "Overig")
    resp = logged_in.post(ITEMS_URL, json={"name": "  ", "category_id": category.id})
    assert resp.status_code == 422


def test_patch_checked_op_handmatig_item(logged_in: TestClient, db: Session) -> None:
    category = _category(db, "Overig")
    item_id = logged_in.post(
        ITEMS_URL, json={"name": "Kaarsen", "category_id": category.id}
    ).json()["id"]

    resp = logged_in.patch(f"{ITEMS_URL}/{item_id}", json={"checked": True})
    assert resp.status_code == 200
    assert resp.json()["checked"] is True


def test_patch_onbekend_item_geeft_404(logged_in: TestClient) -> None:
    resp = logged_in.patch(f"{ITEMS_URL}/999", json={"checked": True})
    assert resp.status_code == 404


def test_delete_handmatig_item(logged_in: TestClient, db: Session) -> None:
    category = _category(db, "Overig")
    item_id = logged_in.post(
        ITEMS_URL, json={"name": "Kaarsen", "category_id": category.id}
    ).json()["id"]

    resp = logged_in.delete(f"{ITEMS_URL}/{item_id}")
    assert resp.status_code == 204
    assert db.get(ShoppingListItem, item_id) is None


def test_delete_onbekend_item_geeft_404(logged_in: TestClient) -> None:
    resp = logged_in.delete(f"{ITEMS_URL}/999")
    assert resp.status_code == 404


def test_post_vereist_login(client: TestClient) -> None:
    resp = client.post(ITEMS_URL, json={"name": "X", "category_id": 1})
    assert resp.status_code == 401


def test_patch_vereist_login(client: TestClient) -> None:
    resp = client.patch(f"{ITEMS_URL}/1", json={"checked": True})
    assert resp.status_code == 401


def test_delete_vereist_login(client: TestClient) -> None:
    assert client.delete(f"{ITEMS_URL}/1").status_code == 401
