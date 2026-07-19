"""Pydantic-schemas voor de Weekmenu-API (Fase 2: parsen + opslaan; Fase 3: CRUD + beheer).

Veldnamen zijn Engels, consistent met de kolomnamen uit Fase 1. Het parse-endpoint
geeft ALTIJD een bewerkbaar ``ParsedRecipe`` terug en slaat nooit iets op; opslaan
gebeurt apart via ``RecipeCreate`` na review in de frontend.
"""

import base64
import binascii
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.weekmenu.models import PantryType

# Anthropic accepteert max ~5 MB per afbeelding; we checken de gedecodeerde grootte.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _validate_image(image_base64: str, media_type: str | None) -> None:
    """Gedeelde check voor base64-afbeeldingen (parse-request én recept-foto-upload)."""
    if media_type not in ALLOWED_IMAGE_MEDIA_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_MEDIA_TYPES))
        raise ValueError(f"media type moet één van {allowed} zijn.")
    try:
        decoded = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("De afbeelding is geen geldige base64.") from exc
    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError("Afbeelding is te groot (max 5 MB).")


class ParsedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    unit: str | None = None


class ParsedRecipe(BaseModel):
    """Bewerkbaar resultaat van elk van de drie parsers (review-scherm in de frontend)."""

    title: str
    description: str = ""  # bereidingsstappen als platte tekst
    photo_url: str | None = None  # externe URL; download gebeurt pas bij opslaan
    source_url: str | None = None
    ingredients: list[ParsedIngredient] = []


class ParseRequest(BaseModel):
    """Eén van beide: een URL, óf een afbeelding (base64 + media type)."""

    url: str | None = None
    image_base64: str | None = None
    image_media_type: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "ParseRequest":
        if bool(self.url) == bool(self.image_base64):
            raise ValueError("Geef óf een url óf een afbeelding op (niet allebei, niet geen).")
        if self.image_base64:
            _validate_image(self.image_base64, self.image_media_type)
        return self


class RecipeIngredientIn(BaseModel):
    name: str
    quantity: str | None = None
    unit: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _name_not_blank(self) -> "RecipeIngredientIn":
        if not self.name.strip():
            raise ValueError("Ingrediëntnaam mag niet leeg zijn.")
        return self


class RecipeCreate(BaseModel):
    """Opslaan na review; photo_url wordt server-side gedownload naar photo_path,
    photo_base64 (geüploade afbeelding, bv. een geparste screenshot) wordt direct
    lokaal weggeschreven. Hooguit één van beide."""

    title: str
    description: str = ""
    source_url: str | None = None
    photo_url: str | None = None
    photo_base64: str | None = None
    photo_media_type: str | None = None
    moment_id: int | None = None
    category_id: int | None = None
    time_id: int | None = None
    difficulty_id: int | None = None
    ingredients: list[RecipeIngredientIn] = []

    @model_validator(mode="after")
    def _validate_create(self) -> "RecipeCreate":
        if not self.title.strip():
            raise ValueError("Titel mag niet leeg zijn.")
        if self.photo_base64:
            if self.photo_url:
                raise ValueError("Geef óf photo_url óf photo_base64 op, niet allebei.")
            _validate_image(self.photo_base64, self.photo_media_type)
        return self


class RecipeUpdate(RecipeCreate):
    """Volledige vervanging (PUT). Foto: nieuwe photo_url/photo_base64 vervangt de
    huidige, remove_photo verwijdert ze; geen van drie → foto blijft ongemoeid."""

    remove_photo: bool = False

    @model_validator(mode="after")
    def _no_new_photo_with_remove(self) -> "RecipeUpdate":
        if self.remove_photo and (self.photo_url or self.photo_base64):
            raise ValueError("remove_photo kan niet samen met een nieuwe foto.")
        return self


class RecipeIngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_id: int
    name: str  # naam van het canonieke ingrediënt
    pantry_type: PantryType
    quantity: str | None
    unit: str | None
    note: str | None


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    photo_path: str | None
    source_url: str | None
    moment_id: int | None
    category_id: int | None
    time_id: int | None
    difficulty_id: int | None
    ingredients: list[RecipeIngredientOut]


class RecipeListOut(BaseModel):
    """Lichtgewicht lijstweergave — zonder ingrediënten (detail wordt apart geladen)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    photo_path: str | None
    moment_id: int | None
    category_id: int | None
    time_id: int | None
    difficulty_id: int | None
    created_at: datetime


# --- Attribuuttabellen (beheerscherm) ---


class AttributeIn(BaseModel):
    name: str
    sort_order: int = 0

    @model_validator(mode="after")
    def _name_not_blank(self) -> "AttributeIn":
        if not self.name.strip():
            raise ValueError("Naam mag niet leeg zijn.")
        return self


class ColorAttributeIn(AttributeIn):
    color: str

    @model_validator(mode="after")
    def _color_not_blank(self) -> "ColorAttributeIn":
        if not self.color.strip():
            raise ValueError("Kleur mag niet leeg zijn.")
        return self


class AttributeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int


class ColorAttributeOut(AttributeOut):
    color: str


# --- Ingrediëntenbeheer ---


class IngredientOut(BaseModel):
    id: int
    name: str
    pantry_type: PantryType
    shopping_category_id: int | None
    recipe_count: int


class IngredientPatch(BaseModel):
    """Gedeeltelijke update; ``model_fields_set`` onderscheidt 'afwezig' van expliciete
    null (shopping_category_id is legitiem nullable, de andere velden niet)."""

    name: str | None = None
    pantry_type: PantryType | None = None
    shopping_category_id: int | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self) -> "IngredientPatch":
        if "name" in self.model_fields_set and (self.name is None or not self.name.strip()):
            raise ValueError("Naam mag niet leeg zijn.")
        if "pantry_type" in self.model_fields_set and self.pantry_type is None:
            raise ValueError("pantry_type mag niet null zijn.")
        return self
