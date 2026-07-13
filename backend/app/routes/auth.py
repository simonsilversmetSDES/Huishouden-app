from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.auth.passwords import verify_password
from app.auth.rate_limit import client_ip, login_limiter
from app.auth.sessions import create_session_value
from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    # Rate limiting per IP én per (opgegeven) account. De melding is even generiek
    # voor bestaande als onbestaande accounts en verraadt dus niets.
    keys = [f"ip:{client_ip(request)}", f"acc:{body.email.strip().lower()}"]
    retry_after = login_limiter.retry_after(keys)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Te veel mislukte pogingen — probeer het later opnieuw",
            headers={"Retry-After": str(retry_after)},
        )
    user = db.scalars(select(User).where(User.email == body.email)).one_or_none()
    hash_ = user.password_hash if user else None
    if not verify_password(hash_, body.password) or user is None:
        login_limiter.register_failure(
            keys,
            max_attempts=settings.login_max_attempts,
            base_block_seconds=settings.login_block_base_seconds,
            max_block_seconds=settings.login_block_max_seconds,
        )
        # Generieke melding: geen onderscheid tussen fout e-mailadres en fout wachtwoord.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Ongeldige inloggegevens")
    login_limiter.reset(keys)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_value(user.id, settings),
        max_age=settings.session_max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
