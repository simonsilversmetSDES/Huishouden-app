"""Recept opslaan (POST /api/weekmenu/recipes): ingrediënt-matching + foto-download."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu import photos
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.models import Ingredient, PantryType, Recipe, RecipeIngredient
from app.weekmenu.url_security import FetchResult

RECIPES_URL = "/api/weekmenu/recipes"


def _payload(**overrides) -> dict:
    payload = {
        "title": "Spaghetti bolognese",
        "description": "Fruit de ui.\nVoeg het gehakt toe.",
        "source_url": "https://example.com/recept",
        "ingredients": [{"name": "Gehakt", "quantity": "500", "unit": "g"}],
    }
    payload.update(overrides)
    return payload


def test_nieuw_ingredient_krijgt_pantry_type_normal(logged_in: TestClient, db: Session) -> None:
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Spaghetti bolognese"
    assert data["photo_path"] is None
    assert data["ingredients"][0]["name"] == "Gehakt"
    assert data["ingredients"][0]["pantry_type"] == "normal"
    ingredient = db.query(Ingredient).one()
    assert ingredient.normalized_name == "gehakt"
    assert ingredient.pantry_type == PantryType.NORMAL


def test_bestaand_ingredient_hergebruikt_met_behoud_pantry_type(
    logged_in: TestClient, db: Session
) -> None:
    """Match op normalized_name: id hergebruiken en pantry_type NIET overschrijven."""
    existing = Ingredient(name="Pasta", normalized_name="pasta", pantry_type=PantryType.PANTRY)
    db.add(existing)
    db.commit()

    resp = logged_in.post(
        RECIPES_URL,
        json=_payload(ingredients=[{"name": " Pasta ", "quantity": "400", "unit": "g"}]),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ingredients"][0]["ingredient_id"] == existing.id
    assert data["ingredients"][0]["pantry_type"] == "pantry"
    assert db.query(Ingredient).count() == 1  # geen duplicaat aangemaakt
    db.refresh(existing)
    assert existing.pantry_type == PantryType.PANTRY
    assert existing.name == "Pasta"  # ook de weergavenaam blijft staan


def test_normalisatie_matcht_hoofdletters_en_spaties(logged_in: TestClient, db: Session) -> None:
    db.add(Ingredient(name="ui", normalized_name="ui"))
    db.commit()
    resp = logged_in.post(RECIPES_URL, json=_payload(ingredients=[{"name": "  Ui  "}]))
    assert resp.status_code == 201
    assert db.query(Ingredient).count() == 1


def test_dubbel_ingredient_in_een_recept_wordt_een_koppelrij(
    logged_in: TestClient, db: Session
) -> None:
    resp = logged_in.post(
        RECIPES_URL,
        json=_payload(
            ingredients=[
                {"name": "Ui", "quantity": "2"},
                {"name": " ui ", "quantity": "1"},
            ]
        ),
    )
    assert resp.status_code == 201
    assert db.query(Ingredient).count() == 1
    assert db.query(RecipeIngredient).count() == 1


def test_onbekende_categorie_geeft_400(logged_in: TestClient, db: Session) -> None:
    resp = logged_in.post(RECIPES_URL, json=_payload(category_ids=[999]))
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_attribute"
    assert db.query(Recipe).count() == 0


def test_lege_titel_geeft_422(logged_in: TestClient) -> None:
    assert logged_in.post(RECIPES_URL, json=_payload(title="   ")).status_code == 422


def test_opslaan_vereist_login(client: TestClient) -> None:
    assert client.post(RECIPES_URL, json=_payload()).status_code == 401


# --- Foto-download bij opslaan (Fase 2-beslissing: nooit een externe URL in de db) ---


@pytest.fixture
def photo_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(photos, "PHOTOS_DIR", tmp_path)
    return tmp_path


def test_foto_wordt_lokaal_opgeslagen(
    logged_in: TestClient, db: Session, photo_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch(url: str, max_bytes: int) -> FetchResult:
        return FetchResult(content=b"jpeg-bytes", content_type="image/jpeg", final_url=url)

    monkeypatch.setattr(photos, "fetch_url", fake_fetch)
    resp = logged_in.post(RECIPES_URL, json=_payload(photo_url="https://example.com/foto.jpg"))
    assert resp.status_code == 201
    photo_path = resp.json()["photo_path"]
    assert photo_path is not None and photo_path.endswith(".jpg")
    assert "example.com" not in photo_path  # bestandsnaam, geen externe URL
    assert (photo_dir / photo_path).read_bytes() == b"jpeg-bytes"
    assert db.query(Recipe).one().photo_path == photo_path


def test_mislukte_fotodownload_is_niet_fataal(
    logged_in: TestClient, db: Session, photo_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dead_fetch(url: str, max_bytes: int) -> FetchResult:
        raise WeekmenuError(502, "fetch_failed", "De pagina kon niet opgehaald worden.")

    monkeypatch.setattr(photos, "fetch_url", dead_fetch)
    resp = logged_in.post(RECIPES_URL, json=_payload(photo_url="https://example.com/dood.jpg"))
    assert resp.status_code == 201  # recept wordt gewoon zonder foto opgeslagen
    assert resp.json()["photo_path"] is None
    assert db.query(Recipe).one().photo_path is None


def test_niet_afbeelding_content_type_geeft_geen_foto(
    logged_in: TestClient, photo_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def html_fetch(url: str, max_bytes: int) -> FetchResult:
        return FetchResult(content=b"<html>", content_type="text/html", final_url=url)

    monkeypatch.setattr(photos, "fetch_url", html_fetch)
    resp = logged_in.post(RECIPES_URL, json=_payload(photo_url="https://example.com/pagina"))
    assert resp.status_code == 201
    assert resp.json()["photo_path"] is None
    assert list(photo_dir.iterdir()) == []
