"""Beleggingen-schemas (spec §7).

Twee soorten getallen over de draad:
- **Geld** als integer-centen (waarde, kostprijs, winst/verlies) — zoals overal.
- **Hoeveelheden/koersen** als exacte Decimal-**string** (fractionele aandelen,
  prijs per stuk, gemiddelde aankoopprijs met 6 decimalen) — nooit als float.
"""

from datetime import date

from pydantic import BaseModel

from app.models.enums import SecuritySide


class SecurityIn(BaseModel):
    name: str
    ticker: str | None = None
    isin: str | None = None
    owner_context_id: int


class SecurityOut(BaseModel):
    id: int
    name: str
    ticker: str | None
    isin: str | None
    owner_context_id: int
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


class PortfolioOut(BaseModel):
    context_id: int
    positions: list[PositionOut]
    total_value_cents: int
    total_cost_cents: int
    total_gain_cents: int
    total_gain_pct: float | None
    realized_gains: list[RealizedGainOut]
    realized_by_year: list[RealizedYearOut]
