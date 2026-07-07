"""Beleggingen-endpoints (spec §7): effecten, transactielog (server-berekend
totaal) en portefeuille-overzicht."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, SecurityPrice, SecurityTransaction


def _context_id(db: Session, name: str = "Simon") -> int:
    return db.scalars(select(Context).where(Context.name == name)).one().id


class TestSecuritiesCrud:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/securities", params={"context_id": 1}).status_code == 401

    def test_aanmaken_en_lijsten(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        resp = logged_in.post(
            "/api/securities",
            json={"name": "iShares IWDA", "ticker": "IWDA", "owner_context_id": ctx},
        )
        assert resp.status_code == 201
        sec_id = resp.json()["id"]
        listed = logged_in.get("/api/securities", params={"context_id": ctx}).json()
        assert [s["id"] for s in listed] == [sec_id]

    def test_verwijderen_ruimt_transacties_op(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _context_id(seeded_db)
        sec_id = logged_in.post(
            "/api/securities", json={"name": "X", "owner_context_id": ctx}
        ).json()["id"]
        logged_in.post(
            "/api/security-transactions",
            json={
                "security_id": sec_id,
                "date": "2025-01-01",
                "side": "buy",
                "shares": "1",
                "price_per_share": "100",
            },
        )
        assert logged_in.delete(f"/api/securities/{sec_id}").status_code == 204
        assert seeded_db.scalars(select(SecurityTransaction)).all() == []


class TestTransactionTotal:
    def _security(self, logged_in: TestClient, seeded_db: Session) -> int:
        ctx = _context_id(seeded_db)
        return logged_in.post(
            "/api/securities", json={"name": "IWDA", "owner_context_id": ctx}
        ).json()["id"]

    def test_aankoop_totaal_incl_kosten_en_taks(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        sec_id = self._security(logged_in, seeded_db)
        resp = logged_in.post(
            "/api/security-transactions",
            json={
                "security_id": sec_id,
                "date": "2025-01-31",
                "side": "buy",
                "shares": "2",
                "price_per_share": "107.935",
                "fee": "1",
                "tax": "0.259044",
            },
        )
        assert resp.status_code == 201
        # 2×107,935 + 1 + 0,259044 = 217,129044
        assert resp.json()["total"] == "217.129044"

    def test_verkoop_totaal_is_netto(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec_id = self._security(logged_in, seeded_db)
        resp = logged_in.post(
            "/api/security-transactions",
            json={
                "security_id": sec_id,
                "date": "2025-06-01",
                "side": "sell",
                "shares": "2",
                "price_per_share": "120",
                "fee": "1",
                "tax": "0.5",
            },
        )
        # 2×120 − 1 − 0,5 = 238,5
        assert resp.json()["total"] == "238.5"

    def test_ongeldig_aantal_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec_id = self._security(logged_in, seeded_db)
        resp = logged_in.post(
            "/api/security-transactions",
            json={
                "security_id": sec_id,
                "date": "2025-01-01",
                "side": "buy",
                "shares": "0",
                "price_per_share": "100",
            },
        )
        assert resp.status_code == 422


class TestPortfolioEndpoint:
    def test_portefeuille_overzicht(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        sec_id = logged_in.post(
            "/api/securities", json={"name": "IWDA", "owner_context_id": ctx}
        ).json()["id"]
        logged_in.post(
            "/api/security-transactions",
            json={
                "security_id": sec_id,
                "date": "2025-01-01",
                "side": "buy",
                "shares": "10",
                "price_per_share": "100",
            },
        )
        seeded_db.add(
            SecurityPrice(security_id=sec_id, date=date(2026, 1, 1), price=Decimal("110"))
        )
        seeded_db.commit()

        out = logged_in.get("/api/portfolio", params={"context_id": ctx}).json()
        assert out["total_cost_cents"] == 100000
        assert out["total_value_cents"] == 110000
        assert out["total_gain_cents"] == 10000
        assert out["positions"][0]["gain_pct"] == 10.0
