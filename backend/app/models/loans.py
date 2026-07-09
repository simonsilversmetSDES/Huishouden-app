from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.types import MoneyCents, PreciseDecimal


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    name: Mapped[str] = mapped_column(String)

    # Leningparameters (spec §8)
    principal: Mapped[Decimal] = mapped_column(MoneyCents)  # geleend bedrag
    annual_rate: Mapped[Decimal] = mapped_column(PreciseDecimal)  # bv. 0.0251 (2,51 %)
    term_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)  # datum eerste aflossing (bv. de 5e)
    # Maandlast: manueel ("af te lossen bedrag gekend") of None → berekend via annuïteit.
    monthly_payment: Mapped[Decimal | None] = mapped_column(MoneyCents)

    # Woningblok (spec §8)
    # betaalde prijs incl. kosten
    property_value_paid: Mapped[Decimal | None] = mapped_column(MoneyCents)
    # basiswaarde + jaar voor de indexatie, en de jaarlijkse indexatie (bv. 0.015)
    property_base_value: Mapped[Decimal | None] = mapped_column(MoneyCents)
    property_base_year: Mapped[int | None] = mapped_column(Integer)
    indexation_rate: Mapped[Decimal | None] = mapped_column(PreciseDecimal)

    investments: Mapped[list["PropertyInvestment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )
    contributions: Mapped[list["LoanContribution"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )


class PropertyInvestment(Base):
    """Investering aan de woning die meerwaarde toevoegt (spec §8), bv. keuken."""

    __tablename__ = "property_investments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    label: Mapped[str] = mapped_column(String)
    # Vrije toelichting, bv. "50% van de aankoopprijs van de keuken".
    comment: Mapped[str | None] = mapped_column(String)
    added_value: Mapped[Decimal] = mapped_column(MoneyCents)  # toegevoegde meerwaarde

    loan: Mapped[Loan] = relationship(back_populates="investments")


class LoanContribution(Base):
    """Eigen inbreng per persoon (context) bij de aankoop (spec §8)."""

    __tablename__ = "loan_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    amount: Mapped[Decimal] = mapped_column(MoneyCents)

    loan: Mapped[Loan] = relationship(back_populates="contributions")


class LoanPayment(Base):
    """Optioneel: gelogde werkelijke betaling (de aflossingstabel zelf wordt berekend)."""

    __tablename__ = "loan_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MoneyCents)
    interest_part: Mapped[Decimal] = mapped_column(MoneyCents)
    principal_part: Mapped[Decimal] = mapped_column(MoneyCents)
    balance_after: Mapped[Decimal] = mapped_column(MoneyCents)
