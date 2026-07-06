"""Transactielogica (spec §5.1): manuele invoer en lijst met filters.

Tekenconventie identiek aan de Excel-import: signed = magnitude voor Inkomen,
−magnitude voor Uitgaven/Sparen. Alle rekenwerk in Decimal (nooit float);
centen enkel aan de API-rand via to_cents/from_cents.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Context, Transaction
from app.models.enums import Categorization, CategoryType, TransactionSource
from app.schemas.transactions import TransactionIn, TransactionOut
from app.services.budget import from_cents, to_cents


class UnknownCategoryError(ValueError):
    """De categorie bestaat niet of hoort bij een andere context."""


class CategoryTypeMismatchError(ValueError):
    """Het type van de categorie komt niet overeen met dat van de transactie."""


def _signed_amount(tx_type: CategoryType, magnitude_cents: int) -> Decimal:
    magnitude = from_cents(magnitude_cents)
    return magnitude if tx_type == CategoryType.INKOMEN else -magnitude


def _resolve_category(
    db: Session, context_id: int, tx_type: CategoryType, category_id: int | None
) -> Category | None:
    if category_id is None:
        return None
    category = db.get(Category, category_id)
    if category is None or category.context_id != context_id:
        raise UnknownCategoryError("Onbekende categorie voor deze context")
    if category.type != tx_type:
        raise CategoryTypeMismatchError(
            f"Categorie '{category.name}' is van type {category.type}, niet {tx_type}"
        )
    return category


def _apply_body(tx: Transaction, body: TransactionIn, category: Category | None) -> None:
    tx.date = body.date
    tx.effective_date = body.effective_date or body.date
    tx.type = body.type
    tx.amount = _signed_amount(body.type, body.amount_cents)
    tx.category_id = category.id if category else None
    tx.description = body.description
    tx.categorization = Categorization.MANUAL if category else Categorization.UNCATEGORIZED


def create_transaction(db: Session, body: TransactionIn) -> Transaction:
    category = _resolve_category(db, body.context_id, body.type, body.category_id)
    tx = Transaction(context_id=body.context_id, source=TransactionSource.MANUAL)
    _apply_body(tx, body, category)
    db.add(tx)
    db.commit()
    return tx


def list_transactions(
    db: Session,
    context: Context,
    year: int,
    month: int | None = None,
    type_: CategoryType | None = None,
    category_id: int | None = None,
) -> list[TransactionOut]:
    """Transacties in de budgetperiode (effective_date, zoals het dashboard)."""
    if month is None:
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    else:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    query = select(Transaction).where(
        Transaction.context_id == context.id,
        Transaction.effective_date >= start,
        Transaction.effective_date < end,
    )
    if type_ is not None:
        query = query.where(Transaction.type == type_)
    if category_id is not None:
        query = query.where(Transaction.category_id == category_id)
    rows = db.scalars(
        query.order_by(
            Transaction.effective_date.desc(), Transaction.date.desc(), Transaction.id.desc()
        )
    ).all()

    # Geen relationships op Transaction — categorienamen via één losse query.
    names = dict(
        db.execute(
            select(Category.id, Category.name).where(Category.context_id == context.id)
        ).all()
    )
    return [to_out(tx, names.get(tx.category_id)) for tx in rows]


def to_out(tx: Transaction, category_name: str | None) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        context_id=tx.context_id,
        date=tx.date,
        effective_date=tx.effective_date,
        type=tx.type,
        amount_cents=to_cents(tx.amount),
        category_id=tx.category_id,
        category_name=category_name,
        description=tx.description,
        source=tx.source,
        is_internal_transfer=tx.is_internal_transfer,
    )
