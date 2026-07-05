from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.types import MoneyCents, PreciseDecimal


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    name: Mapped[str] = mapped_column(String)
    principal: Mapped[Decimal] = mapped_column(MoneyCents)
    annual_rate: Mapped[Decimal] = mapped_column(PreciseDecimal)  # bv. 0.0251 (2,51 %)
    term_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    monthly_payment: Mapped[Decimal] = mapped_column(MoneyCents)
    property_value_paid: Mapped[Decimal | None] = mapped_column(MoneyCents)
    property_value_estimate: Mapped[Decimal | None] = mapped_column(MoneyCents)


class LoanPayment(Base):
    __tablename__ = "loan_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MoneyCents)
    interest_part: Mapped[Decimal] = mapped_column(MoneyCents)
    principal_part: Mapped[Decimal] = mapped_column(MoneyCents)
    balance_after: Mapped[Decimal] = mapped_column(MoneyCents)
