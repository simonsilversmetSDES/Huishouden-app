from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.sessions import parse_session_value
from app.config import Settings, get_settings
from app.database import get_db
from app.models import User


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Niet ingelogd")
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        raise unauthorized
    user_id = parse_session_value(cookie, settings)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
