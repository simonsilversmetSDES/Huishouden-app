"""Rekeningstatus-rekenlogica (spec §6, tests-first).

Referentie uit de echte Excel (tabblad Rekeningstatus, Gemeenschappelijk):
01/01/2025 → 3.000,10 ; 01/02/2025 → 3.143,00 ; verandering = 142,90 (≈ +4,76 %).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Context
from app.models.enums import AccountType, Bank
from app.services.account_status import build_account_status


def _context(db: Session, name: str = "Gemeenschappelijk") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _account(db: Session, context: Context, name: str, type_: AccountType) -> Account:
    account = Account(context_id=context.id, name=name, bank=Bank.KBC, type=type_)
    db.add(account)
    db.flush()
    return account


def _snapshot(db: Session, account: Account, d: date, balance: str) -> None:
    db.add(AccountSnapshot(account_id=account.id, snapshot_date=d, balance=Decimal(balance)))


class TestBuildAccountStatus:
    def _setup_gem(self, db: Session) -> Context:
        ctx = _context(db)
        zicht = _account(db, ctx, "KBC Zichtrekening", AccountType.ZICHT)
        spaar = _account(db, ctx, "KBC Spaarrekening", AccountType.SPAAR)
        _snapshot(db, zicht, date(2025, 1, 1), "3000.10")
        _snapshot(db, spaar, date(2025, 1, 1), "0")
        _snapshot(db, zicht, date(2025, 2, 1), "3000.00")
        _snapshot(db, spaar, date(2025, 2, 1), "143.00")
        db.commit()
        return ctx

    def test_totalen_en_verandering(self, seeded_db: Session) -> None:
        ctx = self._setup_gem(seeded_db)
        status = build_account_status(seeded_db, ctx, today=date(2025, 2, 15))

        jan, feb = status.rows
        assert jan.snapshot_date == date(2025, 1, 1)
        assert jan.total_cents == 300010
        assert jan.change_cents is None  # eerste maand: geen vorige
        assert jan.change_pct is None

        assert feb.snapshot_date == date(2025, 2, 1)
        assert feb.total_cents == 314300
        assert feb.change_cents == 14290
        assert feb.change_pct == pytest.approx(4.7632, abs=1e-4)

    def test_saldo_per_rekening(self, seeded_db: Session) -> None:
        ctx = self._setup_gem(seeded_db)
        status = build_account_status(seeded_db, ctx, today=date(2025, 2, 15))
        feb = status.rows[1]
        per_account = {b.account_id: b.balance_cents for b in feb.balances}
        namen = {a.id: a.name for a in status.accounts}
        by_name = {namen[aid]: cents for aid, cents in per_account.items()}
        assert by_name == {"KBC Zichtrekening": 300000, "KBC Spaarrekening": 14300}

    def test_missing_current_month(self, seeded_db: Session) -> None:
        ctx = self._setup_gem(seeded_db)
        # laatste snapshot is februari; in maart ontbreken beide rekeningen
        status = build_account_status(seeded_db, ctx, today=date(2025, 3, 3))
        assert status.missing_current_month is True
        assert len(status.missing_account_ids) == 2

    def test_niet_missing_wanneer_maand_ingevuld(self, seeded_db: Session) -> None:
        ctx = self._setup_gem(seeded_db)
        status = build_account_status(seeded_db, ctx, today=date(2025, 2, 20))
        assert status.missing_current_month is False
        assert status.missing_account_ids == []

    def test_lege_context(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db, "Simon")
        status = build_account_status(seeded_db, ctx, today=date(2025, 2, 1))
        assert status.rows == []
        assert status.accounts == []
        assert status.missing_current_month is False


class TestAccountSnapshotRoutes:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.get("/api/account-snapshots", params={"context_id": 1}).status_code == 401

    def test_upsert_en_status(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        zicht = _account(seeded_db, ctx, "KBC Zichtrekening", AccountType.ZICHT)
        seeded_db.commit()

        resp = logged_in.put(
            "/api/account-snapshots",
            json={"account_id": zicht.id, "snapshot_date": "2025-02-01", "balance_cents": 300000},
        )
        assert resp.status_code in (200, 201)

        # bijwerken van dezelfde (account, datum) overschrijft
        logged_in.put(
            "/api/account-snapshots",
            json={"account_id": zicht.id, "snapshot_date": "2025-02-01", "balance_cents": 250000},
        )
        rows = seeded_db.scalars(select(AccountSnapshot)).all()
        assert len(rows) == 1
        assert rows[0].balance == Decimal("2500.00")

        status = logged_in.get("/api/account-snapshots", params={"context_id": ctx.id}).json()
        assert status["rows"][0]["total_cents"] == 250000

    def test_delete(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        zicht = _account(seeded_db, ctx, "KBC Zichtrekening", AccountType.ZICHT)
        _snapshot(seeded_db, zicht, date(2025, 2, 1), "3000.00")
        seeded_db.commit()
        snap = seeded_db.scalars(select(AccountSnapshot)).one()

        assert logged_in.delete(f"/api/account-snapshots/{snap.id}").status_code == 204
        assert seeded_db.scalars(select(AccountSnapshot)).all() == []
