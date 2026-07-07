"""Rekeningstatus-endpoints (spec §6): maandsnapshots per rekening.

Upsert op de UNIQUE(account_id, snapshot_date): dezelfde maand invoeren werkt de
bestaande stand bij. De GET geeft de volledige status (totalen + verandering +
ontbrekende-maand-reminder) via build_account_status.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Account, AccountSnapshot, Context
from app.schemas.snapshots import AccountSnapshotIn, AccountStatusOut
from app.services.account_status import build_account_status
from app.services.budget import from_cents

router = APIRouter(prefix="/api/account-snapshots", tags=["snapshots"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


@router.get("", response_model=AccountStatusOut)
def account_status(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> AccountStatusOut:
    context = _get_context(db, context_id)
    return build_account_status(db, context)


@router.put("", response_model=AccountStatusOut)
def upsert_snapshot(
    body: AccountSnapshotIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> AccountStatusOut:
    account = db.get(Account, body.account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende rekening")
    existing = db.scalars(
        select(AccountSnapshot).where(
            AccountSnapshot.account_id == body.account_id,
            AccountSnapshot.snapshot_date == body.snapshot_date,
        )
    ).one_or_none()
    balance = from_cents(body.balance_cents)
    if existing is None:
        db.add(
            AccountSnapshot(
                account_id=body.account_id, snapshot_date=body.snapshot_date, balance=balance
            )
        )
    else:
        existing.balance = balance
    db.commit()
    context = db.get(Context, account.context_id)
    assert context is not None
    return build_account_status(db, context)


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(
    snapshot_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    snapshot = db.get(AccountSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende snapshot")
    db.delete(snapshot)
    db.commit()
