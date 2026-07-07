from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Account, Context
from app.schemas.core import AccountIn, AccountOut
from app.services.accounts import (
    DuplicateAccountError,
    EmptyAccountNameError,
    create_account,
    deactivate_account,
    update_account,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


def _get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende rekening")
    return account


@router.get("", response_model=list[AccountOut])
def list_accounts(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> list[Account]:
    _get_context(db, context_id)
    return list(
        db.scalars(
            select(Account)
            .where(Account.context_id == context_id, Account.active)
            .order_by(Account.type, Account.name)
        ).all()
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AccountOut)
def create_account_route(
    body: AccountIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Account:
    _get_context(db, body.context_id)
    try:
        return create_account(db, body.context_id, body.name, body.type, body.bank, body.iban)
    except EmptyAccountNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except DuplicateAccountError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.put("/{account_id}", response_model=AccountOut)
def update_account_route(
    account_id: int,
    body: AccountIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Account:
    account = _get_account(db, account_id)
    if body.context_id != account.context_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="De context van een rekening is vast"
        )
    try:
        return update_account(db, account, body.name, body.type, body.bank, body.iban)
    except EmptyAccountNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_route(
    account_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    deactivate_account(db, _get_account(db, account_id))
