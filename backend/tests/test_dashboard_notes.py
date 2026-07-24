"""Maandnotities op het dashboard: zetten, bijwerken, wissen; komen mee in de
dashboard-response, onafhankelijk van de gekozen periode (maand/YTD/jaar)."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context


def _gem_context_id(db: Session) -> int:
    return db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).one().id


def _month_notes(client: TestClient, context_id: int, **params: int) -> dict[int, str]:
    """Haal de dashboard-response op en geef {maand: notitie}."""
    resp = client.get("/api/dashboard", params={"context_id": context_id, **params})
    assert resp.status_code == 200
    return {n["month"]: n["note"] for n in resp.json()["month_notes"]}


class TestMonthNotes:
    def test_zetten_bijwerken_en_wissen(
        self, logged_in: TestClient, seeded_db: Session
    ) -> None:
        ctx = _gem_context_id(seeded_db)
        body = {"context_id": ctx, "year": 2025, "month": 7, "note": "vakantiegeld ontvangen"}
        assert logged_in.put("/api/dashboard/notes", json=body).status_code == 204
        assert _month_notes(logged_in, ctx, year=2025) == {7: "vakantiegeld ontvangen"}

        # bijwerken + witruimte wordt getrimd
        assert (
            logged_in.put(
                "/api/dashboard/notes", json={**body, "note": "  bijgewerkt  "}
            ).status_code
            == 204
        )
        assert _month_notes(logged_in, ctx, year=2025) == {7: "bijgewerkt"}

        # lege/witruimte-notitie verwijdert
        assert logged_in.put("/api/dashboard/notes", json={**body, "note": "  "}).status_code == 204
        assert _month_notes(logged_in, ctx, year=2025) == {}

    def test_zichtbaar_in_elke_periode(self, logged_in: TestClient, seeded_db: Session) -> None:
        """Een notitie op juli hoort bij (context, jaar, maand) en verschijnt dus in
        maand-, YTD- én jaarmodus — de dashboard-response bevat altijd het hele jaar."""
        ctx = _gem_context_id(seeded_db)
        body = {"context_id": ctx, "year": 2025, "month": 7, "note": "let op grote uitgave"}
        assert logged_in.put("/api/dashboard/notes", json=body).status_code == 204

        assert _month_notes(logged_in, ctx, year=2025, month=7) == {7: "let op grote uitgave"}
        assert _month_notes(logged_in, ctx, year=2025, month_to=8) == {7: "let op grote uitgave"}
        assert _month_notes(logged_in, ctx, year=2025) == {7: "let op grote uitgave"}

    def test_gesorteerd_op_maand(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        for month in (11, 3, 7):
            body = {"context_id": ctx, "year": 2025, "month": month, "note": f"m{month}"}
            assert logged_in.put("/api/dashboard/notes", json=body).status_code == 204
        resp = logged_in.get("/api/dashboard", params={"context_id": ctx, "year": 2025})
        assert [n["month"] for n in resp.json()["month_notes"]] == [3, 7, 11]

    def test_ander_jaar_geen_notitie(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        body = {"context_id": ctx, "year": 2025, "month": 7, "note": "enkel 2025"}
        assert logged_in.put("/api/dashboard/notes", json=body).status_code == 204
        assert _month_notes(logged_in, ctx, year=2026) == {}

    def test_onbekende_context_404(self, logged_in: TestClient) -> None:
        body = {"context_id": 99999, "year": 2025, "month": 7, "note": "x"}
        assert logged_in.put("/api/dashboard/notes", json=body).status_code == 404

    def test_ongeldige_maand_422(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _gem_context_id(seeded_db)
        body = {"context_id": ctx, "year": 2025, "month": 13, "note": "x"}
        assert logged_in.put("/api/dashboard/notes", json=body).status_code == 422
