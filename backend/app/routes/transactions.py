from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Category, Context, Transaction
from app.models.enums import CategoryType
from app.schemas.transactions import TransactionIn, TransactionOut
from app.services.transactions import (
    CategoryTypeMismatchError,
    ContextImmutableError,
    UnknownCategoryError,
    create_transaction,
    list_transactions,
    to_out,
    update_transaction,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=list[TransactionOut])
def list_transactions_route(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    type: CategoryType | None = None,
    category_id: int | None = None,
) -> list[TransactionOut]:
    context = _get_context(db, context_id)
    return list_transactions(db, context, year, month, type, category_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TransactionOut)
def create_transaction_route(
    body: TransactionIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> TransactionOut:
    _get_context(db, body.context_id)
    try:
        tx = create_transaction(db, body)
    except UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CategoryTypeMismatchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    category_name = None
    if tx.category_id is not None:
        category = db.get(Category, tx.category_id)
        category_name = category.name if category else None
    return to_out(tx, category_name)


def _get_transaction(db: Session, transaction_id: int) -> Transaction:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende transactie")
    return tx


@router.put("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_transaction_route(
    transaction_id: int,
    body: TransactionIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    tx = _get_transaction(db, transaction_id)
    try:
        update_transaction(db, tx, body)
    except UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (CategoryTypeMismatchError, ContextImmutableError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction_route(
    transaction_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    tx = _get_transaction(db, transaction_id)
    db.delete(tx)
    db.commit()
