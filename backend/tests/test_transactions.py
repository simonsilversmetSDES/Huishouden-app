"""Transactie-API: manuele invoer (spec §5.1) met de app-tekenconventie en lijst met filters.

Tekenconventie (zelfde als de Excel-import): de API neemt amount_cents als
positieve magnitude + type; opgeslagen wordt signed (+ = inkomen, − = uitgave/
sparen). Responses geven amount_cents signed terug.

Het 23/12/2025-geval: de rij uit "Tracking S." zonder bedrag werd bij de import
overgeslagen; handmatig toevoegen zonder bedrag moet 422 geven, mét bedrag 201.
"""

from decimal import Decimal
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Context, Transaction
from app.models.enums import Categorization, TransactionSource


def _context_id(db: Session, name: str = "Gemeenschappelijk") -> int:
    return db.scalars(select(Context).where(Context.name == name)).one().id


def _category(db: Session, context_id: int, name: str) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context_id, Category.name == name)
    ).one()


def _post_tx(client: TestClient, db: Session, **overrides: Any) -> httpx.Response:
    """POST met een geldige basispayload (uitgave 'Boodschappen'); overrides passen aan."""
    context_id = overrides.pop("context_id", None) or _context_id(db)
    payload: dict[str, Any] = {
        "context_id": context_id,
        "date": "2026-07-03",
        "type": "Uitgaven",
        "amount_cents": 12345,
        "description": "Colruyt",
    }
    payload.update(overrides)
    if "category_id" not in payload:
        payload["category_id"] = _category(db, context_id, "Boodschappen").id
    for key in [k for k, v in payload.items() if v is ...]:
        del payload[key]  # ... = veld weglaten uit de payload
    return client.post("/api/transactions", json=payload)


def _db_amount(db: Session, tx_id: int) -> Decimal:
    tx = db.get(Transaction, tx_id)
    assert tx is not None
    db.refresh(tx)
    return tx.amount


