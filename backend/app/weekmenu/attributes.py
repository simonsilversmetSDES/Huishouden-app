"""Generiek CRUD voor de vijf beheerbare attribuuttabellen (Fase 3-beheerscherm).

Eén route-factory in plaats van vijf keer dezelfde vier routes. DELETE blokkeert
met 409 ``in_use`` wanneer de rij nog gerefereerd wordt — nooit stilzwijgend
recepten of ingrediënten degraderen.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.weekmenu.errors import WeekmenuError, to_http
from app.weekmenu.models import (
    Ingredient,
    Recipe,
    RecipeCategory,
    RecipeDifficulty,
    RecipeMoment,
    RecipeTime,
    ShoppingCategory,
    ShoppingListItem,
)
from app.weekmenu.schemas import AttributeIn, AttributeOut, ColorAttributeIn, ColorAttributeOut

attributes_router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class _Resource:
    path: str
    model: type
    has_color: bool
    # Waar de FK's naartoe wijzen die DELETE moeten blokkeren, + NL-omschrijving.
    usage: tuple[tuple[type, str], ...]
    usage_noun: str


_RESOURCES = (
    _Resource("/moments", RecipeMoment, False, ((Recipe, "moment_id"),), "recept(en)"),
    _Resource("/categories", RecipeCategory, True, ((Recipe, "category_id"),), "recept(en)"),
    _Resource("/times", RecipeTime, False, ((Recipe, "time_id"),), "recept(en)"),
    _Resource("/difficulties", RecipeDifficulty, False, ((Recipe, "difficulty_id"),), "recept(en)"),
    _Resource(
        "/shopping-categories",
        ShoppingCategory,
        True,
        ((Ingredient, "shopping_category_id"), (ShoppingListItem, "category_id")),
        "ingrediënt(en) of boodschappen-item(s)",
    ),
)


def _name_taken(db: Session, model: type, name: str, exclude_id: int | None) -> bool:
    """Duplicaatcheck trim/case-insensitief — strikter dan de exacte db-constraint."""
    stmt = select(model).where(func.lower(model.name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return db.scalar(stmt) is not None


def _get_or_404(db: Session, model: type, item_id: int):
    obj = db.get(model, item_id)
    if obj is None:
        raise to_http(WeekmenuError(404, "not_found", "Niet gevonden."))
    return obj


def _usage_count(db: Session, resource: _Resource, item_id: int) -> int:
    total = 0
    for model, column_name in resource.usage:
        column: InstrumentedAttribute = getattr(model, column_name)
        total += db.scalar(select(func.count()).select_from(model).where(column == item_id)) or 0
    return total


def _register(resource: _Resource) -> None:
    in_schema = ColorAttributeIn if resource.has_color else AttributeIn
    out_schema = ColorAttributeOut if resource.has_color else AttributeOut
    model = resource.model

    def _apply(obj, payload) -> None:
        obj.name = payload.name.strip()
        obj.sort_order = payload.sort_order
        if resource.has_color:
            obj.color = payload.color.strip()

    @attributes_router.get(resource.path, response_model=list[out_schema])
    def list_items(_user: CurrentUser, db: DbDep):
        return db.scalars(select(model).order_by(model.sort_order, model.name)).all()

    @attributes_router.post(resource.path, response_model=out_schema, status_code=201)
    def create_item(payload: in_schema, _user: CurrentUser, db: DbDep):  # type: ignore[valid-type]
        if _name_taken(db, model, payload.name, exclude_id=None):
            raise to_http(
                WeekmenuError(409, "duplicate_name", f"'{payload.name.strip()}' bestaat al.")
            )
        obj = model()
        _apply(obj, payload)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @attributes_router.put(resource.path + "/{item_id}", response_model=out_schema)
    def update_item(item_id: int, payload: in_schema, _user: CurrentUser, db: DbDep):  # type: ignore[valid-type]
        obj = _get_or_404(db, model, item_id)
        if _name_taken(db, model, payload.name, exclude_id=item_id):
            raise to_http(
                WeekmenuError(409, "duplicate_name", f"'{payload.name.strip()}' bestaat al.")
            )
        _apply(obj, payload)
        db.commit()
        db.refresh(obj)
        return obj

    @attributes_router.delete(resource.path + "/{item_id}", status_code=204)
    def delete_item(item_id: int, _user: CurrentUser, db: DbDep) -> Response:
        obj = _get_or_404(db, model, item_id)
        count = _usage_count(db, resource, item_id)
        if count:
            raise to_http(
                WeekmenuError(
                    409,
                    "in_use",
                    f"'{obj.name}' wordt nog gebruikt door {count} {resource.usage_noun}.",
                )
            )
        db.delete(obj)
        db.commit()
        return Response(status_code=204)


for _resource in _RESOURCES:
    _register(_resource)
