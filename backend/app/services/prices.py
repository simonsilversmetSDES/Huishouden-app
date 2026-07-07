"""Koersen (spec §7): opslag + PriceProvider (manuele invoer én yfinance-fetch).

`security_prices` is de cache/historiek; de positieberekening gebruikt de recentste
koers per effect. Manuele invoer is de fallback voor fondsen zonder ticker en voor
de groepsverzekering. De yfinance-fetch is de enige externe call en is
uitschakelbaar via `price_fetch_enabled` (CLAUDE.md: geen externe calls behalve de
koersen-fetch). Koersen komen als float uit yfinance → altijd via Decimal(str(...))
(nooit float in PreciseDecimal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Security, SecurityPrice


@dataclass
class FetchResult:
    fetched: int = 0
    failed: list[str] = field(default_factory=list)


def upsert_price(
    db: Session, security_id: int, price_date: date, price: Decimal, source: str = "manual"
) -> SecurityPrice:
    """Koers zetten of bijwerken (UNIQUE(security_id, date)); caller commit."""
    existing = db.scalars(
        select(SecurityPrice).where(
            SecurityPrice.security_id == security_id,
            SecurityPrice.date == price_date,
        )
    ).one_or_none()
    if existing is None:
        existing = SecurityPrice(
            security_id=security_id, date=price_date, price=price, source=source
        )
        db.add(existing)
    else:
        existing.price = price
        existing.source = source
    return existing


def fetch_prices(db: Session, securities: list[Security], today: date) -> FetchResult:
    """Actuele koers per effect met ticker ophalen via yfinance en cachen.

    yfinance wordt lui geïmporteerd zodat de rest van de app niet van de
    dependency afhangt en de tests geen netwerk raken. De caller commit.
    """
    import yfinance  # lui geïmporteerd: enkel nodig bij een echte fetch

    result = FetchResult()
    for security in securities:
        if not security.ticker:
            continue
        try:
            price = _fetch_one(yfinance, security.ticker)
        except Exception:  # best effort per ticker: netwerk/parse-fouten overslaan
            result.failed.append(security.ticker)
            continue
        upsert_price(db, security.id, today, price, source="yfinance")
        result.fetched += 1
    return result


def _fetch_one(yfinance: object, ticker_symbol: str) -> Decimal:
    ticker = yfinance.Ticker(ticker_symbol)  # type: ignore[attr-defined]
    raw = None
    fast_info = getattr(ticker, "fast_info", None)
    if fast_info is not None:
        raw = fast_info.get("last_price")
    if raw is None:
        history = ticker.history(period="1d")
        raw = None if history.empty else history["Close"].iloc[-1]
    if raw is None:
        raise ValueError("geen koers beschikbaar")
    price = Decimal(str(raw))
    if price <= 0:
        raise ValueError("koers is niet positief")
    return price
