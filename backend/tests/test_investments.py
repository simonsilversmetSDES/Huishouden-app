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
from app.services.investments import (
    benchmark_yearly_returns,
    build_portfolio,
    portfolio_history,
    yearly_returns,
)


def _context(db: Session, name: str = "Simon") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _security(
    db: Session, ctx: Context, name: str, ticker: str | None = None, is_benchmark: bool = False
) -> Security:
    sec = Security(name=name, ticker=ticker, owner_context_id=ctx.id, is_benchmark=is_benchmark)
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


class TestDagwinst:
    def test_dagwinst_uit_laatste_twee_koersen(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "DAG")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2026, 7, 10), "100")
        _price(seeded_db, sec, date(2026, 7, 11), "102.50")
        seeded_db.commit()

        pos = build_portfolio(seeded_db, ctx).positions[0]
        # (102,50 − 100) × 10 = € 25,00; koers +2,5 %
        assert pos.day_gain_cents == 2500
        assert pos.day_gain_pct == pytest.approx(2.5, abs=1e-9)

    def test_dagverlies_negatief(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "DAG")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "4", "50", "200.00")
        _price(seeded_db, sec, date(2026, 7, 10), "50")
        _price(seeded_db, sec, date(2026, 7, 11), "49")
        seeded_db.commit()

        pos = build_portfolio(seeded_db, ctx).positions[0]
        # (49 − 50) × 4 = € −4,00; koers −2 %
        assert pos.day_gain_cents == -400
        assert pos.day_gain_pct == pytest.approx(-2.0, abs=1e-9)

    def test_een_koers_geen_dagwinst(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "DAG")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2026, 7, 11), "102")
        seeded_db.commit()

        pos = build_portfolio(seeded_db, ctx).positions[0]
        assert pos.day_gain_cents is None
        assert pos.day_gain_pct is None


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

    def test_waardering_voor_splitdatum_met_gecorrigeerde_koersen(self, seeded_db: Session) -> None:
        # yfinance slaat koersen terugwerkend split-gecorrigeerd op (huidige eenheden).
        # De waardering op een datum vóór de split moet het aantal dus óók in huidige
        # eenheden nemen, anders wordt de positie een factor `ratio` te klein geteld.
        # Scenario (echte SPDR-bug, 2025): koop 14 @ 250 in 2025 (totaal 3500);
        # 25:1-split op 15/02/2026. Koersen in post-split eenheden: 10,00 eind 2025,
        # 11,00 eind 2026. Eind 2025 = 14×25×10 = 3500 (niet 14×10 = 140).
        # 2025: (3500 − 0 − 3500) / 3500 = 0 %. 2026: (3850 − 3500 − 0) / 3500 = +10 %.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "SPDR")
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "14", "250", "3500.00")
        seeded_db.add(
            SecuritySplit(security_id=sec.id, date=date(2026, 2, 15), ratio=Decimal("25"))
        )
        _price(seeded_db, sec, date(2025, 12, 31), "10")
        _price(seeded_db, sec, date(2026, 12, 31), "11")
        seeded_db.commit()

        years = {y.year: y for y in yearly_returns(seeded_db, ctx, today=date(2026, 12, 31))}
        assert years[2025].end_value_cents == 350000
        assert years[2025].return_pct == pytest.approx(0.0, abs=1e-6)
        assert years[2026].start_value_cents == 350000
        assert years[2026].end_value_cents == 385000
        assert years[2026].return_pct == pytest.approx(10.0, abs=1e-6)


