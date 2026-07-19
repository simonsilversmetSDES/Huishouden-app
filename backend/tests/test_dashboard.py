"""Dashboard-API: budget vs. werkelijk per maand, TBA en uitsluitingsregels."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Context, Transaction
from app.models.enums import CategoryType


def _gem(db: Session) -> Context:
    return db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).one()


def _category(db: Session, context_id: int, name: str) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context_id, Category.name == name)
    ).one()


def _setup_maand(client: TestClient, db: Session) -> int:
    """Budget + transacties voor juli 2025 (Gem.): boodschappen en bijdrage."""
    ctx = _gem(db)
    boodschappen = _category(db, ctx.id, "Boodschappen")
    bijdrage = _category(db, ctx.id, "Gemeenschappelijke bijdrage")
    items = [
        {"category_id": boodschappen.id, "year": 2025, "month": 7, "amount_cents": 50000},
        {"category_id": bijdrage.id, "year": 2025, "month": 7, "amount_cents": 300000},
    ]
    assert client.put("/api/budgets", json={"items": items}).status_code == 204

    db.add_all(
        [
            # uitgaven: negatief bedrag (app-conventie: + = inkomen, − = uitgave)
            Transaction(
                context_id=ctx.id,
                category_id=boodschappen.id,
                date=date(2025, 7, 3),
                amount="-123.45",
                type=CategoryType.UITGAVEN,
            ),
            Transaction(
                context_id=ctx.id,
                category_id=boodschappen.id,
                date=date(2025, 7, 10),
                amount="-76.55",
                type=CategoryType.UITGAVEN,
            ),
            # inkomen
            Transaction(
                context_id=ctx.id,
                category_id=bijdrage.id,
                date=date(2025, 7, 1),
                amount="3000.00",
                type=CategoryType.INKOMEN,
            ),
            # eind juni betaald maar budgetmaand juli (Excel "Effective Date"): telt mee
            Transaction(
                context_id=ctx.id,
                category_id=bijdrage.id,
                date=date(2025, 6, 28),
                effective_date=date(2025, 7, 1),
                amount="50.00",
                type=CategoryType.INKOMEN,
            ),
            # andere maand (effective_date volgt date): telt niet mee
            Transaction(
                context_id=ctx.id,
                category_id=boodschappen.id,
                date=date(2025, 6, 30),
                amount="-999.00",
                type=CategoryType.UITGAVEN,
            ),
            # interne overschrijving: uitgesloten van budget vs. werkelijk
            Transaction(
                context_id=ctx.id,
                category_id=boodschappen.id,
                date=date(2025, 7, 5),
                amount="-500.00",
                type=CategoryType.UITGAVEN,
                is_internal_transfer=True,
            ),
            # ongecategoriseerd: telt mee in de teller, niet in een categorierij
            Transaction(
                context_id=ctx.id,
                category_id=None,
                date=date(2025, 7, 8),
                amount="-10.00",
                type=CategoryType.UITGAVEN,
            ),
        ]
    )
    db.commit()
    return ctx.id


class TestDashboard:
    def test_vereist_login(self, client: TestClient) -> None:
        params = {"context_id": 1, "year": 2025, "month": 7}
        assert client.get("/api/dashboard", params=params).status_code == 401

    def test_budget_vs_werkelijk(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _setup_maand(logged_in, seeded_db)
        resp = logged_in.get(
            "/api/dashboard", params={"context_id": context_id, "year": 2025, "month": 7}
        )
        assert resp.status_code == 200
        data = resp.json()

        rows = {r["name"]: r for r in data["categories"]}
        # werkelijk als positieve grootte binnen het type; interne overschrijving telt niet
        assert rows["Boodschappen"]["budget_cents"] == 50000
        assert rows["Boodschappen"]["actual_cents"] == 20000  # 123,45 + 76,55
        assert rows["Gemeenschappelijke bijdrage"]["actual_cents"] == 305000  # incl. eind juni

        totals = {t["type"]: t for t in data["type_totals"]}
        assert totals["Inkomen"]["actual_cents"] == 305000
        assert totals["Uitgaven"]["actual_cents"] == 21000  # incl. ongecategoriseerde € 10
        assert totals["Uitgaven"]["budget_cents"] == 50000

        # TBA van de maand: 3000 − 500 = 2500 gebudgetteerd
        assert data["to_be_allocated_cents"] == 250000
        assert data["uncategorized_count"] == 1

    def test_lege_maand_geeft_nullen(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem(seeded_db)
        resp = logged_in.get(
            "/api/dashboard", params={"context_id": ctx.id, "year": 2031, "month": 2}
        )
        data = resp.json()
        assert data["to_be_allocated_cents"] == 0
        assert all(t["actual_cents"] == 0 for t in data["type_totals"])
        assert data["uncategorized_count"] == 0

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        resp = logged_in.get("/api/dashboard", params={"context_id": 999, "year": 2025, "month": 7})
        assert resp.status_code == 404

    def test_budget_op_inactieve_categorie_genegeerd(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Een budget op een gedeactiveerde categorie mag het dashboard niet laten crashen
        en telt niet mee — zoals de budgetmatrix zulke rijen stil overslaat."""
        context_id = _setup_maand(logged_in, seeded_db)
        boodschappen = _category(seeded_db, context_id, "Boodschappen")
        boodschappen.active = False
        seeded_db.commit()

        resp = logged_in.get(
            "/api/dashboard", params={"context_id": context_id, "year": 2025, "month": 7}
        )
        assert resp.status_code == 200
        data = resp.json()
        # De inactieve categorie verschijnt niet meer in de rijen...
        assert "Boodschappen" not in {r["name"] for r in data["categories"]}
        # ...en haar budget telt niet mee in het Uitgaven-totaal.
        totals = {t["type"]: t for t in data["type_totals"]}
        assert totals["Uitgaven"]["budget_cents"] == 0


