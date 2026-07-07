"""Koers-endpoints (spec §7): manuele koers + yfinance-fetch (uitschakelbaar)."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Context, Security
from app.schemas.investments import PriceFetchResult, SecurityPriceIn, SecurityPriceOut
from app.services.prices import fetch_prices, upsert_price

router = APIRouter(tags=["prices"])


@router.put("/api/security-prices", response_model=SecurityPriceOut)
def put_price(
    body: SecurityPriceIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityPriceOut:
    if db.get(Security, body.security_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekend effect")
    invalid = HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Ongeldige koers")
    try:
        price = Decimal(body.price)
    except InvalidOperation as exc:
        raise invalid from exc
    if price <= 0:
        raise invalid
    row = upsert_price(db, body.security_id, body.date, price, source="manual")
    db.commit()
    return SecurityPriceOut(
        id=row.id,
        security_id=row.security_id,
        date=row.date,
        price=str(row.price),
        source=row.source,
    )


@router.post("/api/prices/fetch", response_model=PriceFetchResult)
def fetch(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    context_id: int,
) -> PriceFetchResult:
    if db.get(Context, context_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    if not settings.price_fetch_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Koersen ophalen is uitgeschakeld"
        )
    securities = list(
        db.scalars(select(Security).where(Security.owner_context_id == context_id)).all()
    )
    result = fetch_prices(db, securities, date.today())
    db.commit()
    return PriceFetchResult(fetched=result.fetched, failed=result.failed)
