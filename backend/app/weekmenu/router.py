"""Weekmenu-routes onder /api/weekmenu; auth per route via CurrentUser (repo-conventie).

Fase 2: POST /recipes/parse (drie parsers, geeft ALTIJD een bewerkbaar recept-object
terug, slaat nooit op) en POST /recipes (opslaan na review, met ingrediënt-matching).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.database import get_db
from app.weekmenu import crud, parsing, photos
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.schemas import ParsedRecipe, ParseRequest, RecipeCreate, RecipeOut

router = APIRouter(prefix="/api/weekmenu", tags=["weekmenu"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def _to_http(exc: WeekmenuError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


@router.get("/ping")
def ping(_user: CurrentUser) -> dict[str, str]:
    """Minimale route uit Fase 0: bewijst registratie + auth-wiring."""
    return {"status": "ok"}


@router.post("/recipes/parse", response_model=ParsedRecipe)
def parse_recipe(payload: ParseRequest, _user: CurrentUser, settings: SettingsDep) -> ParsedRecipe:
    """Parse een recept uit een URL of afbeelding; slaat NOOIT op (review in frontend)."""
    try:
        if payload.url:
            return parsing.parse_url(payload.url, settings)
        assert payload.image_base64 and payload.image_media_type  # afgedwongen door schema
        return parsing.parse_image(payload.image_base64, payload.image_media_type, settings)
    except WeekmenuError as exc:
        raise _to_http(exc) from exc


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def create_recipe(payload: RecipeCreate, _user: CurrentUser, db: DbDep) -> RecipeOut:
    """Sla een gereviewd recept op; externe foto wordt lokaal gedownload (niet-fataal)."""
    photo_path = photos.save_photo_from_url(payload.photo_url) if payload.photo_url else None
    try:
        recipe = crud.create_recipe(db, payload, photo_path)
    except WeekmenuError as exc:
        raise _to_http(exc) from exc
    return crud.recipe_to_out(recipe)
