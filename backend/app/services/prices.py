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
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Security, SecurityPrice


@dataclass
class FetchResult:
    fetched: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class BackfillResult:
    fetched: int = 0  # totaal geschreven koersrijen
    per_security: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)  # tickers zonder bruikbare historiek
    skipped: list[str] = field(default_factory=list)  # effecten zonder ticker


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


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """Yahoo-symbolen zoeken via yfinance (externe call). Best effort → [] bij fout."""
    import yfinance  # lui geïmporteerd

    try:
        quotes = yfinance.Search(query, max_results=limit).quotes
    except Exception:
        return []
    hits: list[dict] = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol:
            continue
        hits.append(
            {
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname"),
                "exchange": q.get("exchange"),
                "quote_type": q.get("quoteType"),
            }
        )
    return hits


_SIX = Decimal("0.000001")


def to_eur(price: Decimal, currency: str | None, rate: Decimal | None) -> Decimal:
    """Koers omrekenen naar euro. EUR (of onbekend) blijft ongewijzigd; anders
    price × wisselkoers (rate = euro per eenheid vreemde valuta). Transacties worden
    in euro ingevoerd, dus de waarde/rendement moet ook in euro staan."""
    if not currency or currency.upper() == "EUR":
        return price
    if rate is None:
        raise ValueError(f"geen wisselkoers voor {currency}")
    return (price * rate).quantize(_SIX)


def fetch_prices(db: Session, securities: list[Security], today: date) -> FetchResult:
    """Actuele koers per effect met ticker ophalen via yfinance, naar euro
    omrekenen en cachen.

    yfinance wordt lui geïmporteerd zodat de rest van de app niet van de
    dependency afhangt en de tests geen netwerk raken. De caller commit.
    """
    import yfinance  # lui geïmporteerd: enkel nodig bij een echte fetch

    result = FetchResult()
    fx_cache: dict[str, Decimal | None] = {}
    for security in securities:
        if not security.ticker:
            continue
        try:
            price, currency = _fetch_one(yfinance, security.ticker)
            rate = None
            if currency and currency.upper() != "EUR":
                rate = _fx_rate(yfinance, currency.upper(), fx_cache)
            price = to_eur(price, currency, rate)
        except Exception:  # best effort per ticker: netwerk/parse-fouten overslaan
            result.failed.append(security.ticker)
            continue
        security.currency = "EUR"  # opgeslagen koers is altijd in euro
        upsert_price(db, security.id, today, price, source="yfinance")
        result.fetched += 1
    return result


def _fx_rate(yfinance: object, currency: str, cache: dict[str, Decimal | None]) -> Decimal | None:
    """Wisselkoers (euro per eenheid `currency`) via bv. USDEUR=X; None bij fout."""
    if currency in cache:
        return cache[currency]
    rate: Decimal | None = None
    try:
        raw = _last_price(yfinance.Ticker(f"{currency}EUR=X"))  # type: ignore[attr-defined]
        rate = Decimal(str(raw)) if raw is not None else None
    except Exception:
        rate = None
    cache[currency] = rate
    return rate


def _last_price(ticker: object) -> object | None:
    fast_info = getattr(ticker, "fast_info", None)
    raw = fast_info.get("last_price") if fast_info is not None else None
    if raw is None:
        history = ticker.history(period="1d")  # type: ignore[attr-defined]
        raw = None if history.empty else history["Close"].iloc[-1]
    return raw


def _nearest_rate(fx: dict[date, Decimal], on: date) -> Decimal | None:
    """Meest recente wisselkoers op of vóór `on` (weekends/feestdagen hebben geen
    Yahoo-notering, dus terugvallen op de vorige beursdag)."""
    best: Decimal | None = None
    for rate_date in sorted(fx):
        if rate_date <= on:
            best = fx[rate_date]
        else:
            break
    return best


def _fetch_history_one(
    yfinance: object, ticker_symbol: str, start: date, end: date
) -> tuple[dict[date, Decimal], str | None]:
    """Dagelijkse slotkoersen [start, end] voor één ticker + de munt ervan."""
    ticker = yfinance.Ticker(ticker_symbol)  # type: ignore[attr-defined]
    fast_info = getattr(ticker, "fast_info", None)
    currency = fast_info.get("currency") if fast_info is not None else None
    hist = ticker.history(  # type: ignore[attr-defined]
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), interval="1d"
    )
    closes: dict[date, Decimal] = {}
    if hist is not None and not hist.empty:
        for timestamp, raw in hist["Close"].items():
            if raw is None:
                continue
            price = Decimal(str(raw))
            if price > 0:
                closes[timestamp.date()] = price
    return closes, (currency if isinstance(currency, str) else None)


def _fx_history(
    yfinance: object,
    currency: str,
    start: date,
    end: date,
    cache: dict[str, dict[date, Decimal]],
) -> dict[date, Decimal]:
    """Historiek van de wisselkoers (euro per eenheid `currency`), bv. USDEUR=X."""
    if currency in cache:
        return cache[currency]
    rates: dict[date, Decimal] = {}
    try:
        closes, _ = _fetch_history_one(yfinance, f"{currency}EUR=X", start, end)
        rates = closes
    except Exception:
        rates = {}
    cache[currency] = rates
    return rates


def fetch_price_history(
    db: Session,
    securities: list[Security],
    start_by_security: dict[int, date],
    today: date,
) -> BackfillResult:
    """Historische dagkoersen ophalen en cachen (spec §7), per beursdag naar euro
    omgerekend met de wisselkoers van diezelfde dag. Eenmalige backfill zodat o.a.
    het jaarrendement en historische grafieken echte cijfers krijgen.

    Best effort per ticker; de caller commit. yfinance wordt lui geïmporteerd zodat
    de tests geen netwerk raken.
    """
    import yfinance  # lui geïmporteerd: enkel nodig bij een echte fetch

    result = BackfillResult()
    fx_cache: dict[str, dict[date, Decimal]] = {}
    for security in securities:
        if not security.ticker:
            result.skipped.append(security.name)
            continue
        start = start_by_security.get(security.id)
        if start is None:
            continue
        try:
            closes, currency = _fetch_history_one(yfinance, security.ticker, start, today)
        except Exception:
            result.failed.append(security.ticker)
            continue
        if not closes:
            result.failed.append(security.ticker)
            continue

        fx: dict[date, Decimal] | None = None
        if currency and currency.upper() != "EUR":
            fx = _fx_history(yfinance, currency.upper(), start, today, fx_cache)
            if not fx:
                result.failed.append(security.ticker)
                continue

        written = 0
        for price_date, close in closes.items():
            price = close
            if fx is not None:
                rate = _nearest_rate(fx, price_date)
                if rate is None:
                    continue  # geen wisselkoers vóór deze datum → koers overslaan
                price = to_eur(close, currency, rate)
            upsert_price(db, security.id, price_date, price, source="yfinance")
            written += 1
        if currency:
            security.currency = "EUR"  # opgeslagen koers is altijd in euro
        result.fetched += written
        result.per_security[security.name] = written
    return result


def _fetch_one(yfinance: object, ticker_symbol: str) -> tuple[Decimal, str | None]:
    ticker = yfinance.Ticker(ticker_symbol)  # type: ignore[attr-defined]
    fast_info = getattr(ticker, "fast_info", None)
    currency = fast_info.get("currency") if fast_info is not None else None
    raw = _last_price(ticker)
    if raw is None:
        raise ValueError("geen koers beschikbaar")
    price = Decimal(str(raw))
    if price <= 0:
        raise ValueError("koers is niet positief")
    return price, (currency if isinstance(currency, str) else None)
