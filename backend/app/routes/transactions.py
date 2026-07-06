from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Category, Context
from app.models.enums import CategoryType
from app.schemas.transactions import TransactionIn, TransactionOut
from app.services.transactions import (
    CategoryTypeMismatchError,
    UnknownCategoryError,
    create_transaction,
    list_transactions,
    to_out,
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
