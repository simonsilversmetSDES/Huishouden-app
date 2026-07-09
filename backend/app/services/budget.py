"""Budgetlogica (spec §4): TBA-berekening, budgetmatrix per context/jaar en upsert.

Alle rekenwerk in Decimal (harde regel: nooit float voor geld); centen enkel
aan de API-rand.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, BudgetNote, Category, Context
from app.models.enums import CategoryType
from app.schemas.budget import (
    BudgetCategoryRow,
    BudgetCellIn,
    BudgetMatrixOut,
    BudgetNoteIn,
    BudgetTypeGroup,
)

TYPE_ORDER = [CategoryType.INKOMEN, CategoryType.UITGAVEN, CategoryType.SPAREN]

ZERO = Decimal("0")


class UnknownCategoryError(ValueError):
    """Upsert verwijst naar een categorie-id dat niet bestaat."""


def compute_tba(income: Decimal, expenses: Decimal, savings: Decimal) -> Decimal:
    """'To be allocated' = Σ Inkomen − Σ Uitgaven − Σ Sparen (mag negatief)."""
    return income - expenses - savings


def to_cents(amount: Decimal) -> int:
    return int(amount * 100)


def from_cents(cents: int) -> Decimal:
    return Decimal(cents) / 100


def build_matrix(db: Session, context: Context, year: int) -> BudgetMatrixOut:
    """Budgetmatrix categorieën × 12 maanden, gegroepeerd per type, met TBA-rij."""
    categories = db.scalars(
        select(Category)
        .where(Category.context_id == context.id, Category.active)
        .order_by(Category.sort_order, Category.id)
    ).all()
    budget_rows = db.scalars(
        select(Budget)
        .join(Category, Budget.category_id == Category.id)
        .where(Category.context_id == context.id, Budget.year == year)
    ).all()
    note_rows = db.scalars(
        select(BudgetNote)
        .join(Category, BudgetNote.category_id == Category.id)
        .where(Category.context_id == context.id, BudgetNote.year == year)
    ).all()

    per_category: dict[int, list[Decimal]] = {c.id: [ZERO] * 12 for c in categories}
    for row in budget_rows:
        if row.category_id in per_category:
            per_category[row.category_id][row.month - 1] = row.amount
    notes_per_category: dict[int, list[str | None]] = {c.id: [None] * 12 for c in categories}
    for note in note_rows:
        if note.category_id in notes_per_category:
            notes_per_category[note.category_id][note.month - 1] = note.note

    groups: list[BudgetTypeGroup] = []
    type_month_totals: dict[CategoryType, list[Decimal]] = {}
    for cat_type in TYPE_ORDER:
        month_totals = [ZERO] * 12
        rows: list[BudgetCategoryRow] = []
        for category in categories:
            if category.type != cat_type:
                continue
            months = per_category[category.id]
            for i, amount in enumerate(months):
                month_totals[i] += amount
            rows.append(
                BudgetCategoryRow(
                    category_id=category.id,
                    name=category.name,
                    month_cents=[to_cents(m) for m in months],
                    month_notes=notes_per_category[category.id],
                    total_cents=to_cents(sum(months, ZERO)),
                )
            )
        type_month_totals[cat_type] = month_totals
        groups.append(
            BudgetTypeGroup(
                type=cat_type,
                categories=rows,
                monthly_total_cents=[to_cents(m) for m in month_totals],
                total_cents=to_cents(sum(month_totals, ZERO)),
            )
        )

    tba = [
        compute_tba(
            type_month_totals[CategoryType.INKOMEN][i],
            type_month_totals[CategoryType.UITGAVEN][i],
            type_month_totals[CategoryType.SPAREN][i],
        )
        for i in range(12)
    ]
    return BudgetMatrixOut(
        context_id=context.id,
        year=year,
        groups=groups,
        to_be_allocated_cents=[to_cents(t) for t in tba],
        to_be_allocated_total_cents=to_cents(sum(tba, ZERO)),
    )


def upsert_budgets(db: Session, items: list[BudgetCellIn]) -> None:
    """Zet budgetcellen (categorie × jaar × maand); bestaande waarden worden overschreven."""
    known_ids = set(db.scalars(select(Category.id)).all())
    for item in items:
        if item.category_id not in known_ids:
            raise UnknownCategoryError(f"Onbekende categorie: {item.category_id}")
        existing = db.scalars(
            select(Budget).where(
                Budget.category_id == item.category_id,
                Budget.year == item.year,
                Budget.month == item.month,
            )
        ).one_or_none()
        amount = from_cents(item.amount_cents)
        if existing is None:
            db.add(
                Budget(
                    category_id=item.category_id,
                    year=item.year,
                    month=item.month,
                    amount=amount,
                )
            )
        else:
            existing.amount = amount
    db.commit()


def upsert_note(db: Session, item: BudgetNoteIn) -> None:
    """Zet of wist een celnotitie (lege/witruimte-notitie = verwijderen)."""
    if db.get(Category, item.category_id) is None:
        raise UnknownCategoryError(f"Onbekende categorie: {item.category_id}")
    existing = db.scalars(
        select(BudgetNote).where(
            BudgetNote.category_id == item.category_id,
            BudgetNote.year == item.year,
            BudgetNote.month == item.month,
        )
    ).one_or_none()
    text = item.note.strip()
    if text == "":
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(
            BudgetNote(category_id=item.category_id, year=item.year, month=item.month, note=text)
        )
    else:
        existing.note = text
    db.commit()
