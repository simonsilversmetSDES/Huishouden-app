from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonthNote(Base):
    """Vrije-tekstnotitie op een dashboardmaand (context × jaar × maand).

    Eén notitie per maand, los van budget/transacties. Analoog aan budget_notes,
    maar op het niveau van de maand als geheel i.p.v. een budgetcel."""

    __tablename__ = "month_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("context_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_note_month_range"),
    )
