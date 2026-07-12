"""Beleggingslogica (spec §7): posities, gemiddelde aankoopprijs, winst/verlies.

Per effect (Security) worden de transacties samengevat tot een positie:
- totaal aantal = Σ aankopen − Σ verkopen (fractioneel toegestaan);
- **gemiddelde aankoopprijs** = Σ(totaal van de aankopen) / Σ(aantal gekocht),
  kosten en beurstaks (TOB) inbegrepen, gekwantiseerd op 6 decimalen (§10);
- kostbasis van de huidige positie = gem. aankoopprijs × aantal;
- actuele waarde = laatste koers × aantal; winst/verlies = waarde − kostbasis.

Bij verkopen: gerealiseerde meerwaarde = opbrengst − (gem. aankoopprijs × aantal),
met jaartotaal (BE-meerwaardebelasting vanaf 2026; berekening, geen fiscaal advies).

Hoeveelheden en koersen zijn exacte Decimals (nooit float); geld gaat als centen
de API uit via to_cents. Winst = waarde_cent − kost_cent, zodat het altijd klopt
met de getoonde waarde en kostprijs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, Security, SecurityPrice, SecuritySplit, SecurityTransaction
from app.models.enums import AssetClass, SecuritySide
from app.schemas.investments import (
    BenchmarkOut,
    BenchmarkYearOut,
    PortfolioOut,
    PositionOut,
    RealizedGainOut,
    RealizedYearOut,
    YearReturnOut,
)
from app.services.budget import to_cents

ZERO = Decimal("0")
SIX = Decimal("0.000001")

# Een jaargrens-koers mag maximaal zoveel dagen ouder zijn dan de grens zelf;
# anders valt het jaar niet betrouwbaar te waarderen (bv. enkel maandelijkse
# manuele koersen). Ruim genoeg voor maandelijkse invoer, streng genoeg om
# ontbrekende jaren te herkennen.
PRICE_TOLERANCE_DAYS = 45


def _latest_prices(
    db: Session, security_ids: list[int]
) -> dict[int, tuple[Decimal, Decimal | None]]:
    """Recentste én voorlaatste koers per effect (op datum) — de voorlaatste dient
    voor de dagwinst/-verlieskolom (verschil met de vorige koersdag)."""
    latest: dict[int, tuple[Decimal, Decimal | None]] = {}
    for price in db.scalars(
        select(SecurityPrice)
        .where(SecurityPrice.security_id.in_(security_ids))
        .order_by(SecurityPrice.date)
    ):
        previous = latest.get(price.security_id)  # oplopend gesorteerd → laatste wint
        latest[price.security_id] = (price.price, previous[0] if previous else None)
    return latest


def _pct(numerator: int, denominator: int) -> float | None:
    return float(Decimal(numerator) / Decimal(denominator) * 100) if denominator else None


def _split_factor(splits: list[SecuritySplit], tx_date: date) -> Decimal:
    """Cumulatieve factor: product van de ratio's van alle splits ná de transactie
    (een 25:1-split na je aankoop maakt van 1 aandeel er 25)."""
    factor = Decimal(1)
    for split in splits:
        if split.date > tx_date:
            factor *= split.ratio
    return factor


def build_portfolio(db: Session, context: Context, today: date | None = None) -> PortfolioOut:
    securities = list(
        db.scalars(
            select(Security)
            .where(Security.owner_context_id == context.id)
            .order_by(Security.name)
        )
    )
    empty = PortfolioOut(
        context_id=context.id,
        positions=[],
        total_value_cents=0,
        total_cost_cents=0,
        total_gain_cents=0,
        total_gain_pct=None,
        realized_gains=[],
        realized_by_year=[],
        yearly_returns=[],
    )
    if not securities:
        return empty

    security_ids = [s.id for s in securities]
    by_security: dict[int, list[SecurityTransaction]] = defaultdict(list)
    for tx in db.scalars(
        select(SecurityTransaction)
        .where(SecurityTransaction.security_id.in_(security_ids))
        .order_by(SecurityTransaction.date, SecurityTransaction.id)
    ):
        by_security[tx.security_id].append(tx)
    latest = _latest_prices(db, security_ids)

    splits_by_security: dict[int, list[SecuritySplit]] = defaultdict(list)
    for split in db.scalars(
        select(SecuritySplit).where(SecuritySplit.security_id.in_(security_ids))
    ):
        splits_by_security[split.security_id].append(split)

    realized: list[RealizedGainOut] = []
    computed: list[dict] = []
    total_value = 0
    total_cost = 0
    for security in securities:
        txns = by_security.get(security.id, [])
        splits = splits_by_security.get(security.id, [])
        buys = [t for t in txns if t.side == SecuritySide.BUY]
        sells = [t for t in txns if t.side == SecuritySide.SELL]
        # Aantallen naar huidige (post-split) eenheden brengen; totaal (= geld) blijft.
        shares_bought = sum((t.shares * _split_factor(splits, t.date) for t in buys), ZERO)
        total_bought = sum((t.total for t in buys), ZERO)
        shares_sold = sum((t.shares * _split_factor(splits, t.date) for t in sells), ZERO)
        net = shares_bought - shares_sold
        avg = (total_bought / shares_bought).quantize(SIX, ROUND_HALF_UP) if shares_bought else None

        cost_cents = to_cents(avg * net) if avg is not None else 0
        price, prev_price = latest.get(security.id, (None, None))
        value_cents = to_cents(price * net) if price is not None else None
        gain_cents = value_cents - cost_cents if value_cents is not None else None
        # Dagwinst = waarde nu − waarde aan de voorlaatste koers (zelfde afronding
        # als de waardekolom, dus de bedragen sluiten op elkaar aan).
        day_gain_cents = (
            value_cents - to_cents(prev_price * net)
            if value_cents is not None and prev_price is not None
            else None
        )
        day_gain_pct = (
            float((price / prev_price - 1) * 100)
            if price is not None and prev_price is not None and prev_price != ZERO
            else None
        )

        computed.append(
            {
                "s": security,
                "net": net,
                "avg": avg,
                "cost_cents": cost_cents,
                "price": price,
                "value_cents": value_cents,
                "gain_cents": gain_cents,
                "day_gain_cents": day_gain_cents,
                "day_gain_pct": day_gain_pct,
            }
        )
        total_cost += cost_cents
        if value_cents is not None:
            total_value += value_cents

        for sell in sells:
            if avg is None:
                continue
            adjusted_sold = sell.shares * _split_factor(splits, sell.date)
            proceeds_cents = to_cents(sell.price_per_share * sell.shares)  # echte opbrengst
            cost_basis_cents = to_cents(avg * adjusted_sold)
            realized.append(
                RealizedGainOut(
                    security_id=security.id,
                    name=security.name,
                    date=sell.date,
                    shares=str(sell.shares),
                    proceeds_cents=proceeds_cents,
                    cost_basis_cents=cost_basis_cents,
                    gain_cents=proceeds_cents - cost_basis_cents,
                    year=sell.date.year,
                )
            )

    positions: list[PositionOut] = []
    for row in computed:
        value_cents = row["value_cents"]
        cost_cents = row["cost_cents"]
        gain_cents = row["gain_cents"]
        positions.append(
            PositionOut(
                security_id=row["s"].id,
                name=row["s"].name,
                ticker=row["s"].ticker,
                shares=str(row["net"]),
                avg_buy_price=str(row["avg"]) if row["avg"] is not None else None,
                cost_cents=cost_cents,
                current_price=str(row["price"]) if row["price"] is not None else None,
                value_cents=value_cents,
                gain_cents=gain_cents,
                gain_pct=_pct(gain_cents, cost_cents) if gain_cents is not None else None,
                day_gain_cents=row["day_gain_cents"],
                day_gain_pct=row["day_gain_pct"],
                portfolio_pct=_pct(value_cents, total_value) or 0.0
                if value_cents is not None
                else 0.0,
            )
        )

    by_year: dict[int, int] = defaultdict(int)
    for gain in realized:
        by_year[gain.year] += gain.gain_cents

    return PortfolioOut(
        context_id=context.id,
        positions=positions,
        total_value_cents=total_value,
        total_cost_cents=total_cost,
        total_gain_cents=total_value - total_cost,
        total_gain_pct=_pct(total_value - total_cost, total_cost),
        realized_gains=realized,
        realized_by_year=[
            RealizedYearOut(year=year, gain_cents=cents) for year, cents in sorted(by_year.items())
        ],
        yearly_returns=(returns := yearly_returns(db, context, today)),
        benchmark=benchmark_yearly_returns(db, context, [y.year for y in returns], today),
    )


def _shares_as_of(
    txns: list[SecurityTransaction], splits: list[SecuritySplit], on: date
) -> Decimal:
    """Aangehouden aantal op datum `on`, altijd in de huidige (post-split) eenheden.

    Bewust niet "de eenheden die op dat moment golden": de opgeslagen koersreeks
    volgt de yfinance-conventie en is terugwerkend split-gecorrigeerd (een koers
    van vóór de splitsdatum staat al in de huidige eenheden). Waarde-op-datum =
    aantal × koers klopt dus enkel als het aantal dezelfde eenheden gebruikt —
    anders wordt een positie vóór de split een factor `ratio` te klein geteld."""
    shares = ZERO
    for tx in txns:
        if tx.date > on:
            continue
        signed = tx.shares if tx.side == SecuritySide.BUY else -tx.shares
        shares += signed * _split_factor(splits, tx.date)
    return shares


def _price_as_of(
    history: list[tuple[date, Decimal]], on: date, allow_stale: bool
) -> Decimal | None:
    """Recentste koers op of vóór `on`. Buiten de tolerantie (en niet `allow_stale`)
    → None, zodat een jaar zonder bruikbare grens-koers als onvolledig geldt."""
    best: tuple[date, Decimal] | None = None
    for point in history:  # oplopend gesorteerd
        if point[0] <= on:
            best = point
        else:
            break
    if best is None:
        return None
    if not allow_stale and (on - best[0]).days > PRICE_TOLERANCE_DAYS:
        return None
    return best[1]


def _value_as_of(
    on: date,
    securities: list[Security],
    by_security: dict[int, list[SecurityTransaction]],
    splits_by_security: dict[int, list[SecuritySplit]],
    prices_by_security: dict[int, list[tuple[date, Decimal]]],
    allow_stale: bool,
) -> tuple[Decimal, bool]:
    """Portefeuillewaarde op datum `on` en of ze volledig te bepalen viel
    (True als elke aangehouden positie een koers binnen de tolerantie had)."""
    total = ZERO
    complete = True
    for security in securities:
        shares = _shares_as_of(
            by_security.get(security.id, []), splits_by_security.get(security.id, []), on
        )
        if shares == ZERO:
            continue
        price = _price_as_of(prices_by_security.get(security.id, []), on, allow_stale)
        if price is None:
            complete = False
            continue
        total += price * shares
    return total, complete


def _load_tx_history(
    db: Session, security_ids: list[int]
) -> tuple[
    dict[int, list[SecurityTransaction]],
    dict[int, list[SecuritySplit]],
    dict[int, list[tuple[date, Decimal]]],
]:
    """Transacties, splits en koershistoriek per effect (chronologisch gesorteerd)."""
    by_security: dict[int, list[SecurityTransaction]] = defaultdict(list)
    for tx in db.scalars(
        select(SecurityTransaction)
        .where(SecurityTransaction.security_id.in_(security_ids))
        .order_by(SecurityTransaction.date, SecurityTransaction.id)
    ):
        by_security[tx.security_id].append(tx)

    splits_by_security: dict[int, list[SecuritySplit]] = defaultdict(list)
    for split in db.scalars(
        select(SecuritySplit).where(SecuritySplit.security_id.in_(security_ids))
    ):
        splits_by_security[split.security_id].append(split)

    prices_by_security: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    for price in db.scalars(
        select(SecurityPrice)
        .where(SecurityPrice.security_id.in_(security_ids))
        .order_by(SecurityPrice.date)
    ):
        prices_by_security[price.security_id].append((price.date, price.price))

    return by_security, splits_by_security, prices_by_security


def beleggingen_by_class_history(
    db: Session, context: Context, dates: list[date]
) -> dict[date, dict[AssetClass, Decimal]]:
    """Beleggingswaarde per activaklasse op elk van de gegeven datums (spec §9):
    aantallen uit de transacties (split-correct), gewaardeerd met de recentste
    koers op of vóór de datum. Effecten zonder positie of zonder koers blijven
    weg, zodat de vermogensbalans geen nul-rijen krijgt."""
    securities = list(
        db.scalars(select(Security).where(Security.owner_context_id == context.id))
    )
    if not securities or not dates:
        return {}
    by_security, splits_by_security, prices_by_security = _load_tx_history(
        db, [s.id for s in securities]
    )
    out: dict[date, dict[AssetClass, Decimal]] = {}
    for on in dates:
        totals: dict[AssetClass, Decimal] = {}
        for security in securities:
            shares = _shares_as_of(
                by_security.get(security.id, []), splits_by_security.get(security.id, []), on
            )
            if shares == ZERO:
                continue
            price = _price_as_of(prices_by_security.get(security.id, []), on, allow_stale=True)
            if price is None:
                continue
            asset_class = AssetClass(security.soort.value)
            totals[asset_class] = totals.get(asset_class, ZERO) + price * shares
        if totals:
            out[on] = totals
    return out


def benchmark_yearly_returns(
    db: Session, context: Context, years: list[int], today: date | None = None
) -> BenchmarkOut | None:
    """Koersrendement per kalenderjaar van het effect gemarkeerd als referentie-index
    (`is_benchmark`), voor dezelfde jaren als `yearly_returns` (spec §7-uitbreiding).

    In tegenstelling tot het portefeuillerendement is dit géén Modified Dietz: het is
    puur koers-eind t.o.v. koers-begin, zodat het antwoord geeft op "wat deed de index",
    los van wanneer er werd bijgestort.

    Geen eigen split-correctie: net als `_value_as_of` elders wordt de opgeslagen koers
    zonder aanpassing over de tijd vergeleken. Voor tickers die via yfinance ververst
    worden (het gangbare geval voor een index-ETF) is dat correct, want yfinance geeft
    historische slotkoersen terug-aangepast voor latere splits terug — een koers van
    vóór de effectieve splitsdatum staat dus al in de huidige eenheden."""
    if today is None:
        today = date.today()

    security = db.scalars(
        select(Security)
        .where(Security.owner_context_id == context.id, Security.is_benchmark.is_(True))
        .order_by(Security.id)
    ).first()
    if security is None:
        return None

    _, _, prices_by_security = _load_tx_history(db, [security.id])
    prices = prices_by_security.get(security.id, [])

    out: list[BenchmarkYearOut] = []
    for year in years:
        period_start = date(year - 1, 12, 31)
        is_current = year == today.year
        period_end = today if is_current else date(year, 12, 31)

        price_start = _price_as_of(prices, period_start, allow_stale=False)
        price_end = _price_as_of(prices, period_end, allow_stale=is_current)
        if price_start is None or price_end is None or price_start == ZERO:
            out.append(BenchmarkYearOut(year=year, return_pct=None, complete=False))
            continue

        return_pct = float((price_end - price_start) / price_start * 100)
        out.append(BenchmarkYearOut(year=year, return_pct=return_pct, complete=True))

    return BenchmarkOut(security_id=security.id, name=security.name, years=out)


def yearly_returns(
    db: Session, context: Context, today: date | None = None
) -> list[YearReturnOut]:
    """Rendement per kalenderjaar via Modified Dietz (spec §7).

    Per jaar: (Weinde − Wstart − netto_instroom) / (Wstart + Σ instroom×(T−t)/T),
    waarbij instroom = aankoop-totalen (+) en verkoop-opbrengsten (−), dag-gewogen
    over het jaar. Jaargrens-waarden worden gereconstrueerd uit de transacties en de
    koershistoriek; ontbreekt een grens-koers, dan blijft het rendement leeg
    (`complete=False`) i.p.v. een misleidend cijfer te tonen.
    """
    if today is None:
        today = date.today()

    securities = list(
        db.scalars(select(Security).where(Security.owner_context_id == context.id))
    )
    if not securities:
        return []
    by_security, splits_by_security, prices_by_security = _load_tx_history(
        db, [s.id for s in securities]
    )
    if not any(by_security.values()):
        return []

    first_year = min(tx.date.year for txns in by_security.values() for tx in txns)

    results: list[YearReturnOut] = []
    for year in range(first_year, today.year + 1):
        period_start = date(year, 1, 1)
        is_current = year == today.year
        period_end = today if is_current else date(year, 12, 31)

        start_value, start_complete = _value_as_of(
            date(year - 1, 12, 31),
            securities,
            by_security,
            splits_by_security,
            prices_by_security,
            allow_stale=False,
        )
        end_value, end_complete = _value_as_of(
            period_end,
            securities,
            by_security,
            splits_by_security,
            prices_by_security,
            allow_stale=is_current,  # lopend jaar volgt de laatst gekende koers
        )

        days = (period_end - period_start).days
        net_flow = ZERO
        weighted_flow = ZERO
        for security in securities:
            for tx in by_security.get(security.id, []):
                if tx.date.year != year:
                    continue
                signed = tx.total if tx.side == SecuritySide.BUY else -tx.total
                net_flow += signed
                if days > 0:
                    elapsed = (tx.date - period_start).days
                    weighted_flow += signed * Decimal(days - elapsed) / Decimal(days)

        avg_capital = start_value + weighted_flow
        complete = start_complete and end_complete and avg_capital != ZERO
        return_pct = (
            float((end_value - start_value - net_flow) / avg_capital * 100)
            if complete
            else None
        )
        results.append(
            YearReturnOut(
                year=year,
                return_pct=return_pct,
                start_value_cents=to_cents(start_value),
                end_value_cents=to_cents(end_value),
                net_flow_cents=to_cents(net_flow),
                complete=complete,
            )
        )
    return results
