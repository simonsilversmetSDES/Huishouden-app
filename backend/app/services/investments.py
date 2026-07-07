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
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, Security, SecurityPrice, SecurityTransaction
from app.models.enums import SecuritySide
from app.schemas.investments import (
    PortfolioOut,
    PositionOut,
    RealizedGainOut,
    RealizedYearOut,
)
from app.services.budget import to_cents

ZERO = Decimal("0")
SIX = Decimal("0.000001")


def _latest_prices(db: Session, security_ids: list[int]) -> dict[int, Decimal]:
    """Recentste koers per effect (op datum)."""
    latest: dict[int, Decimal] = {}
    for price in db.scalars(
        select(SecurityPrice)
        .where(SecurityPrice.security_id.in_(security_ids))
        .order_by(SecurityPrice.date)
    ):
        latest[price.security_id] = price.price  # oplopend gesorteerd → laatste wint
    return latest


def _pct(numerator: int, denominator: int) -> float | None:
    return float(Decimal(numerator) / Decimal(denominator) * 100) if denominator else None


def build_portfolio(db: Session, context: Context) -> PortfolioOut:
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

    realized: list[RealizedGainOut] = []
    computed: list[dict] = []
    total_value = 0
    total_cost = 0
    for security in securities:
        txns = by_security.get(security.id, [])
        buys = [t for t in txns if t.side == SecuritySide.BUY]
        sells = [t for t in txns if t.side == SecuritySide.SELL]
        shares_bought = sum((t.shares for t in buys), ZERO)
        total_bought = sum((t.total for t in buys), ZERO)
        shares_sold = sum((t.shares for t in sells), ZERO)
        net = shares_bought - shares_sold
        avg = (total_bought / shares_bought).quantize(SIX, ROUND_HALF_UP) if shares_bought else None

        cost_cents = to_cents(avg * net) if avg is not None else 0
        price = latest.get(security.id)
        value_cents = to_cents(price * net) if price is not None else None
        gain_cents = value_cents - cost_cents if value_cents is not None else None

        computed.append(
            {
                "s": security,
                "net": net,
                "avg": avg,
                "cost_cents": cost_cents,
                "price": price,
                "value_cents": value_cents,
                "gain_cents": gain_cents,
            }
        )
        total_cost += cost_cents
        if value_cents is not None:
            total_value += value_cents

        for sell in sells:
            if avg is None:
                continue
            proceeds_cents = to_cents(sell.price_per_share * sell.shares)
            cost_basis_cents = to_cents(avg * sell.shares)
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
    )
