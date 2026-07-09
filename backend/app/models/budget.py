from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.types import MoneyCents


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(MoneyCents)

    __table_args__ = (
        UniqueConstraint("category_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
    )


class BudgetNote(Base):
    """Excel-achtige celnotitie op een budgetcel (categorie × jaar × maand).

    Los van `budgets`: een notitie kan bestaan op een cel zonder bedrag."""

    __tablename__ = "budget_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("category_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="note_month_range"),
    )
