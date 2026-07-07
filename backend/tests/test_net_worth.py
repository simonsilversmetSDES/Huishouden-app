"""Vermogensbalans-rekenlogica (spec §9, tests-first).

Nettowaarde per maand = som van de activaklasse-waarden (mag negatief zijn, bv.
een aandelenpositie in verlies). Verandering t.o.v. de vorige maand (abs + %).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, NetWorthSnapshot
from app.models.enums import AssetClass
from app.services.net_worth import build_net_worth


def _context(db: Session, name: str = "Gemeenschappelijk") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _nw(db: Session, ctx: Context, d: date, asset: AssetClass, value: str) -> None:
    db.add(
        NetWorthSnapshot(
            context_id=ctx.id, snapshot_date=d, asset_class=asset, value=Decimal(value)
        )
    )


class TestBuildNetWorth:
    def _setup(self, db: Session) -> Context:
        ctx = _context(db)
        _nw(db, ctx, date(2025, 1, 1), AssetClass.CONTANT, "100.00")
        _nw(db, ctx, date(2025, 2, 1), AssetClass.CONTANT, "150.00")
        _nw(db, ctx, date(2025, 2, 1), AssetClass.AANDELEN, "-20.00")
        db.commit()
        return ctx

    def test_totalen_en_evolutie(self, seeded_db: Session) -> None:
        ctx = self._setup(seeded_db)
        out = build_net_worth(seeded_db, ctx)

        assert [r.snapshot_date for r in out.rows] == [date(2025, 1, 1), date(2025, 2, 1)]
        jan, feb = out.rows
        assert jan.total_cents == 10000
        assert jan.change_cents is None
        assert feb.total_cents == 13000  # 15000 + (−2000)
        assert feb.change_cents == 3000
        assert feb.change_pct == pytest.approx(30.0, abs=1e-6)

    def test_laatste_maand_en_donut(self, seeded_db: Session) -> None:
        ctx = self._setup(seeded_db)
        out = build_net_worth(seeded_db, ctx)
        assert out.latest_date == date(2025, 2, 1)
        assert out.latest_total_cents == 13000
        assert out.latest_change_cents == 3000
        breakdown = {a.asset_class: a.value_cents for a in out.latest_breakdown}
        assert breakdown == {AssetClass.CONTANT: 15000, AssetClass.AANDELEN: -2000}

    def test_lege_context(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Jozefien")
        out = build_net_worth(seeded_db, ctx)
        assert out.rows == []
        assert out.latest_date is None
        assert out.latest_total_cents == 0
        assert out.latest_breakdown == []


class TestNetWorthRoutes:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/net-worth", params={"context_id": 1}).status_code == 401

    def test_upsert_en_get(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        body = {
            "context_id": ctx.id,
            "snapshot_date": "2025-02-01",
            "asset_class": "contant",
            "value_cents": 500000,
        }
        assert logged_in.put("/api/net-worth", json=body).status_code in (200, 201)
        # bijwerken overschrijft dezelfde (context, datum, klasse)
        logged_in.put("/api/net-worth", json={**body, "value_cents": 400000})
        rows = seeded_db.scalars(select(NetWorthSnapshot)).all()
        assert len(rows) == 1
        assert rows[0].value == Decimal("4000.00")

        out = logged_in.get("/api/net-worth", params={"context_id": ctx.id}).json()
        assert out["latest_total_cents"] == 400000

    def test_delete(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        _nw(seeded_db, ctx, date(2025, 2, 1), AssetClass.WONING, "1000.00")
        seeded_db.commit()
        snap = seeded_db.scalars(select(NetWorthSnapshot)).one()
        assert logged_in.delete(f"/api/net-worth/{snap.id}").status_code == 204
        assert seeded_db.scalars(select(NetWorthSnapshot)).all() == []
