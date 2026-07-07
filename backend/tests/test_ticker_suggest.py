"""Ticker-suggestie uit de effectnaam + suggested_ticker in de API + zoek-gate."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Context, Security
from app.services.securities import suggest_ticker


class TestSuggestTicker:
    def test_beurscodes(self) -> None:
        assert suggest_ticker("ALPHABET INC. (XETR:ABEA)") == "ABEA.DE"
        assert suggest_ticker("iShs CoreMSCI Wld ETF USD A (XAMS:IWDA)") == "IWDA.AS"
        assert suggest_ticker("argenx SE (XBRU:ARGX)") == "ARGX.BR"

    def test_crypto(self) -> None:
        assert suggest_ticker("BTC/EUR") == "BTC-EUR"

    def test_onbekend(self) -> None:
        assert suggest_ticker("iemand (XXXX:FOO)") is None
        assert suggest_ticker("Gewoon een fonds zonder code") is None


def _simon(db: Session) -> int:
    return db.scalars(select(Context).where(Context.name == "Simon")).one().id


class TestSecurityOutSuggestion:
    def test_suggested_ticker_bij_lege_ticker(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _simon(seeded_db)
        seeded_db.add(Security(name="ALPHABET INC. (XETR:ABEA)", owner_context_id=ctx))
        seeded_db.commit()
        out = logged_in.get("/api/securities", params={"context_id": ctx}).json()
        row = next(s for s in out if s["name"].startswith("ALPHABET"))
        assert row["ticker"] is None
        assert row["suggested_ticker"] == "ABEA.DE"

    def test_geen_suggestie_als_ticker_gezet(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _simon(seeded_db)
        seeded_db.add(
            Security(name="ALPHABET INC. (XETR:ABEA)", ticker="ABEA.DE", owner_context_id=ctx)
        )
        seeded_db.commit()
        out = logged_in.get("/api/securities", params={"context_id": ctx}).json()
        row = next(s for s in out if s["name"].startswith("ALPHABET"))
        assert row["suggested_ticker"] is None


class TestSearchGate:
    def test_uitgeschakeld_503(self, logged_in: TestClient) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(
            _env_file=None,
            secret_key="test-secret",
            session_cookie_secure=False,
            price_fetch_enabled=False,
        )
        assert logged_in.get("/api/securities/search", params={"q": "alphabet"}).status_code == 503
