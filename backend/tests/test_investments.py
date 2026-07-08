"""Beleggings-rekenlogica (spec §7, tests-first).

Referentie §10: gemiddelde aankoopprijs = € 98,240055 bij 25 stuks. Hier bewezen
op de formule (Σtotaal_koop / Σaantal, 6 decimalen) met een exacte fixture; de
échte 25-koopregels uit de Excel worden in de migratie-sanity-check geverifieerd.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, Security, SecurityPrice, SecuritySplit, SecurityTransaction
from app.models.enums import SecuritySide
from app.schemas.investments import RealizedYearOut
from app.services.investments import build_portfolio, yearly_returns


def _context(db: Session, name: str = "Simon") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _security(db: Session, ctx: Context, name: str, ticker: str | None = None) -> Security:
    sec = Security(name=name, ticker=ticker, owner_context_id=ctx.id)
    db.add(sec)
    db.flush()
    return sec


def _tx(
    db: Session,
    sec: Security,
    d: date,
    side: SecuritySide,
    shares: str,
    price: str,
    total: str,
    fee: str = "0",
    tax: str = "0",
) -> None:
    db.add(
        SecurityTransaction(
            security_id=sec.id,
            date=d,
            side=side,
            shares=Decimal(shares),
            price_per_share=Decimal(price),
            fee=Decimal(fee),
            tax=Decimal(tax),
            total=Decimal(total),
        )
    )


def _price(db: Session, sec: Security, d: date, price: str) -> None:
    db.add(SecurityPrice(security_id=sec.id, date=d, price=Decimal(price)))


class TestGemiddeldeAankoopprijs:
    def test_98_240055(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "iShares IWDA World ETF")
        # 25 stuks, Σtotaal = 2456,001375 → gemiddelde 98,240055 (6 decimalen)
        _tx(seeded_db, sec, date(2022, 1, 1), SecuritySide.BUY, "20", "98", "1960.00")
        _tx(seeded_db, sec, date(2022, 2, 1), SecuritySide.BUY, "5", "99.20", "496.001375",
            tax="0.001375")
        seeded_db.add(
            SecurityPrice(security_id=sec.id, date=date(2026, 7, 1), price=Decimal("153.96"))
        )
        seeded_db.commit()

        portfolio = build_portfolio(seeded_db, ctx)
        assert len(portfolio.positions) == 1
        pos = portfolio.positions[0]
        assert pos.avg_buy_price == "98.240055"
        assert pos.shares == "25"
        assert pos.cost_cents == 245600  # 98,240055 × 25
        assert pos.value_cents == 384900  # 153,96 × 25
        assert pos.gain_cents == 139300
        assert pos.gain_pct == pytest.approx(56.7182, abs=1e-3)

    def test_zonder_koers_geen_waarde(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "Fonds zonder ticker")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        seeded_db.commit()
        pos = build_portfolio(seeded_db, ctx).positions[0]
        assert pos.value_cents is None
        assert pos.gain_cents is None
        assert pos.cost_cents == 100000


class TestStockSplit:
    def test_split_past_aantal_en_gemiddelde_aan(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "SPYI")
        # 17 stuks vóór de split (à 200, totaal 3400), dan 25:1-split, dan 630 stuks
        _tx(seeded_db, sec, date(2026, 1, 1), SecuritySide.BUY, "17", "200", "3400.00")
        _tx(seeded_db, sec, date(2026, 4, 1), SecuritySide.BUY, "630", "10", "6300.00")
        seeded_db.add(
            SecuritySplit(security_id=sec.id, date=date(2026, 2, 1), ratio=Decimal("25"))
        )
        seeded_db.commit()

        pos = build_portfolio(seeded_db, ctx).positions[0]
        # 17 × 25 = 425, + 630 = 1055 aandelen
        assert pos.shares == "1055"
        # gemiddelde = (3400 + 6300) / 1055
        assert pos.avg_buy_price == "9.194313"

    def test_zonder_split_ongewijzigd(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "GEEN")
        _tx(seeded_db, sec, date(2026, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        seeded_db.commit()
        pos = build_portfolio(seeded_db, ctx).positions[0]
        assert pos.shares == "10"


class TestPortefeuille:
    def test_totalen_en_netto_aantal(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        a = _security(seeded_db, ctx, "A")
        b = _security(seeded_db, ctx, "B")
        _tx(seeded_db, a, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _tx(seeded_db, b, date(2025, 1, 1), SecuritySide.BUY, "5", "200", "1000.00")
        seeded_db.add_all(
            [
                SecurityPrice(security_id=a.id, date=date(2026, 1, 1), price=Decimal("110")),
                SecurityPrice(security_id=b.id, date=date(2026, 1, 1), price=Decimal("180")),
            ]
        )
        seeded_db.commit()

        pf = build_portfolio(seeded_db, ctx)
        assert pf.total_cost_cents == 200000
        assert pf.total_value_cents == 110000 + 90000  # A 110×10, B 180×5
        assert pf.total_gain_cents == 0  # +10000 (A) −10000 (B)
        # portfolio_pct sommeert tot ~100
        assert sum(p.portfolio_pct for p in pf.positions) == pytest.approx(100.0, abs=1e-6)

    def test_netto_aantal_na_verkoop(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "C")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _tx(seeded_db, sec, date(2025, 6, 1), SecuritySide.SELL, "4", "120", "480.00")
        seeded_db.commit()
        pos = build_portfolio(seeded_db, ctx).positions[0]
        assert pos.shares == "6"


class TestGerealiseerdeMeerwaarde:
    def test_verkoop_meerwaarde_en_jaartotaal(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "D")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")  # avg 100
        _tx(seeded_db, sec, date(2025, 6, 1), SecuritySide.SELL, "4", "120", "480.00")
        seeded_db.commit()

        pf = build_portfolio(seeded_db, ctx)
        assert len(pf.realized_gains) == 1
        gain = pf.realized_gains[0]
        assert gain.proceeds_cents == 48000
        assert gain.cost_basis_cents == 40000
        assert gain.gain_cents == 8000
        assert gain.year == 2025
        assert pf.realized_by_year == [RealizedYearOut(year=2025, gain_cents=8000)]


class TestJaarrendement:
    """Rendement per kalenderjaar volgens Modified Dietz (dagen-gewogen kasstromen).

    rendement = (Weinde − Wstart − netto_instroom) / (Wstart + Σ instroom×(T−t)/T)
    """

    def test_enkel_jaar_lump_sum(self, seeded_db: Session) -> None:
        # Koop 10 @ 100 op 1/1/2025 (inleg 1000), koers eindejaar 120 → waarde 1200.
        # Volledig jaar belegd: (1200 − 0 − 1000) / (0 + 1000×1) = 20 %.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "A")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2025, 12, 31), "120")
        seeded_db.commit()

        years = yearly_returns(seeded_db, ctx, today=date(2025, 12, 31))
        assert len(years) == 1
        y = years[0]
        assert y.year == 2025
        assert y.complete is True
        assert y.start_value_cents == 0
        assert y.end_value_cents == 120000
        assert y.net_flow_cents == 100000
        assert y.return_pct == pytest.approx(20.0, abs=1e-6)

    def test_meerjaar_met_bijstorting_midden_in_het_jaar(self, seeded_db: Session) -> None:
        # 2024: koop 10 @ 100 op 1/1 (1000), koers 31/12/2024 = 110 → +10 %.
        # 2025: startwaarde 1100; bijkoop 5 @ 120 op 2/7 (600); koers 31/12/2025 = 130
        #   → waarde 1950. T = 364 dagen, storting op dag 182 → gewicht (364−182)/364 = 0,5.
        #   (1950 − 1100 − 600) / (1100 + 600×0,5) = 250 / 1400 = 17,857143 %.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "B")
        _tx(seeded_db, sec, date(2024, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _tx(seeded_db, sec, date(2025, 7, 2), SecuritySide.BUY, "5", "120", "600.00")
        _price(seeded_db, sec, date(2024, 12, 31), "110")
        _price(seeded_db, sec, date(2025, 12, 31), "130")
        seeded_db.commit()

        years = {y.year: y for y in yearly_returns(seeded_db, ctx, today=date(2025, 12, 31))}
        assert set(years) == {2024, 2025}

        assert years[2024].complete is True
        assert years[2024].start_value_cents == 0
        assert years[2024].end_value_cents == 110000
        assert years[2024].return_pct == pytest.approx(10.0, abs=1e-6)

        assert years[2025].complete is True
        assert years[2025].start_value_cents == 110000
        assert years[2025].end_value_cents == 195000
        assert years[2025].net_flow_cents == 60000
        assert years[2025].return_pct == pytest.approx(17.857143, abs=1e-4)

    def test_ontbrekende_koers_markeert_jaar_onvolledig(self, seeded_db: Session) -> None:
        # Positie sinds 2023, maar enkel een recente koers (2025). De jaargrenzen
        # 2022/2023/2024-eind hebben geen koers binnen de tolerantie → geen misleidend cijfer.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "C")
        _tx(seeded_db, sec, date(2023, 6, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2025, 6, 1), "150")
        seeded_db.commit()

        years = yearly_returns(seeded_db, ctx, today=date(2025, 6, 1))
        assert [y.year for y in years] == [2023, 2024, 2025]
        for y in years:
            assert y.complete is False
            assert y.return_pct is None

    def test_geen_transacties_geeft_lege_lijst(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        assert yearly_returns(seeded_db, ctx, today=date(2025, 12, 31)) == []
