"""Ingrediëntenbeheer (Fase 3): GET met recipe_count + gedeeltelijke PATCH."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu.models import Ingredient, PantryType, ShoppingCategory

INGREDIENTS_URL = "/api/weekmenu/ingredients"
RECIPES_URL = "/api/weekmenu/recipes"


@pytest.fixture
def ui_id(db: Session) -> int:
    ingredient = Ingredient(name="Ui", normalized_name="ui")
    db.add(ingredient)
    db.commit()
    return ingredient.id


def test_lijst_gesorteerd_met_recipe_count(logged_in: TestClient, db: Session) -> None:
    db.add(Ingredient(name="zout", normalized_name="zout", pantry_type=PantryType.ALWAYS_HOME))
    db.commit()
    resp = logged_in.post(
        RECIPES_URL,
        json={"title": "Soep", "ingredients": [{"name": "Ajuin"}]},
    )
    assert resp.status_code == 201

    data = logged_in.get(INGREDIENTS_URL).json()
    assert [row["name"] for row in data] == ["Ajuin", "zout"]  # case-insensitief gesorteerd
    assert data[0]["recipe_count"] == 1
    assert data[1]["recipe_count"] == 0
    assert data[1]["pantry_type"] == "always_home"
    assert data[0]["in_stock"] is True  # default bij aanmaak


def test_patch_in_stock(logged_in: TestClient, db: Session, ui_id: int) -> None:
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"in_stock": False})
    assert resp.status_code == 200
    assert resp.json()["in_stock"] is False
    db.expire_all()
    assert db.get(Ingredient, ui_id).in_stock is False

    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"in_stock": True})
    assert resp.status_code == 200
    assert resp.json()["in_stock"] is True


def test_patch_in_stock_null_geeft_422(logged_in: TestClient, ui_id: int) -> None:
    assert (
        logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"in_stock": None}).status_code == 422
    )


def test_patch_pantry_type(logged_in: TestClient, db: Session, ui_id: int) -> None:
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"pantry_type": "pantry"})
    assert resp.status_code == 200
    assert resp.json()["pantry_type"] == "pantry"
    db.expire_all()
    assert db.get(Ingredient, ui_id).pantry_type == PantryType.PANTRY


def test_patch_winkelcategorie_zetten_en_expliciet_nullen(
    logged_in: TestClient, db: Session, ui_id: int
) -> None:
    category = ShoppingCategory(name="Groenten & Fruit", color="#22c55e", sort_order=0)
    db.add(category)
    db.commit()

    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"shopping_category_id": category.id})
    assert resp.status_code == 200
    assert resp.json()["shopping_category_id"] == category.id

    # Expliciete null wist de koppeling (onderscheid met 'veld niet meegestuurd').
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"shopping_category_id": None})
    assert resp.status_code == 200
    assert resp.json()["shopping_category_id"] is None


def test_patch_raakt_afwezige_velden_niet_aan(
    logged_in: TestClient, db: Session, ui_id: int
) -> None:
    logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"pantry_type": "pantry"})
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": "Ajuin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Ajuin"
    assert data["pantry_type"] == "pantry"  # niet teruggevallen op default


def test_patch_rename_herberekent_normalized_name(
    logged_in: TestClient, db: Session, ui_id: int
) -> None:
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": "  Rode Ui  "})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Rode Ui"
    db.expire_all()
    assert db.get(Ingredient, ui_id).normalized_name == "rode ui"


def test_patch_rename_botsing_geeft_409(logged_in: TestClient, db: Session, ui_id: int) -> None:
    db.add(Ingredient(name="Ajuin", normalized_name="ajuin"))
    db.commit()
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": " AJUIN "})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "duplicate_ingredient"


def test_patch_self_rename_zelfde_normalisatie_mag(logged_in: TestClient, ui_id: int) -> None:
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": "ui"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "ui"


def test_patch_lege_naam_geeft_422(logged_in: TestClient, ui_id: int) -> None:
    assert logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": "   "}).status_code == 422
    assert logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"name": None}).status_code == 422


def test_patch_pantry_type_null_geeft_422(logged_in: TestClient, ui_id: int) -> None:
    assert (
        logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"pantry_type": None}).status_code == 422
    )


def test_patch_onbekende_winkelcategorie_geeft_400(logged_in: TestClient, ui_id: int) -> None:
    resp = logged_in.patch(f"{INGREDIENTS_URL}/{ui_id}", json={"shopping_category_id": 999})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_attribute"


def test_patch_404(logged_in: TestClient) -> None:
    assert logged_in.patch(f"{INGREDIENTS_URL}/999", json={"name": "X"}).status_code == 404


def test_ingredienten_vereisen_login(client: TestClient) -> None:
    assert client.get(INGREDIENTS_URL).status_code == 401
