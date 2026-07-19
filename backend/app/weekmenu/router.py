"""Weekmenu-routes onder /api/weekmenu; auth per route via CurrentUser (repo-conventie)."""

from fastapi import APIRouter

from app.auth.deps import CurrentUser

router = APIRouter(prefix="/api/weekmenu", tags=["weekmenu"])


@router.get("/ping")
def ping(_user: CurrentUser) -> dict[str, str]:
    """Minimale route uit Fase 0: bewijst registratie + auth-wiring."""
    return {"status": "ok"}
