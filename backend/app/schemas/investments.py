"""Beleggingen-schemas (spec §7).

Twee soorten getallen over de draad:
- **Geld** als integer-centen (waarde, kostprijs, winst/verlies) — zoals overal.
- **Hoeveelheden/koersen** als exacte Decimal-**string** (fractionele aandelen,
  prijs per stuk, gemiddelde aankoopprijs met 6 decimalen) — nooit als float.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import SecurityKind, SecuritySide


class SecurityIn(BaseModel):
    name: str
    ticker: str | None = None
    isin: str | None = None
    owner_context_id: int
    soort: SecurityKind = SecurityKind.ETF_FONDSEN
    is_benchmark: bool = False  # gebruik dit effect als referentie-index (spec §7-uitbreiding)


class SecurityOut(BaseModel):
    id: int
    name: str
    ticker: str | None
    isin: str | None
    owner_context_id: int
    soort: SecurityKind
    is_benchmark: bool
    suggested_ticker: str | None = None  # afgeleid uit de naam wanneer ticker leeg is


class SecuritySearchHit(BaseModel):
    symbol: str
    name: str | None
    exchange: str | None
    quote_type: str | None


class SecuritySplitIn(BaseModel):
    security_id: int
    date: date
    ratio: str  # bv. "25" voor een 25:1-split
    apply_to_other_contexts: bool = False  # zelfde split op hetzelfde effect bij anderen


class SecuritySplitOut(BaseModel):
    id: int
    security_id: int
    date: date
    ratio: str


class SecurityTransactionIn(BaseModel):
    security_id: int
    date: date
    side: SecuritySide
    shares: str  # exacte Decimal-string
    price_per_share: str
    fee: str = "0"
    tax: str = "0"


class SecurityTransactionOut(BaseModel):
    id: int
    security_id: int
    date: date
    side: SecuritySide
    shares: str
    price_per_share: str
    fee: str
    tax: str
    total: str


class SecurityPriceIn(BaseModel):
    security_id: int
    date: date
    price: str  # exacte Decimal-string


class SecurityPriceOut(BaseModel):
    id: int
    security_id: int
    date: date
    price: str
    source: str


class PricePointOut(BaseModel):
    t: datetime  # tijdstip van het interval (intraday) of de beursdag
    price: str  # exacte Decimal-string, in de noteringsmunt


class PriceHistoryOut(BaseModel):
    """Koersreeks voor de grafiek-popup (Yahoo-tijdsblokken), in noteringsmunt."""

    security_id: int
    ticker: str
    range: str  # één van CHART_RANGES (1d, 5d, 1mo, 6mo, ytd, 1y, 5y, max)
    currency: str | None
    prev_close: str | None  # slotkoers vorige beursdag (referentielijn op 1D)
    points: list[PricePointOut]


class PriceFetchResult(BaseModel):
    fetched: int
    failed: list[str]  # tickers/namen die niet opgehaald konden worden


class PositionOut(BaseModel):
    security_id: int
    name: str
    ticker: str | None
    shares: str
    avg_buy_price: str | None  # 6 decimalen; None als geen aankopen
    cost_cents: int  # kostbasis van de huidige positie (avg × aantal)
    current_price: str | None
    value_cents: int | None
    gain_cents: int | None
    gain_pct: float | None
    day_gain_cents: int | None  # (laatste koers − voorlaatste koers) × aantal
    day_gain_pct: float | None  # koersverandering t.o.v. de voorlaatste koersdag
    portfolio_pct: float


class RealizedGainOut(BaseModel):
    security_id: int
    name: str
    date: date
    shares: str
    proceeds_cents: int
    cost_basis_cents: int
    gain_cents: int
    year: int


class RealizedYearOut(BaseModel):
    year: int
    gain_cents: int


class YearReturnOut(BaseModel):
    """Rendement over één kalenderjaar (Modified Dietz)."""

    year: int
    return_pct: float | None  # None = onvoldoende koersdata om het jaar te waarderen
    start_value_cents: int  # portefeuillewaarde begin van het jaar
    end_value_cents: int  # waarde einde jaar (of huidige waarde voor het lopende jaar)
    net_flow_cents: int  # netto in-/uitstroom: + = bijgestort, − = onttrokken
    complete: bool  # False → return_pct is None wegens ontbrekende jaargrens-koers


class BenchmarkYearOut(BaseModel):
    """Koersrendement (geen Modified Dietz) van de referentie-index over één jaar."""

    year: int
    return_pct: float | None  # None = geen jaargrens-koers binnen tolerantie
    complete: bool


class BenchmarkOut(BaseModel):
    security_id: int
    name: str  # naam van het effect dat als referentie-index is gemarkeerd
    years: list[BenchmarkYearOut]


class PortfolioOut(BaseModel):
    context_id: int
    positions: list[PositionOut]
    total_value_cents: int
    total_cost_cents: int
    total_gain_cents: int
    total_gain_pct: float | None
    realized_gains: list[RealizedGainOut]
    realized_by_year: list[RealizedYearOut]
    yearly_returns: list[YearReturnOut]
    benchmark: BenchmarkOut | None = None
