"""Budgetmodule: TBA-berekening (referentie € 92,08 uit de Excel) en de budget-API.

De jan-2025-cijfers hieronder zijn de échte waarden uit het tabblad
"Budget Planning Gemeenschappelijk" van het werkboek (PROJECT_SPEC §10).
"""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Context
from app.models.enums import CategoryType
from app.services.budget import compute_tba

# Categorie -> budget jan 2025 (Gemeenschappelijk), in centen
JAN_2025_GEM = {
    "Gemeenschappelijke bijdrage": 300000,
    "Maaltijdcheques": 15000,
    "Elektriciteit wagen": 1960,
    "Lening": 163152,
    "Energie en Water": 13000,
    "Internet": 4000,
    "Boodschappen": 50000,
    "Restaurant / Café": 10000,
    "Cadeaus": 1000,
    "Verzekeringen / Belastingen": 4600,
    "Huis & Wonen": 10000,
    "Ontspanning/Sport/Boeken": 2000,
    "Verzorging": 5000,
    "Andere": 5000,
    "Spaarrekening": 40000,
}


class TestComputeTba:
    def test_referentie_jan_2025(self) -> None:
        """Spec §10: 'To be allocated' jan 2025 (Gem.) = € 92,08 — exact."""
        tba = compute_tba(
            income=Decimal("3169.60"),
            expenses=Decimal("2677.52"),
            savings=Decimal("400.00"),
        )
        assert tba == Decimal("92.08")

    def test_mag_negatief_zijn(self) -> None:
        tba = compute_tba(Decimal("100"), Decimal("150.50"), Decimal("0"))
        assert tba == Decimal("-50.50")


def _gem_context_id(db: Session) -> int:
    return db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).one().id


def _put_jan_2025(client: TestClient, db: Session) -> int:
    """Zet de jan-2025-referentiebudgetten via de API; geeft het context-id terug."""
    context_id = _gem_context_id(db)
    categories = db.scalars(select(Category).where(Category.context_id == context_id)).all()
    by_name = {c.name: c for c in categories}
    items = [
        {"category_id": by_name[name].id, "year": 2025, "month": 1, "amount_cents": cents}
        for name, cents in JAN_2025_GEM.items()
    ]
    resp = client.put("/api/budgets", json={"items": items})
    assert resp.status_code == 204
    return context_id


