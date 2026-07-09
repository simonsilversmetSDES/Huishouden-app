from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context
from app.schemas.budget import BudgetMatrixOut, BudgetNoteIn, BudgetUpsertIn
from app.services.budget import UnknownCategoryError, build_matrix, upsert_budgets, upsert_note

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=BudgetMatrixOut)
def get_budget_matrix(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> BudgetMatrixOut:
    context = _get_context(db, context_id)
    return build_matrix(db, context, year)


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
def put_budgets(
    body: BudgetUpsertIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        upsert_budgets(db, body.items)
    except UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/notes", status_code=status.HTTP_204_NO_CONTENT)
def put_budget_note(
    body: BudgetNoteIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Celnotitie zetten of wissen (lege notitie = verwijderen)."""
    try:
        upsert_note(db, body)
    except UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