class TestBenchmark:
    """Koersrendement (geen Modified Dietz) van het effect met `is_benchmark=True`,
    als referentie naast het portefeuillerendement — spec §7-uitbreiding."""

    def test_geen_effect_gemarkeerd_geeft_none(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        _security(seeded_db, ctx, "A")  # geen benchmark
        seeded_db.commit()
        assert benchmark_yearly_returns(seeded_db, ctx, [2025], today=date(2025, 12, 31)) is None

    def test_koersrendement_over_twee_jaar(self, seeded_db: Session) -> None:
        # Koers 100 → 110 → 130,9 over 2024/2025: +10 % en +19 %, zonder rekening
        # te houden met wanneer/hoeveel er werd bijgestort (dat is net het verschil
        # met yearly_returns).
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "Wereldindex", is_benchmark=True)
        _price(seeded_db, sec, date(2023, 12, 31), "100")
        _price(seeded_db, sec, date(2024, 12, 31), "110")
        _price(seeded_db, sec, date(2025, 12, 31), "130.9")
        seeded_db.commit()

        bench = benchmark_yearly_returns(seeded_db, ctx, [2024, 2025], today=date(2025, 12, 31))
        assert bench is not None
        assert bench.security_id == sec.id
        assert bench.name == "Wereldindex"
        years = {y.year: y for y in bench.years}
        assert years[2024].complete is True
        assert years[2024].return_pct == pytest.approx(10.0, abs=1e-6)
        assert years[2025].complete is True
        assert years[2025].return_pct == pytest.approx(19.0, abs=1e-6)

    def test_koers_over_split_heen_niet_zelf_gecorrigeerd(self, seeded_db: Session) -> None:
        # Net als _value_as_of elders vergelijkt dit de opgeslagen koers zonder eigen
        # split-correctie: voor yfinance-tickers klopt dat, want yfinance geeft
        # historische koersen al terug-aangepast voor latere splits (een koers van
        # vóór de splitsdatum staat dus al in de huidige eenheden — zie de echte
        # SPYI-data die dit gedrag opleverde). Bij een koers die dat zelf niét doet,
        # zou dit jaar er onterecht dramatisch uitzien; dat is een bekende grens van
        # deze (en de bestaande) berekening, geen bug in deze functie.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "SplitIndex", is_benchmark=True)
        _price(seeded_db, sec, date(2024, 12, 31), "2500")
        _price(seeded_db, sec, date(2025, 12, 31), "130")
        seeded_db.add(SecuritySplit(security_id=sec.id, date=date(2025, 2, 1), ratio=Decimal("25")))
        seeded_db.commit()

        bench = benchmark_yearly_returns(seeded_db, ctx, [2025], today=date(2025, 12, 31))
        assert bench is not None
        assert bench.years[0].return_pct == pytest.approx(-94.8, abs=1e-6)

    def test_ontbrekende_grens_koers_onvolledig(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "Wereldindex", is_benchmark=True)
        _price(seeded_db, sec, date(2025, 6, 1), "150")  # geen koers eind 2024/2025
        seeded_db.commit()

        bench = benchmark_yearly_returns(seeded_db, ctx, [2025], today=date(2025, 6, 1))
        assert bench is not None
        assert bench.years[0].complete is False
        assert bench.years[0].return_pct is None

    def test_build_portfolio_neemt_benchmark_mee(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "Wereldindex", is_benchmark=True)
        _tx(seeded_db, sec, date(2025, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2025, 12, 31), "120")
        seeded_db.commit()

        pf = build_portfolio(seeded_db, ctx, today=date(2025, 12, 31))
        assert pf.benchmark is not None
        assert [y.year for y in pf.benchmark.years] == [y.year for y in pf.yearly_returns]