class TestTransactionCreate:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.post("/api/transactions", json={}).status_code == 401

    def test_uitgave_wordt_negatief_opgeslagen(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Magnitude 12345 + Uitgaven → DB −123,45; response signed."""
        resp = _post_tx(logged_in, seeded_db)
        assert resp.status_code == 201
        body = resp.json()
        assert body["amount_cents"] == -12345
        assert _db_amount(seeded_db, body["id"]) == Decimal("-123.45")

    def test_inkomen_blijft_positief(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = _context_id(seeded_db)
        resp = _post_tx(
            logged_in,
            seeded_db,
            type="Inkomen",
            amount_cents=300000,
            category_id=_category(seeded_db, context_id, "Gemeenschappelijke bijdrage").id,
        )
        assert resp.status_code == 201
        assert resp.json()["amount_cents"] == 300000
        assert _db_amount(seeded_db, resp.json()["id"]) == Decimal("3000.00")

    def test_sparen_wordt_negatief_opgeslagen(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        context_id = _context_id(seeded_db)
        resp = _post_tx(
            logged_in,
            seeded_db,
            type="Sparen",
            amount_cents=40000,
            category_id=_category(seeded_db, context_id, "Spaarrekening").id,
        )
        assert resp.status_code == 201
        assert resp.json()["amount_cents"] == -40000

    def test_negatieve_magnitude_flipt_mee(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Terugbetaling: negatieve invoer op Uitgaven wordt positief opgeslagen."""
        resp = _post_tx(logged_in, seeded_db, amount_cents=-500, description="Terugbetaling")
        assert resp.status_code == 201
        assert resp.json()["amount_cents"] == 500
        assert _db_amount(seeded_db, resp.json()["id"]) == Decimal("5.00")

    def test_tracking_s_rij_zonder_bedrag_422(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """De rij uit Tracking S. van 23/12/2025 zonder bedrag: bij de import
        overgeslagen (rij 292); manueel zonder bedrag hoort 422 te geven."""
        context_id = _context_id(seeded_db, "Simon")
        resp = _post_tx(
            logged_in,
            seeded_db,
            context_id=context_id,
            date="2025-12-23",
            amount_cents=...,  # veld weglaten, zoals de lege Excel-cel
            category_id=None,
            description="Uitgaven2",
        )
        assert resp.status_code == 422

    def test_tracking_s_rij_met_bedrag_kan_wel(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Dezelfde rij mét bedrag moet wél handmatig toe te voegen zijn."""
        context_id = _context_id(seeded_db, "Simon")
        resp = _post_tx(
            logged_in,
            seeded_db,
            context_id=context_id,
            date="2025-12-23",
            amount_cents=2500,
            category_id=None,
            description="Uitgaven2",
        )
        assert resp.status_code == 201
        assert resp.json()["amount_cents"] == -2500

    def test_bedrag_nul_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        assert _post_tx(logged_in, seeded_db, amount_cents=0).status_code == 422

    def test_float_centen_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        assert _post_tx(logged_in, seeded_db, amount_cents=123.45).status_code == 422

    def test_effective_date_default_gelijk_aan_date(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        resp = _post_tx(logged_in, seeded_db, date="2026-07-03")
        assert resp.json()["effective_date"] == "2026-07-03"

    def test_effective_date_expliciet(self, logged_in: TestClient, seeded_db: Session) -> None:
        """Budgetmaand-datum los van de transactiedatum (Excel 'Effective Date')."""
        resp = _post_tx(
            logged_in, seeded_db, date="2025-12-23", effective_date="2026-01-01"
        )
        body = resp.json()
        assert body["date"] == "2025-12-23"
        assert body["effective_date"] == "2026-01-01"

    def test_source_manual_en_categorization(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        met_categorie = _post_tx(logged_in, seeded_db).json()
        assert met_categorie["source"] == TransactionSource.MANUAL
        tx = seeded_db.get(Transaction, met_categorie["id"])
        assert tx is not None
        seeded_db.refresh(tx)
        assert tx.categorization == Categorization.MANUAL
        assert tx.import_hash is None

        zonder_categorie = _post_tx(logged_in, seeded_db, category_id=None).json()
        tx2 = seeded_db.get(Transaction, zonder_categorie["id"])
        assert tx2 is not None
        seeded_db.refresh(tx2)
        assert tx2.categorization == Categorization.UNCATEGORIZED

    def test_categorie_verkeerd_type_422(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """Een Inkomen-categorie hoort niet bij een Uitgaven-transactie."""
        context_id = _context_id(seeded_db)
        inkomen_categorie = _category(seeded_db, context_id, "Gemeenschappelijke bijdrage")
        resp = _post_tx(logged_in, seeded_db, type="Uitgaven", category_id=inkomen_categorie.id)
        assert resp.status_code == 422

    def test_categorie_andere_context_404(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        simon_id = _context_id(seeded_db, "Simon")
        simon_categorie = seeded_db.scalars(
            select(Category).where(Category.context_id == simon_id)
        ).first()
        assert simon_categorie is not None
        resp = _post_tx(
            logged_in,
            seeded_db,
            type=simon_categorie.type,
            category_id=simon_categorie.id,  # context in payload blijft Gemeenschappelijk
        )
        assert resp.status_code == 404

    def test_onbekende_categorie_404(self, logged_in: TestClient, seeded_db: Session) -> None:
        assert _post_tx(logged_in, seeded_db, category_id=99999).status_code == 404

    def test_onbekende_context_404(self, logged_in: TestClient, seeded_db: Session) -> None:
        resp = _post_tx(logged_in, seeded_db, context_id=999, category_id=None)
        assert resp.status_code == 404


class TestTransactionList:
    def _seed_lijst(self, client: TestClient, db: Session) -> int:
        """Vier transacties over twee budgetmaanden heen; geeft het context-id terug."""
        context_id = _context_id(db)
        boodschappen = _category(db, context_id, "Boodschappen").id
        bijdrage = _category(db, context_id, "Gemeenschappelijke bijdrage").id
        for overrides in [
            # het 23/12-patroon: december-datum, januari-budgetmaand
            {"date": "2025-12-23", "effective_date": "2026-01-01", "amount_cents": 2500,
             "category_id": boodschappen, "description": "eind december, telt voor januari"},
            {"date": "2026-01-05", "amount_cents": 5000, "category_id": boodschappen},
            {"date": "2026-01-06", "type": "Inkomen", "amount_cents": 300000,
             "category_id": bijdrage},
            {"date": "2026-02-01", "amount_cents": 1000, "category_id": None},
        ]:
            assert _post_tx(client, db, **overrides).status_code == 201
        return context_id

    def _get(self, client: TestClient, **params: Any) -> httpx.Response:
        return client.get("/api/transactions", params=params)

    def test_vereist_login(self, client: TestClient) -> None:
        resp = client.get("/api/transactions", params={"context_id": 1, "year": 2026})
        assert resp.status_code == 401

    def test_maandfilter_volgt_effective_date(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """23/12/2025 met budgetmaand jan 2026 zit in 2026/1, niet in 2025/12."""
        context_id = self._seed_lijst(logged_in, seeded_db)
        jan = self._get(logged_in, context_id=context_id, year=2026, month=1).json()
        assert len(jan) == 3
        assert "2025-12-23" in [tx["date"] for tx in jan]
        dec = self._get(logged_in, context_id=context_id, year=2025, month=12).json()
        assert dec == []

    def test_jaarfilter_zonder_maand(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = self._seed_lijst(logged_in, seeded_db)
        assert len(self._get(logged_in, context_id=context_id, year=2026).json()) == 4
        assert self._get(logged_in, context_id=context_id, year=2025).json() == []

    def test_filter_op_type(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = self._seed_lijst(logged_in, seeded_db)
        rows = self._get(
            logged_in, context_id=context_id, year=2026, type="Inkomen"
        ).json()
        assert [tx["type"] for tx in rows] == ["Inkomen"]

    def test_filter_op_categorie(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = self._seed_lijst(logged_in, seeded_db)
        boodschappen = _category(seeded_db, context_id, "Boodschappen").id
        rows = self._get(
            logged_in, context_id=context_id, year=2026, category_id=boodschappen
        ).json()
        assert len(rows) == 2
        assert all(tx["category_id"] == boodschappen for tx in rows)

    def test_sortering_nieuwste_eerst(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = self._seed_lijst(logged_in, seeded_db)
        rows = self._get(logged_in, context_id=context_id, year=2026).json()
        effective_dates = [tx["effective_date"] for tx in rows]
        assert effective_dates == sorted(effective_dates, reverse=True)

    def test_category_name_in_response(self, logged_in: TestClient, seeded_db: Session) -> None:
        context_id = self._seed_lijst(logged_in, seeded_db)
        rows = self._get(logged_in, context_id=context_id, year=2026).json()
        by_desc = {tx["description"]: tx for tx in rows}
        assert by_desc["eind december, telt voor januari"]["category_name"] == "Boodschappen"
        ongecategoriseerd = next(tx for tx in rows if tx["category_id"] is None)
        assert ongecategoriseerd["category_name"] is None

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        assert self._get(logged_in, context_id=999, year=2026).status_code == 404


class TestTransactionDashboardIntegratie:
    def test_manuele_uitgave_telt_positief_op_dashboard(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        """De tekenconventie strookt met _actual_magnitude: een uitgave van
        € 123,45 verschijnt als +12345 actual_cents bij de categorie."""
        context_id = _context_id(seeded_db)
        boodschappen = _category(seeded_db, context_id, "Boodschappen").id
        assert _post_tx(logged_in, seeded_db, date="2026-07-03").status_code == 201

        resp = logged_in.get(
            "/api/dashboard", params={"context_id": context_id, "year": 2026, "month": 7}
        )
        assert resp.status_code == 200
        per_categorie = {c["category_id"]: c for c in resp.json()["categories"]}
        assert per_categorie[boodschappen]["actual_cents"] == 12345
