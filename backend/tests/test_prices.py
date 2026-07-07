"""Koers-endpoints (spec §7): manuele invoer + fetch-gate. Geen netwerk in tests."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Context, Security, SecurityPrice


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