class TestBudgetMatrix:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/budgets", params={"context_id": 1, "year": 2025}).status_code == 401
        assert client.put("/api/budgets", json={"items": []}).status_code == 401

    def test_tba_en_totalen_jan_2025(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _put_jan_2025(logged_in, seeded_db)
        resp = logged_in.get("/api/budgets", params={"context_id": context_id, "year": 2025})
        assert resp.status_code == 200
        matrix = resp.json()

        assert matrix["to_be_allocated_cents"][0] == 9208  # € 92,08
        totals = {g["type"]: g["monthly_total_cents"][0] for g in matrix["groups"]}
        assert totals == {"Inkomen": 316960, "Uitgaven": 267752, "Sparen": 40000}
        # lege maanden: TBA 0
        assert matrix["to_be_allocated_cents"][1:] == [0] * 11

    def test_rij_en_jaartotalen(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _put_jan_2025(logged_in, seeded_db)
        resp = logged_in.get("/api/budgets", params={"context_id": context_id, "year": 2025})
        groups = {g["type"]: g for g in resp.json()["groups"]}

        boodschappen = next(
            c for c in groups["Uitgaven"]["categories"] if c["name"] == "Boodschappen"
        )
        assert boodschappen["month_cents"] == [50000] + [0] * 11
        assert boodschappen["total_cents"] == 50000
        assert groups["Inkomen"]["total_cents"] == 316960

    def test_alle_categorieen_aanwezig_ook_zonder_budget(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        context_id = _gem_context_id(seeded_db)
        resp = logged_in.get("/api/budgets", params={"context_id": context_id, "year": 2030})
        matrix = resp.json()
        names = [c["name"] for g in matrix["groups"] for c in g["categories"]]
        assert len(names) == 21  # volledige seed-lijst, ook zonder budgetcellen
        assert matrix["to_be_allocated_cents"] == [0] * 12

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        resp = logged_in.get("/api/budgets", params={"context_id": 999, "year": 2025})
        assert resp.status_code == 404


class TestBudgetUpsert:
    def test_upsert_is_idempotent_en_overschrijft(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        context_id = _gem_context_id(seeded_db)
        category = seeded_db.scalars(
            select(Category).where(
                Category.context_id == context_id, Category.name == "Boodschappen"
            )
        ).one()
        cell = {"category_id": category.id, "year": 2025, "month": 3, "amount_cents": 45000}
        assert logged_in.put("/api/budgets", json={"items": [cell]}).status_code == 204
        cell["amount_cents"] = 47500
        assert logged_in.put("/api/budgets", json={"items": [cell]}).status_code == 204

        rows = seeded_db.scalars(
            select(Budget).where(Budget.category_id == category.id, Budget.year == 2025)
        ).all()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("475.00")

    def test_onbekende_categorie_404(self, logged_in: TestClient) -> None:
        cell = {"category_id": 9999, "year": 2025, "month": 1, "amount_cents": 100}
        assert logged_in.put("/api/budgets", json={"items": [cell]}).status_code == 404

    def test_ongeldige_maand_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        category = seeded_db.scalars(select(Category)).first()
        assert category is not None
        cell = {"category_id": category.id, "year": 2025, "month": 13, "amount_cents": 100}
        assert logged_in.put("/api/budgets", json={"items": [cell]}).status_code == 422


class TestContexts:
    def test_lijst(self, logged_in: TestClient) -> None:
        resp = logged_in.get("/api/contexts")
        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()] == ["Gemeenschappelijk", "Simon", "Jozefien"]

    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/contexts").status_code == 401


class TestCategoryTypeVolgorde:
    def test_groepen_in_vaste_volgorde(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _gem_context_id(seeded_db)
        resp = logged_in.get("/api/budgets", params={"context_id": context_id, "year": 2025})
        assert [g["type"] for g in resp.json()["groups"]] == [
            CategoryType.INKOMEN,
            CategoryType.UITGAVEN,
            CategoryType.SPAREN,
        ]


class TestBudgetNotes:
    """Excel-achtige celnotities: zetten, bijwerken, wissen; komen mee in de matrix."""

    def _first_category(self, db: Session) -> Category:
        context_id = _gem_context_id(db)
        return db.scalars(
            select(Category).where(Category.context_id == context_id).order_by(Category.id)
        ).first()

    def _matrix_note(self, client: TestClient, db: Session, category_id: int) -> str | None:
        context_id = _gem_context_id(db)
        resp = client.get("/api/budgets", params={"context_id": context_id, "year": 2025})
        assert resp.status_code == 200
        for group in resp.json()["groups"]:
            for row in group["categories"]:
                if row["category_id"] == category_id:
                    return row["month_notes"][0]  # januari
        raise AssertionError("categorie niet gevonden in matrix")

    def test_zetten_bijwerken_en_wissen(self, logged_in: TestClient, seeded_db: Session) -> None:
        cat = self._first_category(seeded_db)
        body = {"category_id": cat.id, "year": 2025, "month": 1, "note": "voorschot geannuleerd"}
        assert logged_in.put("/api/budgets/notes", json=body).status_code == 204
        assert self._matrix_note(logged_in, seeded_db, cat.id) == "voorschot geannuleerd"

        assert logged_in.put(
            "/api/budgets/notes", json={**body, "note": "  bijgewerkt  "}
        ).status_code == 204
        assert self._matrix_note(logged_in, seeded_db, cat.id) == "bijgewerkt"

        assert logged_in.put("/api/budgets/notes", json={**body, "note": "  "}).status_code == 204
        assert self._matrix_note(logged_in, seeded_db, cat.id) is None

    def test_notitie_zonder_budgetbedrag_kan(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        # Geen enkel budget gezet; notitie mag toch bestaan.
        cat = self._first_category(seeded_db)
        body = {"category_id": cat.id, "year": 2025, "month": 1, "note": "nog te plannen"}
        assert logged_in.put("/api/budgets/notes", json=body).status_code == 204
        assert self._matrix_note(logged_in, seeded_db, cat.id) == "nog te plannen"

    def test_onbekende_categorie_404(self, logged_in: TestClient) -> None:
        body = {"category_id": 99999, "year": 2025, "month": 1, "note": "x"}
        assert logged_in.put("/api/budgets/notes", json=body).status_code == 404

    def test_ongeldige_maand_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        cat = self._first_category(seeded_db)
        body = {"category_id": cat.id, "year": 2025, "month": 13, "note": "x"}
        assert logged_in.put("/api/budgets/notes", json=body).status_code == 422
