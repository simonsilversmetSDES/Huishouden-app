from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Account, Context
from app.schemas.core import AccountOut

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> list[Account]:
    if db.get(Context, context_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return list(
        db.scalars(
            select(Account)
            .where(Account.context_id == context_id, Account.active)
            .order_by(Account.type, Account.name)
        ).all()
    )
