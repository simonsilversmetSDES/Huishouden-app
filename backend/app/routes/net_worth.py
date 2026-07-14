"""Vermogensbalans-endpoints (spec §9): waarde per activaklasse per maand.

Upsert op UNIQUE(context_id, snapshot_date, asset_class). De GET geeft de volledige
reeks (evolutie + laatste maand voor de donut) via build_net_worth.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context, NetWorthSnapshot
from app.schemas.snapshots import (
    NetWorthContextTotal,
    NetWorthIn,
    NetWorthOut,
    NetWorthSummaryOut,
)
from app.services.budget import from_cents
from app.services.net_worth import build_net_worth, build_net_worth_combined

router = APIRouter(prefix="/api/net-worth", tags=["net-worth"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=NetWorthOut)
def net_worth(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> NetWorthOut:
    context = _get_context(db, context_id)
    return build_net_worth(db, context)


@router.get("/combined", response_model=NetWorthOut)
def net_worth_combined(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_ids: Annotated[list[int], Query()],
) -> NetWorthOut:
    """Nettowaarde van meerdere entiteiten opgeteld (bv. Simon + Jozefien + Gemeenschappelijk)."""
    contexts = list(db.scalars(select(Context).where(Context.id.in_(context_ids))).all())
    if not contexts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Geen geldige contexts")
    return build_net_worth_combined(db, contexts)


@router.get("/summary", response_model=NetWorthSummaryOut)
def net_worth_summary(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> NetWorthSummaryOut:
    """Laatste nettowaarde per context + het gezinstotaal (voor de 't.o.v. totaal'-gauge)."""
    contexts = db.scalars(select(Context).order_by(Context.id)).all()
    totals = []
    for c in contexts:
        nw = build_net_worth(db, c)
        woning_cents = sum(
            a.value_cents for a in nw.latest_breakdown if a.asset_class == "woning"
        )
        totals.append(
            NetWorthContextTotal(
                context_id=c.id,
                name=c.name,
                total_cents=nw.latest_total_cents,
                woning_cents=woning_cents,
            )
        )
    return NetWorthSummaryOut(contexts=totals, total_cents=sum(t.total_cents for t in totals))


@router.put("", response_model=NetWorthOut)
def upsert_net_worth(
    body: NetWorthIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> NetWorthOut:
    context = _get_context(db, body.context_id)
    existing = db.scalars(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.context_id == body.context_id,
            NetWorthSnapshot.snapshot_date == body.snapshot_date,
            NetWorthSnapshot.asset_class == body.asset_class,
        )
    ).one_or_none()
    value = from_cents(body.value_cents)
    if existing is None:
        db.add(
            NetWorthSnapshot(
                context_id=body.context_id,
                snapshot_date=body.snapshot_date,
                asset_class=body.asset_class,
                value=value,
            )
        )
    else:
        existing.value = value
    db.commit()
    return build_net_worth(db, context)


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_net_worth(
    snapshot_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    snapshot = db.get(NetWorthSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende snapshot")
    db.delete(snapshot)
    db.commit()
