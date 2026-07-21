"""Attribuut- en winkelcategorie-CRUD (Fase 3-beheerscherm), generiek over de 5 paden."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu.models import (
    Ingredient,
    Recipe,
    RecipeCategory,
    ShoppingCategory,
    ShoppingListItem,
)
from app.weekmenu.seed import seed_weekmenu

BASE = "/api/weekmenu"

# (pad, heeft kleur, eerste seed-naam op sort_order)
RESOURCES = [
    ("moments", False, "Lunch"),
    ("categories", True, "Vis"),
    ("times", False, "Snel"),
    ("difficulties", False, "Makkelijk"),
    ("shopping-categories", True, "Groenten & Fruit"),
]


@pytest.fixture
def seeded(db: Session) -> Session:
    seed_weekmenu(db)
    db.commit()
    return db


def _in_payload(has_color: bool, name: str = "Nieuw", sort_order: int = 99) -> dict:
    payload = {"name": name, "sort_order": sort_order}
    if has_color:
        payload["color"] = "#123456"
    return payload


@pytest.mark.parametrize(("path", "has_color", "first_name"), RESOURCES)
def test_get_geeft_seed_in_sorteervolgorde(
    logged_in: TestClient, seeded: Session, path: str, has_color: bool, first_name: str
) -> None:
    resp = logged_in.get(f"{BASE}/{path}")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == first_name
    assert data == sorted(data, key=lambda row: row["sort_order"])
    assert ("color" in data[0]) == has_color


@pytest.mark.parametrize(("path", "has_color", "first_name"), RESOURCES)
def test_post_maakt_nieuwe_rij(
    logged_in: TestClient, seeded: Session, path: str, has_color: bool, first_name: str
) -> None:
    resp = logged_in.post(f"{BASE}/{path}", json=_in_payload(has_color))
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Nieuw"
    names = [row["name"] for row in logged_in.get(f"{BASE}/{path}").json()]
    assert "Nieuw" in names


@pytest.mark.parametrize("path", ["categories", "shopping-categories"])
def test_post_zonder_kleur_geeft_422_bij_gekleurde_tabellen(
    logged_in: TestClient, seeded: Session, path: str
) -> None:
    assert logged_in.post(f"{BASE}/{path}", json=_in_payload(False)).status_code == 422


@pytest.mark.parametrize(("path", "has_color", "first_name"), RESOURCES)
def test_post_duplicaatnaam_geeft_409(
    logged_in: TestClient, seeded: Session, path: str, has_color: bool, first_name: str
) -> None:
    # Trim/case-insensitief: " lunch " botst met "Lunch".
    resp = logged_in.post(
        f"{BASE}/{path}", json=_in_payload(has_color, name=f"  {first_name.lower()}  ")
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "duplicate_name"


@pytest.mark.parametrize(("path", "has_color", "first_name"), RESOURCES)
def test_put_hernoemt_en_hersorteert(
    logged_in: TestClient, seeded: Session, path: str, has_color: bool, first_name: str
) -> None:
    row = logged_in.get(f"{BASE}/{path}").json()[0]
    resp = logged_in.put(
        f"{BASE}/{path}/{row['id']}", json=_in_payload(has_color, name="Hernoemd", sort_order=5)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Hernoemd"
    assert data["sort_order"] == 5


def test_put_eigen_naam_op_zichzelf_mag(logged_in: TestClient, seeded: Session) -> None:
    row = logged_in.get(f"{BASE}/moments").json()[0]
    resp = logged_in.put(f"{BASE}/moments/{row['id']}", json=_in_payload(False, name=row["name"]))
    assert resp.status_code == 200


def test_put_duplicaatnaam_van_andere_rij_geeft_409(logged_in: TestClient, seeded: Session) -> None:
    rows = logged_in.get(f"{BASE}/moments").json()
    resp = logged_in.put(
        f"{BASE}/moments/{rows[0]['id']}", json=_in_payload(False, name=rows[1]["name"])
    )
    assert resp.status_code == 409


def test_put_404(logged_in: TestClient, seeded: Session) -> None:
    assert logged_in.put(f"{BASE}/moments/999", json=_in_payload(False)).status_code == 404


@pytest.mark.parametrize(("path", "has_color", "first_name"), RESOURCES)
def test_delete_ongebruikte_rij(
    logged_in: TestClient, seeded: Session, path: str, has_color: bool, first_name: str
) -> None:
    created = logged_in.post(f"{BASE}/{path}", json=_in_payload(has_color)).json()
    assert logged_in.delete(f"{BASE}/{path}/{created['id']}").status_code == 204
    names = [row["name"] for row in logged_in.get(f"{BASE}/{path}").json()]
    assert "Nieuw" not in names


def test_delete_404(logged_in: TestClient, seeded: Session) -> None:
    assert logged_in.delete(f"{BASE}/moments/999").status_code == 404


# --- DELETE blokkeert bij gebruik (409 in_use) ---


@pytest.mark.parametrize(
    ("path", "fk_field"),
    [
        ("moments", "moment_id"),
        ("times", "time_id"),
        ("difficulties", "difficulty_id"),
    ],
)
def test_delete_attribuut_in_gebruik_door_recept_geeft_409(
    logged_in: TestClient, seeded: Session, path: str, fk_field: str
) -> None:
    row = logged_in.get(f"{BASE}/{path}").json()[0]
    seeded.add(Recipe(title="Testrecept", **{fk_field: row["id"]}))
    seeded.commit()
    resp = logged_in.delete(f"{BASE}/{path}/{row['id']}")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "in_use"


def test_delete_categorie_in_gebruik_door_recept_geeft_409(
    logged_in: TestClient, seeded: Session
) -> None:
    """Categorieën zijn many-to-many — kunnen niet via een simpele FK-kwarg gekoppeld
    worden zoals de andere attributen hierboven."""
    row = logged_in.get(f"{BASE}/categories").json()[0]
    category = seeded.get(RecipeCategory, row["id"])
    seeded.add(Recipe(title="Testrecept", categories=[category]))
    seeded.commit()
    resp = logged_in.delete(f"{BASE}/categories/{row['id']}")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "in_use"


def test_delete_winkelcategorie_in_gebruik_door_ingredient_geeft_409(
    logged_in: TestClient, seeded: Session
) -> None:
    row = logged_in.get(f"{BASE}/shopping-categories").json()[0]
    seeded.add(Ingredient(name="Appel", normalized_name="appel", shopping_category_id=row["id"]))
    seeded.commit()
    assert logged_in.delete(f"{BASE}/shopping-categories/{row['id']}").status_code == 409


def test_delete_winkelcategorie_in_gebruik_door_boodschappenitem_geeft_409(
    logged_in: TestClient, seeded: Session
) -> None:
    category = seeded.query(ShoppingCategory).first()
    seeded.add(ShoppingListItem(name="Melk", category_id=category.id))
    seeded.commit()
    assert logged_in.delete(f"{BASE}/shopping-categories/{category.id}").status_code == 409


def test_attribuut_crud_vereist_login(client: TestClient) -> None:
    assert client.get(f"{BASE}/moments").status_code == 401
    assert client.post(f"{BASE}/moments", json=_in_payload(False)).status_code == 401
