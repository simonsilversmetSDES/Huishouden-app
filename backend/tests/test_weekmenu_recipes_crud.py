"""Recept-CRUD (Fase 3): lijst, detail, PUT (incl. foto-statemachine) en DELETE."""

import base64
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu import photos
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.models import (
    Ingredient,
    PantryType,
    Recipe,
    RecipeIngredient,
    ShoppingCategory,
    ShoppingListItem,
    WeekPlanEntry,
)
from app.weekmenu.url_security import FetchResult

RECIPES_URL = "/api/weekmenu/recipes"
PNG_B64 = base64.b64encode(b"png-bytes").decode()


def _payload(**overrides) -> dict:
    payload = {
        "title": "Spaghetti bolognese",
        "description": "Fruit de ui.",
        "ingredients": [{"name": "Gehakt", "quantity": "500", "unit": "g"}],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def photo_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(photos, "PHOTOS_DIR", tmp_path)
    return tmp_path


def _create(client: TestClient, **overrides) -> dict:
    resp = client.post(RECIPES_URL, json=_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()


# --- Lijst + detail ---


def test_lege_lijst(logged_in: TestClient) -> None:
    resp = logged_in.get(RECIPES_URL)
    assert resp.status_code == 200
    assert resp.json() == []


def test_lijst_is_licht_en_gesorteerd_op_titel(logged_in: TestClient) -> None:
    _create(logged_in, title="bbb-recept")
    _create(logged_in, title="Aaa-recept")
    data = logged_in.get(RECIPES_URL).json()
    assert [r["title"] for r in data] == ["Aaa-recept", "bbb-recept"]
    assert "ingredients" not in data[0]  # lichtgewicht schema
    assert "created_at" in data[0]


def test_detail_geeft_volledig_recept(logged_in: TestClient) -> None:
    created = _create(logged_in)
    resp = logged_in.get(f"{RECIPES_URL}/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Spaghetti bolognese"
    assert data["ingredients"][0]["name"] == "Gehakt"


def test_detail_404(logged_in: TestClient) -> None:
    resp = logged_in.get(f"{RECIPES_URL}/999")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


def test_lijst_vereist_login(client: TestClient) -> None:
    assert client.get(RECIPES_URL).status_code == 401


# --- PUT: scalars + ingrediëntenlijst ---


def test_put_vervangt_scalars_en_ingredienten(logged_in: TestClient, db: Session) -> None:
    created = _create(
        logged_in,
        ingredients=[{"name": "Gehakt"}, {"name": "Ui"}],
    )
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(
            title="Lasagne",
            description="Nieuwe stappen.",
            ingredients=[{"name": "Ui", "quantity": "1"}, {"name": "Tomaat"}],
        ),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Lasagne"
    assert sorted(i["name"] for i in data["ingredients"]) == ["Tomaat", "Ui"]
    # Oude koppelrijen weg, canonieke ingrediënten blijven bestaan.
    assert db.query(RecipeIngredient).count() == 2
    assert {i.name for i in db.query(Ingredient)} == {"Gehakt", "Ui", "Tomaat"}


def test_put_behoudt_pantry_type_van_bestaand_ingredient(
    logged_in: TestClient, db: Session
) -> None:
    db.add(Ingredient(name="Pasta", normalized_name="pasta", pantry_type=PantryType.PANTRY))
    db.commit()
    created = _create(logged_in)
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}", json=_payload(ingredients=[{"name": "pasta"}])
    )
    assert resp.status_code == 200
    assert resp.json()["ingredients"][0]["pantry_type"] == "pantry"


def test_put_onbekend_attribuut_geeft_400(logged_in: TestClient) -> None:
    created = _create(logged_in)
    resp = logged_in.put(f"{RECIPES_URL}/{created['id']}", json=_payload(moment_id=999))
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_attribute"


def test_put_404(logged_in: TestClient) -> None:
    assert logged_in.put(f"{RECIPES_URL}/999", json=_payload()).status_code == 404


# --- Foto's: upload (photo_base64), download (photo_url) en de PUT-statemachine ---


def test_create_met_photo_base64_schrijft_bestand(
    logged_in: TestClient, db: Session, photo_dir
) -> None:
    data = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    assert data["photo_path"] is not None and data["photo_path"].endswith(".png")
    assert (photo_dir / data["photo_path"]).read_bytes() == b"png-bytes"
    assert db.query(Recipe).one().photo_path == data["photo_path"]


def test_create_photo_base64_ongeldig_media_type_geeft_422(logged_in: TestClient) -> None:
    resp = logged_in.post(
        RECIPES_URL, json=_payload(photo_base64=PNG_B64, photo_media_type="image/tiff")
    )
    assert resp.status_code == 422


def test_create_photo_base64_te_groot_geeft_422(logged_in: TestClient) -> None:
    too_big = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
    resp = logged_in.post(
        RECIPES_URL, json=_payload(photo_base64=too_big, photo_media_type="image/png")
    )
    assert resp.status_code == 422


def test_create_photo_url_en_base64_samen_geeft_422(logged_in: TestClient) -> None:
    resp = logged_in.post(
        RECIPES_URL,
        json=_payload(
            photo_url="https://example.com/foto.jpg",
            photo_base64=PNG_B64,
            photo_media_type="image/png",
        ),
    )
    assert resp.status_code == 422


def test_put_nieuwe_foto_vervangt_oude(logged_in: TestClient, photo_dir) -> None:
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    old_name = created["photo_path"]
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(
            photo_base64=base64.b64encode(b"nieuwe-bytes").decode(),
            photo_media_type="image/jpeg",
        ),
    )
    assert resp.status_code == 200
    new_name = resp.json()["photo_path"]
    assert new_name != old_name and new_name.endswith(".jpg")
    assert (photo_dir / new_name).read_bytes() == b"nieuwe-bytes"
    assert not (photo_dir / old_name).exists()


