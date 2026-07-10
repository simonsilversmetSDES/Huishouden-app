"""Vermogensforecast-endpoints ("Status balans"): matrix, formule-upsert en
de forecastreeks voor de nettowaarde-grafiek."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context
from app.schemas.forecast import (
    ForecastFormulaIn,
    ForecastMatrixOut,
    ForecastNetWorthOut,
    ForecastNoteIn,
)
from app.services.forecast import (
    UnknownContextError,
    build_forecast_matrix,
    build_forecast_net_worth,
    upsert_forecast_note,
    upsert_formula,
)
from app.services.forecast_formula import FormulaError

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=ForecastMatrixOut)
def get_forecast_matrix(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> ForecastMatrixOut:
    context = _get_context(db, context_id)
    return build_forecast_matrix(db, context, year)


@router.put("/formulas", status_code=status.HTTP_204_NO_CONTENT)
def put_forecast_formula(
    body: ForecastFormulaIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Rij-formule (year/month leeg) of cel-override zetten; lege formule = wissen."""
    try:
        upsert_formula(db, body)
    except UnknownContextError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FormulaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/notes", status_code=status.HTTP_204_NO_CONTENT)
def put_forecast_note(
    body: ForecastNoteIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Celnotitie zetten of wissen (lege notitie = verwijderen)."""
    try:
        upsert_forecast_note(db, body)
    except UnknownContextError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/net-worth", response_model=ForecastNetWorthOut)
def get_forecast_net_worth(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_ids: Annotated[list[int], Query()],
) -> ForecastNetWorthOut:
    """Forecast van de (gecombineerde) nettowaarde, aansluitend op de werkelijke reeks."""
    contexts = list(db.scalars(select(Context).where(Context.id.in_(context_ids))).all())
    if not contexts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Geen geldige contexts")
    return build_forecast_net_worth(db, contexts)
