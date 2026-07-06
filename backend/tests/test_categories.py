"""Categorieën-endpoint: actieve categorieën per context, optioneel gefilterd op type.

Voedt het transactieformulier (spec §5.1): de categorie-keuze hangt af van de
actieve context en het gekozen type.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Context


def _gem_context_id(db: Session) -> int:
    return db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).one().id


class TestCategoriesEndpoint:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/categories", params={"context_id": 1}).status_code == 401

    def test_lijst_per_context(self, logged_in: TestClient, seeded_db: Session) -> None:
        """Alle actieve categorieën van de context, in sort_order-volgorde."""
        context_id = _gem_context_id(seeded_db)
        resp = logged_in.get("/api/categories", params={"context_id": context_id})
        assert resp.status_code == 200
        categories = resp.json()
        assert len(categories) == 21  # volledige seed-lijst (Gemeenschappelijk)
        assert {c["type"] for c in categories} == {"Inkomen", "Uitgaven", "Sparen"}
        assert all({"id", "name", "type"} <= c.keys() for c in categories)
        # sort_order bepaalt de volgorde: seed zet Inkomen eerst
        assert categories[0]["type"] == "Inkomen"

    def test_filter_op_type(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _gem_context_id(seeded_db)
        resp = logged_in.get(
            "/api/categories", params={"context_id": context_id, "type": "Uitgaven"}
        )
        assert resp.status_code == 200
        categories = resp.json()
        assert categories, "seed bevat Uitgaven-categorieën"
        assert all(c["type"] == "Uitgaven" for c in categories)
        assert "Boodschappen" in [c["name"] for c in categories]

    def test_inactieve_verborgen(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _gem_context_id(seeded_db)
        boodschappen = seeded_db.scalars(
            select(Category).where(
                Category.context_id == context_id, Category.name == "Boodschappen"
            )
        ).one()
        boodschappen.active = False
        seeded_db.commit()

        resp = logged_in.get("/api/categories", params={"context_id": context_id})
        assert "Boodschappen" not in [c["name"] for c in resp.json()]

    def test_context_scheiding(self, logged_in: TestClient, seeded_db: Session) -> None:
        """Categorieën van Simon lekken niet naar Gemeenschappelijk en omgekeerd."""
        gem_id = _gem_context_id(seeded_db)
        simon_id = seeded_db.scalars(select(Context).where(Context.name == "Simon")).one().id
        gem_ids = {c["id"] for c in logged_in.get(
            "/api/categories", params={"context_id": gem_id}
        ).json()}
        simon_ids = {c["id"] for c in logged_in.get(
            "/api/categories", params={"context_id": simon_id}
        ).json()}
        assert gem_ids and simon_ids
        assert gem_ids.isdisjoint(simon_ids)

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        assert logged_in.get("/api/categories", params={"context_id": 999}).status_code == 404

    def test_ongeldig_type_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _gem_context_id(seeded_db)
        resp = logged_in.get(
            "/api/categories", params={"context_id": context_id, "type": "Onzin"}
        )
        assert resp.status_code == 422
