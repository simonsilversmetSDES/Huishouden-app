"""Migratie-service beleggingen (spec §10): effect per naam, idempotent op effect-niveau."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Context, Security, SecurityTransaction
from app.services.investments import build_portfolio
from app.services.investments_import import InvestmentRow, import_rows


def _context(db: Session, name: str = "Simon") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _row(
    d: date, name: str, shares: str, price: str, fee: str = "0", tax: str = "0"
) -> InvestmentRow:
    return InvestmentRow(d, name, Decimal(shares), Decimal(price), Decimal(fee), Decimal(tax))


def _rows() -> list[InvestmentRow]:
    return [
        _row(date(2022, 1, 1), "VWCE", "20", "98"),
        _row(date(2022, 2, 1), "VWCE", "5", "99.2", tax="0.001375"),
        _row(date(2022, 3, 1), "IWDA", "10", "100", fee="1"),
    ]


class TestImportRows:
    def test_effecten_en_transacties(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        report = import_rows(seeded_db, ctx, _rows())
        seeded_db.commit()

        assert {s.name for s in report.securities} == {"VWCE", "IWDA"}
        secs = seeded_db.scalars(select(Security).where(Security.owner_context_id == ctx.id)).all()
        assert {s.name for s in secs} == {"VWCE", "IWDA"}
        assert seeded_db.scalar(select(func.count()).select_from(SecurityTransaction)) == 3

        # VWCE: 25 stuks, gemiddelde 98,240055 (dezelfde §10-referentie)
        vwce = next(p for p in build_portfolio(seeded_db, ctx).positions if p.name == "VWCE")
        assert vwce.shares == "25"
        assert vwce.avg_buy_price == "98.240055"

    def test_idempotent(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        import_rows(seeded_db, ctx, _rows())
        seeded_db.commit()
        # opnieuw draaien: effecten bestaan al mét transacties → overgeslagen
        report = import_rows(seeded_db, ctx, _rows())
        seeded_db.commit()
        assert all(s.skipped_existing for s in report.securities)
        assert seeded_db.scalar(select(func.count()).select_from(SecurityTransaction)) == 3