class TestPortfolioHistory:
    """Tijdreeks inleg (kostbasis) vs. waarde per effect, voor de waarde/inleg-grafiek.

    Zelfde rekenregels als build_portfolio, maar dan op elke roosterdatum:
    inleg = gemiddelde aankoopprijs-tot-dan × netto aantal-tot-dan; waarde =
    recentste koers op of vóór de datum × netto aantal (None zolang er geen
    koers bestaat en er wél een positie is)."""

    def test_inleg_en_waarde_per_datum(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "HIST")
        _tx(seeded_db, sec, date(2026, 1, 5), SecuritySide.BUY, "10", "100", "1000.00")
        _price(seeded_db, sec, date(2026, 1, 31), "110")
        _tx(seeded_db, sec, date(2026, 3, 1), SecuritySide.BUY, "5", "120", "600.00")
        _price(seeded_db, sec, date(2026, 4, 1), "130")
        seeded_db.commit()

        hist = portfolio_history(seeded_db, ctx, today=date(2026, 7, 1))
        # Rooster = transactiedatums ∪ koersdatums ∪ vandaag
        assert hist.dates == [
            date(2026, 1, 5), date(2026, 1, 31), date(2026, 3, 1),
            date(2026, 4, 1), date(2026, 7, 1),
        ]
        assert len(hist.series) == 1
        serie = hist.series[0]
        assert serie.security_id == sec.id
        # Inleg: 10×100 = 1000; na bijkoop avg = 1600/15 = 106,666667 × 15 → 1600,00
        assert [p.cost_cents for p in serie.points] == [
            100000, 100000, 160000, 160000, 160000,
        ]
        # Waarde: geen koers vóór 31/01 → None; daarna recentste koers × aantal
        assert [p.value_cents for p in serie.points] == [
            None, 110000, 165000, 195000, 195000,
        ]

    def test_verkoop_verlaagt_inleg_met_gemiddelde(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "SELL")
        _tx(seeded_db, sec, date(2026, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _tx(seeded_db, sec, date(2026, 2, 1), SecuritySide.SELL, "4", "150", "600.00")
        _price(seeded_db, sec, date(2026, 3, 1), "150")
        seeded_db.commit()

        serie = portfolio_history(seeded_db, ctx, today=date(2026, 3, 15)).series[0]
        # Na verkoop: kostbasis = avg 100 × 6 = 600 (niet 1000 − 600 opbrengst)
        assert [p.cost_cents for p in serie.points] == [100000, 60000, 60000, 60000]
        assert [p.value_cents for p in serie.points] == [None, None, 90000, 90000]

    def test_split_aantallen_in_huidige_eenheden(self, seeded_db: Session) -> None:
        # Koersen volgen de yfinance-conventie (terugwerkend split-gecorrigeerd),
        # dus ook vóór de splitdatum rekent de reeks in post-split eenheden.
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "SPLIT")
        _tx(seeded_db, sec, date(2026, 1, 1), SecuritySide.BUY, "2", "100", "200.00")
        seeded_db.add(
            SecuritySplit(security_id=sec.id, date=date(2026, 2, 1), ratio=Decimal("25"))
        )
        _price(seeded_db, sec, date(2026, 3, 1), "4.40")
        seeded_db.commit()

        serie = portfolio_history(seeded_db, ctx, today=date(2026, 3, 15)).series[0]
        # 2×25 = 50 stuks; inleg blijft € 200; waarde = 4,40 × 50 = € 220
        assert [p.cost_cents for p in serie.points] == [20000, 20000, 20000]
        assert [p.value_cents for p in serie.points] == [None, 22000, 22000]

    def test_rooster_start_bij_eerste_transactie(self, seeded_db: Session) -> None:
        # Backfill-koersen van vóór de eerste aankoop horen niet in het rooster
        # (anders begint de grafiek met een lange platte nul-lijn).
        ctx = _context(seeded_db)
        sec = _security(seeded_db, ctx, "TRIM")
        _price(seeded_db, sec, date(2025, 12, 1), "100")
        _tx(seeded_db, sec, date(2026, 1, 10), SecuritySide.BUY, "10", "100", "1000.00")
        seeded_db.commit()

        hist = portfolio_history(seeded_db, ctx, today=date(2026, 2, 1))
        assert hist.dates == [date(2026, 1, 10), date(2026, 2, 1)]
        serie = hist.series[0]
        # De oudere koers telt wél mee als recentste koers op de startdatum
        assert [p.value_cents for p in serie.points] == [100000, 100000]

    def test_twee_effecten_gedeeld_rooster_en_effect_zonder_transacties_weg(
        self, seeded_db: Session
    ) -> None:
        ctx = _context(seeded_db)
        a = _security(seeded_db, ctx, "A")
        b = _security(seeded_db, ctx, "B")
        _security(seeded_db, ctx, "LEEG")  # geen transacties → geen reeks
        _tx(seeded_db, a, date(2026, 1, 1), SecuritySide.BUY, "10", "100", "1000.00")
        _tx(seeded_db, b, date(2026, 2, 1), SecuritySide.BUY, "5", "200", "1000.00")
        _price(seeded_db, a, date(2026, 3, 1), "110")
        _price(seeded_db, b, date(2026, 3, 1), "180")
        seeded_db.commit()

        hist = portfolio_history(seeded_db, ctx, today=date(2026, 3, 1))
        assert hist.dates == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
        assert [s.name for s in hist.series] == ["A", "B"]
        by_name = {s.name: s for s in hist.series}
        # B heeft vóór zijn eerste aankoop een lege positie: inleg 0 en waarde 0
        assert [p.cost_cents for p in by_name["B"].points] == [0, 100000, 100000]
        assert [p.value_cents for p in by_name["B"].points] == [0, None, 90000]
        assert [p.value_cents for p in by_name["A"].points] == [None, None, 110000]

    def test_geen_transacties_geeft_leeg(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        _security(seeded_db, ctx, "LEEG")
        seeded_db.commit()
        hist = portfolio_history(seeded_db, ctx, today=date(2026, 1, 1))
        assert hist.dates == []
        assert hist.series == []
