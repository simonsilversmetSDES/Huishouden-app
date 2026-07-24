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
from datetime import date, datetime, timedelta
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
            price_local, currency, prev_close = _fetch_one(yfinance, security.ticker, today)
            rate = None
            if currency and currency.upper() != "EUR":
                rate = _fx_rate(yfinance, currency.upper(), fx_cache)
            price = to_eur(price_local, currency, rate)
        except Exception:  # best effort per ticker: netwerk/parse-fouten overslaan
            result.failed.append(security.ticker)
            continue
        # Dagbeweging in de noteringsmunt (geen wisselkoerseffect), zoals de broker:
        # (laatste koers − vorige slotkoers) / vorige slotkoers.
        if prev_close is not None and prev_close != Decimal("0"):
            security.day_change_pct = ((price_local / prev_close) - 1) * 100
        else:
            security.day_change_pct = None
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
            # NaN (lopende beursdag zonder slot) overslaan: Decimal('nan') > 0
            # gooit InvalidOperation en zou de hele ticker doen falen.
            if raw is None or raw != raw:
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


# Yahoo Finance-tijdsblokken voor de koersgrafiek: periode → (yfinance-period,
# interval). Intraday voor 1D/5D, dagkoersen voor de middellange blokken en
# week-/maandkoersen voor de lange trend — dezelfde verdichting als Yahoo zelf.
CHART_RANGES: dict[str, tuple[str, str]] = {
    "1d": ("1d", "1m"),
    "5d": ("5d", "5m"),
    "1mo": ("1mo", "1d"),
    "6mo": ("6mo", "1d"),
    "ytd": ("ytd", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
    "max": ("max", "1mo"),
}


@dataclass
class ChartPoint:
    t: datetime
    price: Decimal


@dataclass
class ChartHistory:
    currency: str | None
    prev_close: Decimal | None  # slotkoers vorige beursdag (referentielijn op 1D)
    points: list[ChartPoint]


def fetch_chart_history(ticker_symbol: str, chart_range: str) -> ChartHistory:
    """Koersreeks voor de grafiek-popup, live van Yahoo (niet gecachet).

    Bewust in de noteringsmunt van het effect — dit is dezelfde weergave als
    Yahoo Finance, geen waardeberekening in euro. yfinance wordt lui geïmporteerd
    zodat de tests geen netwerk raken.
    """
    import yfinance  # lui geïmporteerd: enkel nodig bij een echte fetch

    period, interval = CHART_RANGES[chart_range]
    ticker = yfinance.Ticker(ticker_symbol)
    fast_info = getattr(ticker, "fast_info", None)
    currency = fast_info.get("currency") if fast_info is not None else None
    raw_prev = fast_info.get("previousClose") if fast_info is not None else None
    prev_close = Decimal(str(raw_prev)).quantize(_SIX) if raw_prev is not None else None

    hist = ticker.history(period=period, interval=interval)
    points: list[ChartPoint] = []
    if hist is not None and not hist.empty:
        for timestamp, raw in hist["Close"].items():
            # NaN (nog geen slot voor dit interval) overslaan, zoals bij de backfill.
            if raw is None or raw != raw:
                continue
            price = Decimal(str(raw))
            if price > 0:
                points.append(ChartPoint(t=timestamp.to_pydatetime(), price=price.quantize(_SIX)))
    return ChartHistory(
        currency=currency if isinstance(currency, str) else None,
        prev_close=prev_close,
        points=points,
    )


def _daily_closes(ticker: object) -> list[tuple[date, Decimal]]:
    """Dagelijkse slotkoersen (oplopend, positief, NaN overgeslagen) uit de historiek.
    yfinance's fast_info['previousClose'] is onbetrouwbaar; de dagslotkoersen matchen
    wél de referentie die Bolero/Degiro voor de dagwinst gebruiken."""
    try:
        hist = ticker.history(period="5d", interval="1d")  # type: ignore[attr-defined]
    except Exception:
        return []
    out: list[tuple[date, Decimal]] = []
    if hist is not None and not hist.empty:
        for timestamp, raw in hist["Close"].items():
            if raw is None or raw != raw:  # NaN overslaan (Decimal('nan') > 0 gooit)
                continue
            value = Decimal(str(raw))
            if value > 0:
                out.append((timestamp.date(), value))
    return out


def _close_before(closes: list[tuple[date, Decimal]], ref: date) -> Decimal | None:
    """Laatste slotkoers met datum strikt vóór `ref` (closes is oplopend)."""
    prev: Decimal | None = None
    for day, value in closes:
        if day < ref:
            prev = value
    return prev


def _fetch_one(
    yfinance: object, ticker_symbol: str, today: date
) -> tuple[Decimal, str | None, Decimal | None]:
    """Actuele koers, munt én de vorige slotkoers — alle drie in de noteringsmunt.

    De referentie voor de dagwinst is de slotkoers van de sessie *vóór* de sessie van
    de huidige koers (niet 'vóór vandaag'): zo toont een gesloten beurs de laatste
    voltooide dagbeweging (zoals een broker in het weekend), i.p.v. 0 %. Bij een open
    beurs is de huidige koers de live intraday-koers en de referentie de vorige
    beursdag — dat matcht Bolero/Degiro. fast_info['previousClose'] wordt bewust
    genegeerd: dat veld zit structureel naast de echte vorige slotkoers."""
    ticker = yfinance.Ticker(ticker_symbol)  # type: ignore[attr-defined]
    fast_info = getattr(ticker, "fast_info", None)
    currency = fast_info.get("currency") if fast_info is not None else None
    live = fast_info.get("last_price") if fast_info is not None else None
    closes = _daily_closes(ticker)

    price: Decimal | None = None
    prev_close: Decimal | None = None
    if closes:
        last_day, last_close = closes[-1]
        if live is not None and last_day >= today:
            # Beurs handelt vandaag → live intraday-koers t.o.v. de vorige beursdag.
            price = Decimal(str(live))
            prev_close = _close_before(closes, today)
        else:
            # Beurs (nog) dicht vandaag → laatste voltooide sessie en de dag ervoor.
            price = last_close
            prev_close = _close_before(closes, last_day)
    if price is None:
        # Geen bruikbare historiek → val terug op de losse koers (dan geen dagwinst).
        raw = _last_price(ticker)
        if raw is None:
            raise ValueError("geen koers beschikbaar")
        price = Decimal(str(raw))
    if price <= 0:
        raise ValueError("koers is niet positief")
    return price, (currency if isinstance(currency, str) else None), prev_close
