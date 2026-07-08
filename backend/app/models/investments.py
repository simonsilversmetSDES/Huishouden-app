from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import SecurityKind, SecuritySide, str_enum
from app.types import PreciseDecimal


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    ticker: Mapped[str | None] = mapped_column(String)  # fondsen zonder ticker: manuele koers
    isin: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="EUR")
    owner_context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    # Soort belegging → voedt de juiste activaklasse in de vermogensbalans (spec §9).
    soort: Mapped[SecurityKind] = mapped_column(
        str_enum(SecurityKind, "security_kind"), default=SecurityKind.ETF_FONDSEN
    )


class SecurityTransaction(Base):
    __tablename__ = "security_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[date] = mapped_column(Date)
    side: Mapped[SecuritySide] = mapped_column(str_enum(SecuritySide, "security_side"))
    shares: Mapped[Decimal] = mapped_column(PreciseDecimal)  # fractioneel (bv. 0,013013 BTC)
    price_per_share: Mapped[Decimal] = mapped_column(PreciseDecimal)
    # Exacte Decimal (niet centen): de beurstaks (TOB) is sub-cent (bv. 0,259044),
    # en de gemiddelde aankoopprijs (§10 = € 98,240055) vereist die precisie.
    fee: Mapped[Decimal] = mapped_column(PreciseDecimal, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(PreciseDecimal, default=Decimal("0"))  # beurstaks (TOB)
    total: Mapped[Decimal] = mapped_column(PreciseDecimal)  # shares*price ± kosten/taks


class SecurityPrice(Base):
    __tablename__ = "security_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(PreciseDecimal)
    source: Mapped[str] = mapped_column(String, default="manual")  # 'yfinance' | 'manual'

    __table_args__ = (UniqueConstraint("security_id", "date"),)


class SecuritySplit(Base):
    """Aandelensplitsing: transacties vóór `date` krijgen aantal × ratio en
    prijs ÷ ratio (bv. ratio 25 = een 25:1-split)."""

    __tablename__ = "security_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[date] = mapped_column(Date)
    ratio: Mapped[Decimal] = mapped_column(PreciseDecimal)

    __table_args__ = (UniqueConstraint("security_id", "date"),)
