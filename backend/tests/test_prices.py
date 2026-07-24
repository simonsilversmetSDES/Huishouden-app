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
from app.services.prices import (
    ChartHistory,
    ChartPoint,
    _fetch_history_one,
    _nearest_rate,
    to_eur,
)


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


class TestFetchHistoryOne:
    """Historiek-parsing zonder netwerk: yfinance geeft voor de lopende beursdag
    soms een rij met NaN als slotkoers — die mag de hele ticker niet doen falen
    (Decimal('nan') > 0 gooit InvalidOperation)."""

    class _FakeTicker:
        def __init__(self, hist) -> None:  # type: ignore[no-untyped-def]
            self._hist = hist
            self.fast_info = {"currency": "EUR"}

        def history(self, **_kwargs):  # type: ignore[no-untyped-def]
            return self._hist

    class _FakeYfinance:
        def __init__(self, hist) -> None:  # type: ignore[no-untyped-def]
            self._hist = hist

        def Ticker(self, _symbol: str):  # type: ignore[no-untyped-def]  # noqa: N802
            return TestFetchHistoryOne._FakeTicker(self._hist)

    def test_nan_slotkoers_overgeslagen(self) -> None:
        import pandas as pd

        hist = pd.DataFrame(
            {"Close": [10.5, float("nan"), 11.0]},
            index=pd.to_datetime(["2026-07-07", "2026-07-08", "2026-07-09"]),
        )
        closes, currency = _fetch_history_one(
            self._FakeYfinance(hist), "SPYI.DE", date(2026, 7, 7), date(2026, 7, 9)
        )
        assert currency == "EUR"
        assert closes == {
            date(2026, 7, 7): Decimal("10.5"),
            date(2026, 7, 9): Decimal("11.0"),
        }


def _security(db: Session, name: str = "IWDA", ticker: str | None = "IWDA") -> Security:
    ctx = db.scalars(select(Context).where(Context.name == "Simon")).one()
    sec = Security(name=name, ticker=ticker, owner_context_id=ctx.id)
    db.add(sec)
    db.commit()
    return sec


class TestFetchDayChange:
    """fetch_prices berekent de dagbeweging uit last vs previousClose in de
    noteringsmunt — dus zónder wisselkoerseffect, zoals Bolero/Degiro."""

    class _FakeTicker:
        def __init__(self, fast_info: dict) -> None:
            self.fast_info = fast_info

        def history(self, **_kwargs):  # type: ignore[no-untyped-def]
            import pandas as pd

            return pd.DataFrame({"Close": []})

    class _FakeYfinance:
        """USD-effect (+10 % in USD) plus een USDEUR=X-koers van 0,90."""

        def Ticker(self, symbol: str):  # type: ignore[no-untyped-def]  # noqa: N802
            if symbol == "USDEUR=X":
                return TestFetchDayChange._FakeTicker({"last_price": 0.90})
            return TestFetchDayChange._FakeTicker(
                {"currency": "USD", "last_price": 110, "previousClose": 100}
            )

    def test_dagbeweging_zonder_wisselkoerseffect(
        self, seeded_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        from app.services.prices import fetch_prices

        sec = _security(seeded_db, ticker="IWDA")
        monkeypatch.setitem(sys.modules, "yfinance", self._FakeYfinance())
        result = fetch_prices(seeded_db, [sec], date(2026, 7, 24))
        seeded_db.commit()

        assert result.fetched == 1
        # +10 % in USD, ongeacht de EUR/USD-koers
        assert sec.day_change_pct == Decimal("10")
        # opgeslagen koers blijft in euro: 110 USD × 0,90 = 99 EUR
        row = seeded_db.scalars(
            select(SecurityPrice).where(SecurityPrice.security_id == sec.id)
        ).one()
        assert row.price == Decimal("99.000000")


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


class TestChartHistory:
    """Grafiek-endpoint (Yahoo-tijdsblokken); de echte fetch wordt gemockt."""

    def test_zonder_ticker_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec = _security(seeded_db, name="Fonds zonder ticker", ticker=None)
        resp = logged_in.get(f"/api/securities/{sec.id}/history", params={"range": "1d"})
        assert resp.status_code == 422

    def test_onbekende_periode_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        sec = _security(seeded_db)
        resp = logged_in.get(f"/api/securities/{sec.id}/history", params={"range": "2w"})
        assert resp.status_code == 422

    def test_geeft_reeks_terug(
        self, logged_in: TestClient, seeded_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import datetime

        from app.routes import securities as routes

        sec = _security(seeded_db)
        fake = ChartHistory(
            currency="EUR",
            prev_close=Decimal("100.5"),
            points=[
                ChartPoint(t=datetime(2026, 7, 10, 9, 0), price=Decimal("100.5")),
                ChartPoint(t=datetime(2026, 7, 10, 9, 5), price=Decimal("101.25")),
            ],
        )
        monkeypatch.setattr(routes, "fetch_chart_history", lambda *_args: fake)
        resp = logged_in.get(f"/api/securities/{sec.id}/history", params={"range": "1d"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["range"] == "1d"
        assert body["currency"] == "EUR"
        assert body["prev_close"] == "100.5"
        assert [p["price"] for p in body["points"]] == ["100.5", "101.25"]


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
