from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Category, Context
from app.models.enums import CategoryType
from app.schemas.core import CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=list[CategoryOut])
def list_categories(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    type: CategoryType | None = None,
) -> list[Category]:
    _get_context(db, context_id)
    query = select(Category).where(Category.context_id == context_id, Category.active)
    if type is not None:
        query = query.where(Category.type == type)
    return list(db.scalars(query.order_by(Category.sort_order, Category.id)).all())
