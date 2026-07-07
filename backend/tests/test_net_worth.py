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

from app.models import Account, AccountSnapshot, Context, NetWorthSnapshot
from app.models.enums import AccountType, AssetClass, Bank
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


class TestContantAuto:
    def _account(self, db: Session, ctx: Context, name: str, type_: AccountType) -> Account:
        acc = Account(context_id=ctx.id, name=name, bank=Bank.KBC, type=type_)
        db.add(acc)
        db.flush()
        return acc

    def test_contant_uit_rekeningstanden(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Simon")
        zicht = self._account(seeded_db, ctx, "Zicht", AccountType.ZICHT)
        spaar = self._account(seeded_db, ctx, "Spaar", AccountType.SPAAR)
        jun = date(2026, 6, 1)
        seeded_db.add_all(
            [
                AccountSnapshot(account_id=zicht.id, snapshot_date=jun, balance=Decimal("1000.00")),
                AccountSnapshot(account_id=spaar.id, snapshot_date=jun, balance=Decimal("2000.00")),
            ]
        )
        # manuele contant (moet overschreven worden) + woning (blijft)
        _nw(seeded_db, ctx, date(2026, 6, 1), AssetClass.CONTANT, "500.00")
        _nw(seeded_db, ctx, date(2026, 6, 1), AssetClass.WONING, "100.00")
        seeded_db.commit()

        out = build_net_worth(seeded_db, ctx)
        breakdown = {a.asset_class: a.value_cents for a in out.latest_breakdown}
        assert breakdown[AssetClass.CONTANT] == 300000  # 1000 + 2000, niet 500
        assert breakdown[AssetClass.WONING] == 10000
        assert out.latest_total_cents == 310000

    def test_manueel_contant_zonder_rekeningdata(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Jozefien")
        _nw(seeded_db, ctx, date(2026, 5, 1), AssetClass.CONTANT, "500.00")
        seeded_db.commit()
        out = build_net_worth(seeded_db, ctx)
        breakdown = {a.asset_class: a.value_cents for a in out.latest_breakdown}
        assert breakdown[AssetClass.CONTANT] == 50000  # geen rekeningdata → manueel blijft


class TestSummary:
    def test_gezinstotaal(self, logged_in, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        _nw(seeded_db, gem, date(2026, 6, 1), AssetClass.CONTANT, "1000.00")
        _nw(seeded_db, simon, date(2026, 6, 1), AssetClass.AANDELEN, "2500.00")
        seeded_db.commit()

        out = logged_in.get("/api/net-worth/summary").json()
        by_name = {c["name"]: c["total_cents"] for c in out["contexts"]}
        assert by_name["Gemeenschappelijk"] == 100000
        assert by_name["Simon"] == 250000
        assert out["total_cents"] == 350000


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
