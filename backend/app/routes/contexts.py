from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context
from app.schemas.core import ContextOut

router = APIRouter(prefix="/api/contexts", tags=["contexts"])


@router.get("", response_model=list[ContextOut])
def list_contexts(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[Context]:
    return list(db.scalars(select(Context).order_by(Context.id)).all())
