"""Koers-endpoints (spec §7): manuele invoer + fetch-gate. Geen netwerk in tests."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Context, Security, SecurityPrice
from app.services.prices import _nearest_rate, to_eur


class TestToEur:
    def test_eur_ongewijzigd(self) -> None:
        assert to_eur(Decimal("100"), "EUR", None) == Decimal("100")
        assert to_eur(Decimal("100"), None, None) == Decimal("100")

    def test_usd_omgerekend(self) -> None:
        # 100 USD × 0,92 EUR/USD = 92 EUR
        assert to_eur(Decimal("100"), "USD", Decimal("0.92")) == Decimal("92.000000")

    def test_zonder_koers_fout(self) -> None:
        with pytest.raises(ValueError, match="wisselkoers"):
            to_eur(Decimal("100"), "USD", None)


class TestNearestRate:
    """Wisselkoers-keuze bij de historische backfill: val terug op de vorige
    beursdag als een datum (weekend/feestdag) geen notering heeft."""

    fx = {
        date(2024, 12, 30): Decimal("0.90"),
        date(2024, 12, 31): Decimal("0.91"),
        date(2025, 1, 2): Decimal("0.93"),
    }

    def test_exacte_dag(self) -> None:
        assert _nearest_rate(self.fx, date(2024, 12, 31)) == Decimal("0.91")

    def test_valt_terug_op_vorige_beursdag(self) -> None:
        assert _nearest_rate(self.fx, date(2025, 1, 1)) == Decimal("0.91")

    def test_geen_koers_voor_datum(self) -> None:
        assert _nearest_rate(self.fx, date(2024, 12, 29)) is None

    def test_lege_historiek(self) -> None:
        assert _nearest_rate({}, date(2025, 1, 1)) is None


def _security(db: Session, name: str = "IWDA", ticker: str | None = "IWDA") -> Security:
    ctx = db.scalars(select(Context).where(Context.name == "Simon")).one()
    sec = Security(name=name, ticker=ticker, owner_context_id=ctx.id)
    db.add(sec)
    db.commit()
    return sec


class TestManualPrice:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.put("/api/security-prices", json={}).status_code in (401, 422)

    def test_upsert_koers(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec = _security(seeded_db)
        body = {"security_id": sec.id, "date": "2026-07-01", "price": "153.96"}
        resp = logged_in.put("/api/security-prices", json=body)
        assert resp.status_code == 200
        assert resp.json()["price"] == "153.96"
        assert resp.json()["source"] == "manual"
        # bijwerken van dezelfde (effect, datum) overschrijft
        logged_in.put("/api/security-prices", json={**body, "price": "160"})
        rows = seeded_db.scalars(select(SecurityPrice)).all()
        assert len(rows) == 1
        assert str(rows[0].price) == "160"

    def test_ongeldige_koers_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec = _security(seeded_db)
        resp = logged_in.put(
            "/api/security-prices",
            json={"security_id": sec.id, "date": "2026-07-01", "price": "-5"},
        )
        assert resp.status_code == 422


class TestFetchGate:
    def test_uitgeschakeld_503(self, logged_in: TestClient, seeded_db: Session) -> None:
        # zelfde secret_key/secure als de conftest zodat de sessie geldig blijft,
        # enkel de fetch-schakelaar uit.
        app.dependency_overrides[get_settings] = lambda: Settings(
            _env_file=None,
            secret_key="test-secret",
            session_cookie_secure=False,
            price_fetch_enabled=False,
        )
        ctx = seeded_db.scalars(select(Context).where(Context.name == "Simon")).one()
        resp = logged_in.post("/api/prices/fetch", params={"context_id": ctx.id})
        assert resp.status_code == 503
