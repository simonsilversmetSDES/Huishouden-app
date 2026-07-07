"""Regel-endpoints (spec §5.3): CRUD + toepassen via de API.

De engine-semantiek zelf wordt in test_rules.py getest; hier gaat het om de
HTTP-laag: login-vereiste, validatie (categorie-context, regex), en dat 'apply'
ongecategoriseerde transacties bijwerkt en de count teruggeeft.
"""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Context, Transaction
from app.models.enums import Categorization, CategoryType


def _context_id(db: Session, name: str = "Gemeenschappelijk") -> int:
    return db.scalars(select(Context).where(Context.name == name)).one().id


def _category(db: Session, context_id: int, name: str) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context_id, Category.name == name)
    ).one()


def _rule_body(context_id: int, category_id: int, **overrides: object) -> dict:
    body = {
        "context_id": context_id,
        "match_field": "counterparty_name",
        "match_type": "contains",
        "match_value": "JUST RUSSEL",
        "category_id": category_id,
        "priority": 100,
    }
    body.update(overrides)
    return body


class TestRulesCrud:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/rules", params={"context_id": 1}).status_code == 401

    def test_aanmaken_lijsten_en_verwijderen(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        resp = logged_in.post("/api/rules", json=_rule_body(ctx, katten.id))
        assert resp.status_code == 201
        created = resp.json()
        assert created["category_name"] == "Katten"
        assert created["match_value"] == "JUST RUSSEL"
        assert created["created_from_correction"] is False

        listed = logged_in.get("/api/rules", params={"context_id": ctx}).json()
        assert any(r["id"] == created["id"] for r in listed)

        assert logged_in.delete(f"/api/rules/{created['id']}").status_code == 204
        listed_na = logged_in.get("/api/rules", params={"context_id": ctx}).json()
        assert all(r["id"] != created["id"] for r in listed_na)

    def test_bewerken(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        boodschappen = _category(seeded_db, ctx, "Boodschappen")
        rule_id = logged_in.post("/api/rules", json=_rule_body(ctx, katten.id)).json()["id"]
        resp = logged_in.put(
            f"/api/rules/{rule_id}",
            json=_rule_body(ctx, boodschappen.id, match_value="COLRUYT", priority=50),
        )
        assert resp.status_code == 200
        assert resp.json()["category_name"] == "Boodschappen"
        assert resp.json()["priority"] == 50

    def test_categorie_van_andere_context_404(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        gem = _context_id(seeded_db, "Gemeenschappelijk")
        simon_cat = _category(seeded_db, _context_id(seeded_db, "Simon"), "Boodschappen")
        resp = logged_in.post("/api/rules", json=_rule_body(gem, simon_cat.id))
        assert resp.status_code == 404

    def test_ongeldige_regex_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        resp = logged_in.post(
            "/api/rules",
            json=_rule_body(ctx, katten.id, match_type="regex", match_value="[onafgesloten"),
        )
        assert resp.status_code == 422

    def test_lege_matchwaarde_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        resp = logged_in.post("/api/rules", json=_rule_body(ctx, katten.id, match_value="   "))
        assert resp.status_code == 422

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        assert logged_in.get("/api/rules", params={"context_id": 999}).status_code == 404


class TestApplyEndpoint:
    def test_apply_categoriseert_en_telt(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        katten = _category(seeded_db, ctx, "Katten")
        logged_in.post(
            "/api/rules", json=_rule_body(ctx, katten.id, match_field="description")
        )
        seeded_db.add(
            Transaction(
                context_id=ctx,
                date=date(2026, 6, 15),
                amount=Decimal("-25.00"),
                type=CategoryType.UITGAVEN,
                description="JUST RUSSEL DRONGEN",
                categorization=Categorization.UNCATEGORIZED,
            )
        )
        seeded_db.commit()

        resp = logged_in.post("/api/rules/apply", params={"context_id": ctx})
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

        tx = seeded_db.scalars(
            select(Transaction).where(Transaction.description == "JUST RUSSEL DRONGEN")
        ).one()
        seeded_db.refresh(tx)
        assert tx.category_id == katten.id
        assert tx.categorization == Categorization.AUTO


class TestTransactionCounterparty:
    def test_transactieout_bevat_tegenpartij(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _context_id(seeded_db)
        seeded_db.add(
            Transaction(
                context_id=ctx,
                date=date(2026, 6, 15),
                amount=Decimal("-25.00"),
                type=CategoryType.UITGAVEN,
                counterparty_name="JUST RUSSEL",
                counterparty_iban="BE68539007547034",
                description="Kattenvoer",
            )
        )
        seeded_db.commit()
        resp = logged_in.get("/api/transactions", params={"context_id": ctx, "year": 2026})
        assert resp.status_code == 200
        row = next(r for r in resp.json() if r["description"] == "Kattenvoer")
        assert row["counterparty_name"] == "JUST RUSSEL"
        assert row["counterparty_iban"] == "BE68539007547034"
