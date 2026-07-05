"""Dashboardlogica (spec §4/§9): budget vs. werkelijk per context per maand.

Werkelijke bedragen komen uit transactions (app-conventie: + = inkomen,
− = uitgave) en worden hier omgezet naar een positieve grootte binnen het
type, zodat ze naast het (positieve) budget gelegd kunnen worden. Interne
overschrijvingen tellen niet mee. Een transactie telt in de maand van haar
effective_date (budgetmaand), niet per se de uitvoeringsdatum — zoals in de
Excel, waar loon van eind december voor januari telt.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Context, Transaction
from app.models.enums import CategoryType
from app.schemas.dashboard import CategoryStatus, DashboardOut, TypeTotal
from app.services.budget import TYPE_ORDER, ZERO, compute_tba, to_cents


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _actual_magnitude(tx_type: CategoryType, amount: Decimal) -> Decimal:
    """+ = inkomen, − = uitgave; binnen Uitgaven/Sparen is 'werkelijk' dus −bedrag."""
    return amount if tx_type == CategoryType.INKOMEN else -amount


def build_dashboard(db: Session, context: Context, year: int, month: int) -> DashboardOut:
    categories = db.scalars(
        select(Category)
        .where(Category.context_id == context.id, Category.active)
        .order_by(Category.sort_order, Category.id)
    ).all()

    budget_rows = db.scalars(
        select(Budget)
        .join(Category, Budget.category_id == Category.id)
        .where(Category.context_id == context.id, Budget.year == year, Budget.month == month)
    ).all()
    budget_per_category = {row.category_id: row.amount for row in budget_rows}

    start, end = _month_bounds(year, month)
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.context_id == context.id,
            Transaction.effective_date >= start,
            Transaction.effective_date < end,
            Transaction.is_internal_transfer.is_(False),
        )
    ).all()

    actual_per_category: dict[int, Decimal] = {}
    actual_per_type: dict[CategoryType, Decimal] = dict.fromkeys(TYPE_ORDER, ZERO)
    uncategorized = 0
    for tx in transactions:
        magnitude = _actual_magnitude(tx.type, tx.amount)
        actual_per_type[tx.type] += magnitude
        if tx.category_id is None:
            uncategorized += 1
        else:
            actual_per_category[tx.category_id] = (
                actual_per_category.get(tx.category_id, ZERO) + magnitude
            )

    budget_per_type: dict[CategoryType, Decimal] = dict.fromkeys(TYPE_ORDER, ZERO)
    category_rows: list[CategoryStatus] = []
    for category in categories:
        budget = budget_per_category.get(category.id, ZERO)
        budget_per_type[category.type] += budget
        category_rows.append(
            CategoryStatus(
                category_id=category.id,
                name=category.name,
                type=category.type,
                budget_cents=to_cents(budget),
                actual_cents=to_cents(actual_per_category.get(category.id, ZERO)),
            )
        )

    tba = compute_tba(
        budget_per_type[CategoryType.INKOMEN],
        budget_per_type[CategoryType.UITGAVEN],
        budget_per_type[CategoryType.SPAREN],
    )
    return DashboardOut(
        context_id=context.id,
        year=year,
        month=month,
        to_be_allocated_cents=to_cents(tba),
        type_totals=[
            TypeTotal(
                type=cat_type,
                budget_cents=to_cents(budget_per_type[cat_type]),
                actual_cents=to_cents(actual_per_type[cat_type]),
            )
            for cat_type in TYPE_ORDER
        ],
        categories=category_rows,
        uncategorized_count=uncategorized,
    )
