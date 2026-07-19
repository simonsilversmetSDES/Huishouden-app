"""Dashboardlogica (spec §4/§9): budget vs. werkelijk per context, per maand of jaar.

Werkelijke bedragen komen uit transactions (app-conventie: + = inkomen,
− = uitgave) en worden hier omgezet naar een positieve grootte binnen het
type, zodat ze naast het (positieve) budget gelegd kunnen worden. Interne
overschrijvingen tellen niet mee. Een transactie telt in de maand van haar
effective_date (budgetmaand) — zoals in de Excel, waar loon van eind
december voor januari telt.

Periode: een losse maand (`month`), year-to-date (`month_to`: maanden
1..month_to) of het hele jaar (beide None → "Total Year" in de oude Excel).
Bij YTD tellen budget én werkelijk enkel de maanden t/m month_to, zodat de
vergelijking eerlijk blijft (het volledige jaarbudget naast enkel de reeds
verstreken maanden gaf een scheef beeld). Het antwoord bevat altijd de 12
maandtotalen per type, voor de staafgrafiek.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Context, Transaction
from app.models.enums import CategoryType
from app.schemas.dashboard import CategoryStatus, DashboardOut, MonthTotals, TypeTotal
from app.services.budget import TYPE_ORDER, ZERO, compute_tba, to_cents


def _actual_magnitude(tx_type: CategoryType, amount: Decimal) -> Decimal:
    """+ = inkomen, − = uitgave; binnen Uitgaven/Sparen is 'werkelijk' dus −bedrag."""
    return amount if tx_type == CategoryType.INKOMEN else -amount


def build_dashboard(
    db: Session,
    context: Context,
    year: int,
    month: int | None = None,
    month_to: int | None = None,
) -> DashboardOut:
    categories = db.scalars(
        select(Category)
        .where(Category.context_id == context.id, Category.active)
        .order_by(Category.sort_order, Category.id)
    ).all()
    type_of = {c.id: c.type for c in categories}

    # Volledig jaar ophalen; de periode-filter (maand of jaar) gebeurt in Python.
    budget_rows = db.scalars(
        select(Budget)
        .join(Category, Budget.category_id == Category.id)
        .where(Category.context_id == context.id, Budget.year == year)
    ).all()
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.context_id == context.id,
            Transaction.effective_date >= date(year, 1, 1),
            Transaction.effective_date < date(year + 1, 1, 1),
            Transaction.is_internal_transfer.is_(False),
        )
    ).all()

    # Periode-venster [lo, hi] (incl.): losse maand, YTD (1..month_to) of heel jaar.
    if month is not None:
        lo = hi = month
    elif month_to is not None:
        lo, hi = 1, month_to
    else:
        lo, hi = 1, 12

    def in_period(m: int) -> bool:
        return lo <= m <= hi

    monthly_budget: dict[int, dict[CategoryType, Decimal]] = {
        m: dict.fromkeys(TYPE_ORDER, ZERO) for m in range(1, 13)
    }
    monthly_actual: dict[int, dict[CategoryType, Decimal]] = {
        m: dict.fromkeys(TYPE_ORDER, ZERO) for m in range(1, 13)
    }

    budget_per_category: dict[int, Decimal] = {}
    for row in budget_rows:
        # Budgetten van gedeactiveerde categorieën stil overslaan, net als de
        # budgetmatrix (services/budget.py): ze horen niet in de totalen of TBA.
        if row.category_id not in type_of:
            continue
        monthly_budget[row.month][type_of[row.category_id]] += row.amount
        if in_period(row.month):
            budget_per_category[row.category_id] = (
                budget_per_category.get(row.category_id, ZERO) + row.amount
            )

    actual_per_category: dict[int, Decimal] = {}
    uncategorized = 0
    for tx in transactions:
        magnitude = _actual_magnitude(tx.type, tx.amount)
        monthly_actual[tx.effective_date.month][tx.type] += magnitude
        if not in_period(tx.effective_date.month):
            continue
        if tx.category_id is None:
            uncategorized += 1
        else:
            actual_per_category[tx.category_id] = (
                actual_per_category.get(tx.category_id, ZERO) + magnitude
            )

    budget_per_type: dict[CategoryType, Decimal] = dict.fromkeys(TYPE_ORDER, ZERO)
    actual_per_type: dict[CategoryType, Decimal] = dict.fromkeys(TYPE_ORDER, ZERO)
    for m in range(1, 13):
        if not in_period(m):
            continue
        for cat_type in TYPE_ORDER:
            budget_per_type[cat_type] += monthly_budget[m][cat_type]
            actual_per_type[cat_type] += monthly_actual[m][cat_type]

    category_rows = [
        CategoryStatus(
            category_id=category.id,
            name=category.name,
            type=category.type,
            budget_cents=to_cents(budget_per_category.get(category.id, ZERO)),
            actual_cents=to_cents(actual_per_category.get(category.id, ZERO)),
        )
        for category in categories
    ]

    tba = compute_tba(
        budget_per_type[CategoryType.INKOMEN],
        budget_per_type[CategoryType.UITGAVEN],
        budget_per_type[CategoryType.SPAREN],
    )
    return DashboardOut(
        context_id=context.id,
        year=year,
        month=month,
        month_to=month_to,
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
        months=[
            MonthTotals(
                month=m,
                totals=[
                    TypeTotal(
                        type=cat_type,
                        budget_cents=to_cents(monthly_budget[m][cat_type]),
                        actual_cents=to_cents(monthly_actual[m][cat_type]),
                    )
                    for cat_type in TYPE_ORDER
                ],
            )
            for m in range(1, 13)
        ],
    )
