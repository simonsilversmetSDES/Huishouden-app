"""Categorieën-endpoint: actieve categorieën per context, optioneel gefilterd op type.

Voedt het transactieformulier (spec §5.1): de categorie-keuze hangt af van de
actieve context en het gekozen type.
"""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category, Context, Transaction
from app.models.enums import Categorization, CategoryType, MatchField, MatchType


def _gem_context_id(db: Session) -> int:
    return db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).one().id


def _category(db: Session, context_id: int, name: str) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context_id, Category.name == name)
    ).one()


def _names(client: TestClient, context_id: int) -> list[str]:
    resp = client.get("/api/categories", params={"context_id": context_id})
    return [c["name"] for c in resp.json()]


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


class TestCreateCategory:
    def _body(self, context_id: int, name: str = "Tuin", type_: str = "Uitgaven") -> dict:
        return {"context_id": context_id, "name": name, "type": type_}

    def test_vereist_login(self, client: TestClient) -> None:
        assert client.post("/api/categories", json=self._body(1)).status_code == 401

    def test_toevoegen(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        resp = logged_in.post("/api/categories", json=self._body(ctx))
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Tuin"
        assert created["type"] == "Uitgaven"
        assert "Tuin" in _names(logged_in, ctx)

    def test_toevoegen_raakt_andere_context_niet(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        gem = _gem_context_id(seeded_db)
        simon = seeded_db.scalars(select(Context).where(Context.name == "Simon")).one().id
        logged_in.post("/api/categories", json=self._body(gem, name="Tuin"))
        assert "Tuin" not in _names(logged_in, simon)

    def test_duplicaat_actief_409(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        resp = logged_in.post("/api/categories", json=self._body(ctx, name="Boodschappen"))
        assert resp.status_code == 409

    def test_lege_naam_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        resp = logged_in.post("/api/categories", json=self._body(ctx, name="   "))
        assert resp.status_code == 422

    def test_reactiveert_gedeactiveerde(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        assert logged_in.delete(f"/api/categories/{katten.id}").status_code == 204
        # opnieuw toevoegen met dezelfde sleutel reactiveert dezelfde rij
        resp = logged_in.post("/api/categories", json=self._body(ctx, name="Katten"))
        assert resp.status_code == 201
        assert resp.json()["id"] == katten.id
        assert "Katten" in _names(logged_in, ctx)

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        assert logged_in.post("/api/categories", json=self._body(999)).status_code == 404


class TestDeleteCategory:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.delete("/api/categories/1").status_code == 401

    def test_verbergt_uit_lijst_maar_behoudt_transactie(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _gem_context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        tx = Transaction(
            context_id=ctx,
            date=date(2026, 6, 15),
            amount=Decimal("-25.00"),
            type=CategoryType.UITGAVEN,
            category_id=katten.id,
            description="Kattenvoer",
            categorization=Categorization.MANUAL,
        )
        seeded_db.add(tx)
        seeded_db.commit()

        assert logged_in.delete(f"/api/categories/{katten.id}").status_code == 204
        assert "Katten" not in _names(logged_in, ctx)
        # de transactie blijft bestaan met haar categorie
        seeded_db.refresh(tx)
        assert tx.category_id == katten.id

    def test_verwijdert_verwijzende_regels(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _gem_context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        seeded_db.add(
            CategorizationRule(
                context_id=ctx,
                priority=100,
                match_field=MatchField.COUNTERPARTY_NAME,
                match_type=MatchType.CONTAINS,
                match_value="JUST RUSSEL",
                category_id=katten.id,
            )
        )
        seeded_db.commit()

        assert logged_in.delete(f"/api/categories/{katten.id}").status_code == 204
        resterend = seeded_db.scalars(
            select(CategorizationRule).where(CategorizationRule.category_id == katten.id)
        ).all()
        assert resterend == []

    def test_onbekende_categorie_404(self, logged_in: TestClient) -> None:
        assert logged_in.delete("/api/categories/999").status_code == 404
