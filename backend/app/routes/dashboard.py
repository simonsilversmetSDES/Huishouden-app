from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context
from app.schemas.dashboard import DashboardOut, MonthNoteIn
from app.services.dashboard import build_dashboard, upsert_month_note

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    month_to: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> DashboardOut:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return build_dashboard(db, context, year, month, month_to)


@router.put("/notes", status_code=status.HTTP_204_NO_CONTENT)
def put_month_note(
    body: MonthNoteIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Maandnotitie zetten of wissen (lege notitie = verwijderen)."""
    if db.get(Context, body.context_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    upsert_month_note(db, body)