class TestJaarWeergave:
    """month weglaten = heel jaar; juni- én juli-transacties tellen dan samen."""

    def test_jaar_telt_alle_maanden(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _setup_maand(logged_in, seeded_db)
        resp = logged_in.get("/api/dashboard", params={"context_id": context_id, "year": 2025})
        assert resp.status_code == 200
        data = resp.json()

        assert data["month"] is None
        totals = {t["type"]: t for t in data["type_totals"]}
        # uitgaven: juli 200 + ongecat. 10 + juni 999 (effective juni telt nu ook mee)
        assert totals["Uitgaven"]["actual_cents"] == 120900
        assert totals["Inkomen"]["actual_cents"] == 305000
        # budget: enkel juli ingevuld → jaartotaal = juli-budget
        assert totals["Uitgaven"]["budget_cents"] == 50000
        assert data["to_be_allocated_cents"] == 250000  # som van 12 maandelijkse TBA's

        rows = {r["name"]: r for r in data["categories"]}
        assert rows["Boodschappen"]["actual_cents"] == 119900  # 200 + 999

    def test_months_voor_staafgrafiek(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _setup_maand(logged_in, seeded_db)
        for params in ({"month": 7}, {}):
            resp = logged_in.get(
                "/api/dashboard", params={"context_id": context_id, "year": 2025, **params}
            )
            months = resp.json()["months"]
            assert [m["month"] for m in months] == list(range(1, 13))

            juli = {t["type"]: t for t in months[6]["totals"]}
            assert juli["Uitgaven"]["actual_cents"] == 21000
            assert juli["Uitgaven"]["budget_cents"] == 50000
            assert juli["Inkomen"]["actual_cents"] == 305000

            juni = {t["type"]: t for t in months[5]["totals"]}
            assert juni["Uitgaven"]["actual_cents"] == 99900
            assert juni["Uitgaven"]["budget_cents"] == 0

    def test_ytd_telt_enkel_maanden_tot_grens(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """YTD (month_to): enkel maanden 1..month_to tellen, budget én werkelijk.
        Met month_to=6 valt juli weg; enkel de juni-uitgave (999) blijft over en het
        juli-budget telt niet mee — zo blijft budget vs. werkelijk vergelijkbaar."""
        context_id = _setup_maand(logged_in, seeded_db)
        resp = logged_in.get(
            "/api/dashboard",
            params={"context_id": context_id, "year": 2025, "month_to": 6},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["month"] is None
        assert data["month_to"] == 6
        totals = {t["type"]: t for t in data["type_totals"]}
        assert totals["Uitgaven"]["actual_cents"] == 99900  # enkel juni 999
        assert totals["Uitgaven"]["budget_cents"] == 0  # juli-budget valt buiten YTD
        assert totals["Inkomen"]["actual_cents"] == 0  # juli-inkomen valt buiten YTD
        assert data["to_be_allocated_cents"] == 0
        assert data["uncategorized_count"] == 0  # de ongecat. € 10 is een juli-transactie
        assert [m["month"] for m in data["months"]] == list(range(1, 13))

    def test_ytd_tot_juli_gelijk_aan_jaar(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Alle testdata ligt t/m juli, dus month_to=7 geeft dezelfde totalen als heel jaar."""
        context_id = _setup_maand(logged_in, seeded_db)
        resp = logged_in.get(
            "/api/dashboard",
            params={"context_id": context_id, "year": 2025, "month_to": 7},
        )
        data = resp.json()
        totals = {t["type"]: t for t in data["type_totals"]}
        assert totals["Uitgaven"]["actual_cents"] == 120900  # juli 210 + juni 999
        assert totals["Inkomen"]["actual_cents"] == 305000
        assert data["to_be_allocated_cents"] == 250000

    def test_maandweergave_categorien_ongewijzigd(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        context_id = _setup_maand(logged_in, seeded_db)
        resp = logged_in.get(
            "/api/dashboard", params={"context_id": context_id, "year": 2025, "month": 7}
        )
        data = resp.json()
        assert data["month"] == 7
        rows = {r["name"]: r for r in data["categories"]}
        assert rows["Boodschappen"]["actual_cents"] == 20000  # juni telt hier niet mee
