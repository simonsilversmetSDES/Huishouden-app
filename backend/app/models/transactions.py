from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    Bank,
    Categorization,
    CategoryType,
    MatchField,
    MatchType,
    TransactionSource,
    str_enum,
)
from app.types import MoneyCents


def _default_effective_date(context: Any) -> date:
    """Zonder expliciete effective_date geldt de transactiedatum zelf."""
    return context.get_current_parameters()["date"]


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    bank: Mapped[Bank] = mapped_column(str_enum(Bank, "bank"))
    imported_at: Mapped[datetime] = mapped_column(DateTime)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # Budgetmaand-datum (Excel "Effective Date"): loon van eind december telt
    # voor januari. Default gelijk aan date; het dashboard rekent hierop.
    effective_date: Mapped[date] = mapped_column(Date, index=True, default=_default_effective_date)
    amount: Mapped[Decimal] = mapped_column(MoneyCents)  # + = inkomen, − = uitgave
    type: Mapped[CategoryType] = mapped_column(str_enum(CategoryType, "category_type"))
    counterparty_name: Mapped[str | None] = mapped_column(String)
    counterparty_iban: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    source: Mapped[TransactionSource] = mapped_column(
        str_enum(TransactionSource, "transaction_source"), default=TransactionSource.MANUAL
    )
    import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id"))
    import_hash: Mapped[str | None] = mapped_column(String, unique=True)
    categorization: Mapped[Categorization] = mapped_column(
        str_enum(Categorization, "categorization"), default=Categorization.UNCATEGORIZED
    )
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, default=False)


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    match_field: Mapped[MatchField] = mapped_column(str_enum(MatchField, "match_field"))
    match_type: Mapped[MatchType] = mapped_column(str_enum(MatchType, "match_type"))
    match_value: Mapped[str] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    created_from_correction: Mapped[bool] = mapped_column(Boolean, default=False)


class RuleContext(Base):
    """Op welke entiteiten een categorisatieregel van toepassing is (spec §5.3, #9).

    Bron van waarheid voor de 'geldt voor'-set. Een regel zonder rijen hier valt terug
    op zijn eigen `CategorizationRule.context_id` (backward compat)."""

    __tablename__ = "rule_contexts"

    rule_id: Mapped[int] = mapped_column(ForeignKey("categorization_rules.id"), primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"), primary_key=True)
