"""Weekmenu-routes onder /api/weekmenu; auth per route via CurrentUser (repo-conventie).

Fase 2: POST /recipes/parse (drie parsers, geeft ALTIJD een bewerkbaar recept-object
terug, slaat nooit op) en POST /recipes (opslaan na review, met ingrediënt-matching).
Fase 3: recept-CRUD, ingrediëntenbeheer, attribuut-CRUD (attributes.py) en het
auth-beveiligd serveren van receptfoto's.
"""

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.database import get_db
from app.weekmenu import crud, parsing, photos
from app.weekmenu.attributes import attributes_router
from app.weekmenu.errors import WeekmenuError, to_http
from app.weekmenu.schemas import (
    IngredientOut,
    IngredientPatch,
    ParsedRecipe,
    ParseRequest,
    RecipeCreate,
    RecipeListOut,
    RecipeOut,
    RecipeUpdate,
)

router = APIRouter(prefix="/api/weekmenu", tags=["weekmenu"])
router.include_router(attributes_router)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def _store_photo(payload: RecipeCreate) -> str | None:
    """Sla de meegegeven foto op (upload-bytes of externe URL); None bij falen/geen foto.

    Niet-fataal: een recept wordt gewoon zonder foto opgeslagen (Fase 2-beslissing).
    """
    if payload.photo_base64:
        assert payload.photo_media_type  # afgedwongen door schema
        return photos.save_photo_bytes(
            base64.b64decode(payload.photo_base64), payload.photo_media_type
        )
    if payload.photo_url:
        return photos.save_photo_from_url(payload.photo_url)
    return None


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
        raise to_http(exc) from exc


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def create_recipe(payload: RecipeCreate, _user: CurrentUser, db: DbDep) -> RecipeOut:
    """Sla een gereviewd recept op; de foto wordt lokaal opgeslagen (niet-fataal)."""
    photo_path = _store_photo(payload)
    try:
        recipe = crud.create_recipe(db, payload, photo_path)
    except WeekmenuError as exc:
        raise to_http(exc) from exc
    return crud.recipe_to_out(recipe)


@router.get("/recipes", response_model=list[RecipeListOut])
def list_recipes(_user: CurrentUser, db: DbDep) -> list[RecipeListOut]:
    """Lichtgewicht lijst (zonder ingrediënten); filteren gebeurt client-side."""
    return [RecipeListOut.model_validate(recipe) for recipe in crud.list_recipes(db)]


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, _user: CurrentUser, db: DbDep) -> RecipeOut:
    try:
        recipe = crud.get_recipe(db, recipe_id)
    except WeekmenuError as exc:
        raise to_http(exc) from exc
    return crud.recipe_to_out(recipe)


@router.put("/recipes/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int, payload: RecipeUpdate, _user: CurrentUser, db: DbDep
) -> RecipeOut:
    """Volledige vervanging; de oude foto verdwijnt pas ná een geslaagde commit."""
    new_photo_path = _store_photo(payload)
    try:
        recipe, photo_to_delete = crud.update_recipe(db, recipe_id, payload, new_photo_path)
    except WeekmenuError as exc:
        # Commit mislukt/geweigerd → de al weggeschreven nieuwe foto is een wees.
        photos.delete_photo(new_photo_path)
        raise to_http(exc) from exc
    photos.delete_photo(photo_to_delete)
    return crud.recipe_to_out(recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, _user: CurrentUser, db: DbDep) -> Response:
    try:
        photo_path = crud.delete_recipe(db, recipe_id)
    except WeekmenuError as exc:
        raise to_http(exc) from exc
    photos.delete_photo(photo_path)
    return Response(status_code=204)


@router.get("/ingredients", response_model=list[IngredientOut])
def list_ingredients(_user: CurrentUser, db: DbDep) -> list[IngredientOut]:
    return crud.list_ingredients(db)


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientOut)
def patch_ingredient(
    ingredient_id: int, payload: IngredientPatch, _user: CurrentUser, db: DbDep
) -> IngredientOut:
    try:
        return crud.patch_ingredient(db, ingredient_id, payload)
    except WeekmenuError as exc:
        raise to_http(exc) from exc


@router.get("/photos/{filename}")
def get_photo(filename: str, _user: CurrentUser) -> FileResponse:
    """Serveer een receptfoto; strikte naamvalidatie sluit path traversal uit.

    ``photos.PHOTOS_DIR`` bewust at call time lezen (module-attribuut) zodat de
    test-monkeypatch werkt. Bestandsnamen zijn immutable uuids → agressief cachen.
    """
    not_found = HTTPException(
        status_code=404, detail={"code": "not_found", "message": "Foto niet gevonden."}
    )
    if not photos.PHOTO_FILENAME_RE.fullmatch(filename):
        raise not_found
    path = photos.PHOTOS_DIR / filename
    if not path.is_file():
        raise not_found
    return FileResponse(
        path,
        media_type=photos.media_type_for(filename),
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
