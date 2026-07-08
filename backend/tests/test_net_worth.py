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

from app.models import (
    Account,
    AccountSnapshot,
    Context,
    NetWorthSnapshot,
    Security,
    SecurityPrice,
    SecurityTransaction,
)
from app.models.enums import AccountType, AssetClass, Bank, SecurityKind, SecuritySide
from app.services.net_worth import build_net_worth, build_net_worth_combined


def _context(db: Session, name: str = "Gemeenschappelijk") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _nw(db: Session, ctx: Context, d: date, asset: AssetClass, value: str) -> None:
    db.add(
        NetWorthSnapshot(
            context_id=ctx.id, snapshot_date=d, asset_class=asset, value=Decimal(value)
        )
    )


def _asnap(db: Session, account_id: int, d: date, amount: str) -> None:
    db.add(AccountSnapshot(account_id=account_id, snapshot_date=d, balance=Decimal(amount)))


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


class TestRekeningKlassen:
    def _account(self, db: Session, ctx: Context, name: str, type_: AccountType) -> Account:
        acc = Account(context_id=ctx.id, name=name, bank=Bank.KBC, type=type_)
        db.add(acc)
        db.flush()
        return acc

    def test_rekening_types_naar_klasse(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Simon")
        jun = date(2026, 6, 1)
        zicht = self._account(seeded_db, ctx, "Zicht", AccountType.ZICHT)
        spaar = self._account(seeded_db, ctx, "Spaar", AccountType.SPAAR)
        pensioen = self._account(seeded_db, ctx, "Pensioensparen", AccountType.PENSIOENSPAREN)
        groeps = self._account(seeded_db, ctx, "Groepsverzekering", AccountType.GROEPSVERZEKERING)
        _asnap(seeded_db, zicht.id, jun, "1000.00")
        _asnap(seeded_db, spaar.id, jun, "2000.00")
        _asnap(seeded_db, pensioen.id, jun, "500.00")
        _asnap(seeded_db, groeps.id, jun, "3000.00")
        seeded_db.commit()

        out = build_net_worth(seeded_db, ctx, today=jun)
        breakdown = {a.asset_class: a.value_cents for a in out.latest_breakdown}
        assert breakdown[AssetClass.CONTANT] == 300000  # zicht + spaar
        assert breakdown[AssetClass.PENSIOENSPAREN] == 50000
        assert breakdown[AssetClass.GROEPSVERZEKERING] == 300000
        assert out.latest_total_cents == 650000


class TestBeleggingenAfleiding:
    def _security(self, db: Session, ctx: Context, name: str, soort: SecurityKind) -> Security:
        sec = Security(name=name, owner_context_id=ctx.id, soort=soort)
        db.add(sec)
        db.flush()
        return sec

    def _buy(self, db: Session, sec: Security, shares: str, price: str, total: str) -> None:
        db.add(
            SecurityTransaction(
                security_id=sec.id,
                date=date(2026, 1, 1),
                side=SecuritySide.BUY,
                shares=Decimal(shares),
                price_per_share=Decimal(price),
                fee=Decimal("0"),
                tax=Decimal("0"),
                total=Decimal(total),
            )
        )

    def test_beleggingen_op_huidige_maand_per_soort(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Simon")
        etf = self._security(seeded_db, ctx, "IWDA", SecurityKind.ETF_FONDSEN)
        aandeel = self._security(seeded_db, ctx, "Alphabet", SecurityKind.AANDELEN)
        self._buy(seeded_db, etf, "10", "100", "1000")
        self._buy(seeded_db, aandeel, "5", "100", "500")
        seeded_db.add_all(
            [
                SecurityPrice(security_id=etf.id, date=date(2026, 6, 1), price=Decimal("150")),
                SecurityPrice(security_id=aandeel.id, date=date(2026, 6, 1), price=Decimal("200")),
            ]
        )
        seeded_db.commit()

        out = build_net_worth(seeded_db, ctx, today=date(2026, 7, 8))
        assert out.latest_date == date(2026, 7, 1)  # huidige maand automatisch aangemaakt
        breakdown = {a.asset_class: a.value_cents for a in out.latest_breakdown}
        assert breakdown[AssetClass.ETF_FONDSEN] == 150000  # 10 × 150
        assert breakdown[AssetClass.AANDELEN] == 100000  # 5 × 200

    def test_oudere_maand_manueel_blijft(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Jozefien")
        _nw(seeded_db, ctx, date(2026, 3, 1), AssetClass.ETF_FONDSEN, "1000.00")  # oude manuele
        etf = self._security(seeded_db, ctx, "IWDA", SecurityKind.ETF_FONDSEN)
        self._buy(seeded_db, etf, "10", "100", "1000")
        seeded_db.add(
            SecurityPrice(security_id=etf.id, date=date(2026, 6, 1), price=Decimal("150"))
        )
        seeded_db.commit()

        out = build_net_worth(seeded_db, ctx, today=date(2026, 7, 8))
        by_month = {
            r.snapshot_date: {a.asset_class: a.value_cents for a in r.assets} for r in out.rows
        }
        assert by_month[date(2026, 3, 1)][AssetClass.ETF_FONDSEN] == 100000  # manueel ongewijzigd
        assert by_month[date(2026, 7, 1)][AssetClass.ETF_FONDSEN] == 150000  # live huidige maand


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


class TestGecombineerd:
    def test_optellen_per_maand_en_klasse(self, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        _nw(seeded_db, gem, date(2026, 5, 1), AssetClass.CONTANT, "800.00")
        _nw(seeded_db, gem, date(2026, 6, 1), AssetClass.CONTANT, "1000.00")
        _nw(seeded_db, simon, date(2026, 6, 1), AssetClass.CONTANT, "500.00")
        _nw(seeded_db, simon, date(2026, 6, 1), AssetClass.AANDELEN, "2500.00")
        seeded_db.commit()

        out = build_net_worth_combined(seeded_db, [gem, simon], today=date(2026, 6, 1))
        by_month = {
            r.snapshot_date: {a.asset_class: a.value_cents for a in r.assets} for r in out.rows
        }
        assert by_month[date(2026, 5, 1)][AssetClass.CONTANT] == 80000  # enkel gem
        assert by_month[date(2026, 6, 1)][AssetClass.CONTANT] == 150000  # 1000 + 500
        assert by_month[date(2026, 6, 1)][AssetClass.AANDELEN] == 250000
        assert out.latest_total_cents == 400000  # 1500 + 2500
        assert out.rows[-1].change_cents == 320000  # 4000 − 800
        assert out.context_id == 0

    def test_route(self, logged_in: TestClient, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        _nw(seeded_db, gem, date(2026, 6, 1), AssetClass.CONTANT, "1000.00")
        _nw(seeded_db, simon, date(2026, 6, 1), AssetClass.AANDELEN, "2500.00")
        seeded_db.commit()

        resp = logged_in.get(
            "/api/net-worth/combined", params={"context_ids": [gem.id, simon.id]}
        )
        assert resp.status_code == 200
        assert resp.json()["latest_total_cents"] == 350000


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
