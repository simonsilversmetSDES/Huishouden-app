"""Automatische winkelcategorie voor nieuw aangemaakte ingrediënten. Geen netwerk:
de Claude-client wordt gemockt zoals in test_weekmenu_parse.py."""

import json
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu import ingredient_categorization
from app.weekmenu.models import Ingredient, ShoppingCategory

RECIPES_URL = "/api/weekmenu/recipes"


class _FakeMessages:
    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


@pytest.fixture
def shopping_categories(db: Session) -> dict[str, ShoppingCategory]:
    groenten = ShoppingCategory(name="Groenten & Fruit", color="#22c55e", sort_order=0)
    vlees = ShoppingCategory(name="Vlees & Vis", color="#ef4444", sort_order=1)
    db.add_all([groenten, vlees])
    db.commit()
    return {"Groenten & Fruit": groenten, "Vlees & Vis": vlees}


def _mock_claude(monkeypatch: pytest.MonkeyPatch, reply: str | None = None, error=None):
    messages = _FakeMessages(reply=reply, error=error)
    monkeypatch.setattr(
        ingredient_categorization,
        "get_claude_client",
        lambda settings: SimpleNamespace(messages=messages),
    )
    return messages


def _payload(**overrides) -> dict:
    payload = {"title": "Testrecept", "ingredients": [{"name": "Ui", "quantity": "1"}]}
    payload.update(overrides)
    return payload


def test_nieuw_ingredient_krijgt_categorie_van_claude(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_claude(monkeypatch, reply=json.dumps({"Ui": "Groenten & Fruit"}))
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    ingredient = db.query(Ingredient).filter_by(normalized_name="ui").one()
    assert ingredient.shopping_category_id == shopping_categories["Groenten & Fruit"].id


def test_bestaand_ingredient_wordt_nooit_hergeclassificeerd(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ook een bestaand ingrediënt ZONDER categorie mag niet aangeraakt worden — enkel
    net aangemaakte ingrediënten gaan naar Claude."""
    existing = Ingredient(name="Ui", normalized_name="ui")  # bewust geen categorie
    db.add(existing)
    db.commit()

    messages = _mock_claude(monkeypatch, reply=json.dumps({"Peterselie": "Groenten & Fruit"}))
    resp = logged_in.post(
        RECIPES_URL,
        json=_payload(ingredients=[{"name": "Ui"}, {"name": "Peterselie"}]),
    )
    assert resp.status_code == 201

    # Claude kreeg alleen de nieuwe naam te zien, niet "Ui".
    assert len(messages.calls) == 1
    prompt = messages.calls[0]["messages"][0]["content"]
    assert "Peterselie" in prompt
    assert '"Ui"' not in prompt

    db.refresh(existing)
    assert existing.shopping_category_id is None  # ongemoeid
    peterselie = db.query(Ingredient).filter_by(normalized_name="peterselie").one()
    assert peterselie.shopping_category_id == shopping_categories["Groenten & Fruit"].id


def test_ai_fout_is_niet_fataal(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_claude(monkeypatch, error=anthropic.APIConnectionError(request=SimpleNamespace()))
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201  # recept wordt gewoon opgeslagen
    ingredient = db.query(Ingredient).filter_by(normalized_name="ui").one()
    assert ingredient.shopping_category_id is None


def test_ongeldig_antwoord_is_niet_fataal(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_claude(monkeypatch, reply="dit is geen JSON")
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    ingredient = db.query(Ingredient).filter_by(normalized_name="ui").one()
    assert ingredient.shopping_category_id is None


def test_onbekende_categorienaam_wordt_genegeerd(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_claude(monkeypatch, reply=json.dumps({"Ui": "Niet-bestaande categorie"}))
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    ingredient = db.query(Ingredient).filter_by(normalized_name="ui").one()
    assert ingredient.shopping_category_id is None


def test_geen_winkelcategorieen_slaat_classificatie_over(
    logged_in: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Geen enkele winkelcategorie in de db → geen Claude-call, geen crash."""
    messages = _mock_claude(monkeypatch, reply=json.dumps({"Ui": "Overig"}))
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    assert messages.calls == []


def test_geen_nieuwe_ingredienten_slaat_classificatie_over(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.add(Ingredient(name="Ui", normalized_name="ui"))
    db.commit()
    messages = _mock_claude(monkeypatch, reply=json.dumps({}))
    resp = logged_in.post(RECIPES_URL, json=_payload())
    assert resp.status_code == 201
    assert messages.calls == []


def test_put_categoriseert_alleen_de_nieuw_toegevoegde_ingredienten(
    logged_in: TestClient, db: Session, shopping_categories, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_claude(monkeypatch, reply=json.dumps({"Ui": "Groenten & Fruit"}))
    created = logged_in.post(RECIPES_URL, json=_payload()).json()

    messages = _mock_claude(monkeypatch, reply=json.dumps({"Gehakt": "Vlees & Vis"}))
    resp = logged_in.put(
        f"{RECIPES_URL}/{created['id']}",
        json=_payload(ingredients=[{"name": "Ui"}, {"name": "Gehakt"}]),
    )
    assert resp.status_code == 200
    assert len(messages.calls) == 1
    assert "Gehakt" in messages.calls[0]["messages"][0]["content"]
    assert '"Ui"' not in messages.calls[0]["messages"][0]["content"]

    ui = db.query(Ingredient).filter_by(normalized_name="ui").one()
    gehakt = db.query(Ingredient).filter_by(normalized_name="gehakt").one()
    assert ui.shopping_category_id == shopping_categories["Groenten & Fruit"].id
    assert gehakt.shopping_category_id == shopping_categories["Vlees & Vis"].id


def test_classify_ingredients_zonder_namen_of_categorieen(db: Session) -> None:
    settings = SimpleNamespace(anthropic_api_key="x", anthropic_model="claude-haiku-4-5")
    assert ingredient_categorization.classify_ingredients([], [ShoppingCategory()], settings) == {}
    assert ingredient_categorization.classify_ingredients(["Ui"], [], settings) == {}