def test_put_mislukte_download_behoudt_oude_foto(
    logged_in: TestClient, photo_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    old_name = created["photo_path"]

    def dead_fetch(url: str, max_bytes: int) -> FetchResult:
        raise WeekmenuError(502, "fetch_failed", "De pagina kon niet opgehaald worden.")

    monkeypatch.setattr(photos, "fetch_url", dead_fetch)
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(photo_url="https://example.com/dood.jpg"),
    )
    assert resp.status_code == 200
    assert resp.json()["photo_path"] == old_name
    assert (photo_dir / old_name).exists()


def test_put_remove_photo_verwijdert_bestand(logged_in: TestClient, photo_dir) -> None:
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    resp = logged_in.put(f"{RECIPES_URL}/{created['id']}", json=_payload(remove_photo=True))
    assert resp.status_code == 200
    assert resp.json()["photo_path"] is None
    assert list(photo_dir.iterdir()) == []


def test_put_remove_photo_met_nieuwe_foto_geeft_422(logged_in: TestClient) -> None:
    created = _create(logged_in)
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(remove_photo=True, photo_base64=PNG_B64, photo_media_type="image/png"),
    )
    assert resp.status_code == 422


def test_put_zonder_fotovelden_laat_foto_staan(logged_in: TestClient, photo_dir) -> None:
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    resp = logged_in.put(f"{RECIPES_URL}/{created['id']}", json=_payload(title="Anders"))
    assert resp.status_code == 200
    assert resp.json()["photo_path"] == created["photo_path"]
    assert (photo_dir / created["photo_path"]).exists()


def test_put_geweigerd_laat_geen_wees_foto_achter(logged_in: TestClient, photo_dir) -> None:
    """Nieuwe foto al weggeschreven maar commit geweigerd (onbekend attribuut) →
    de nieuwe file wordt opgeruimd en de oude blijft staan."""
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(
            moment_id=999,
            photo_base64=base64.b64encode(b"wees-bytes").decode(),
            photo_media_type="image/png",
        ),
    )
    assert resp.status_code == 400
    assert [p.name for p in photo_dir.iterdir()] == [created["photo_path"]]


# --- DELETE ---


def test_delete_verwijdert_recept_koppelrijen_en_foto(
    logged_in: TestClient, db: Session, photo_dir
) -> None:
    created = _create(logged_in, photo_base64=PNG_B64, photo_media_type="image/png")
    resp = logged_in.delete(f"{RECIPES_URL}/{created['id']}")
    assert resp.status_code == 204
    assert db.query(Recipe).count() == 0
    assert db.query(RecipeIngredient).count() == 0
    assert db.query(Ingredient).count() == 1  # canoniek ingrediënt blijft
    assert list(photo_dir.iterdir()) == []


def test_delete_ruimt_weekplan_en_boodschappen_referenties_op(
    logged_in: TestClient, db: Session
) -> None:
    created = _create(logged_in)
    category = ShoppingCategory(name="Overig", color="#6b7280", sort_order=0)
    db.add(category)
    db.flush()
    db.add(WeekPlanEntry(date=date(2026, 7, 20), recipe_id=created["id"]))
    db.add(
        ShoppingListItem(
            name="Gehakt", category_id=category.id, manually_added=False, recipe_id=created["id"]
        )
    )
    db.commit()

    assert logged_in.delete(f"{RECIPES_URL}/{created['id']}").status_code == 204
    assert db.query(WeekPlanEntry).count() == 0  # dag-invulling verdwijnt mee
    item = db.query(ShoppingListItem).one()
    assert item.recipe_id is None  # item blijft, verliest MENU-herkomst


def test_delete_404(logged_in: TestClient) -> None:
    assert logged_in.delete(f"{RECIPES_URL}/999").status_code == 404


def test_delete_vereist_login(client: TestClient) -> None:
    assert client.delete(f"{RECIPES_URL}/1").status_code == 401
