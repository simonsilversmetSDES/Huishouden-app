"""Pydantic-schemas voor de Weekmenu-API (Fase 2: parsen + opslaan).

Veldnamen zijn Engels, consistent met de kolomnamen uit Fase 1. Het parse-endpoint
geeft ALTIJD een bewerkbaar ``ParsedRecipe`` terug en slaat nooit iets op; opslaan
gebeurt apart via ``RecipeCreate`` na review in de frontend.
"""

import base64
import binascii

from pydantic import BaseModel, ConfigDict, model_validator

from app.weekmenu.models import PantryType

# Anthropic accepteert max ~5 MB per afbeelding; we checken de gedecodeerde grootte.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


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
            if self.image_media_type not in ALLOWED_IMAGE_MEDIA_TYPES:
                allowed = ", ".join(sorted(ALLOWED_IMAGE_MEDIA_TYPES))
                raise ValueError(f"image_media_type moet één van {allowed} zijn.")
            try:
                decoded = base64.b64decode(self.image_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("image_base64 is geen geldige base64.") from exc
            if len(decoded) > MAX_IMAGE_BYTES:
                raise ValueError("Afbeelding is te groot (max 5 MB).")
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
    """Opslaan na review; photo_url wordt server-side gedownload naar photo_path."""

    title: str
    description: str = ""
    source_url: str | None = None
    photo_url: str | None = None
    moment_id: int | None = None
    category_id: int | None = None
    time_id: int | None = None
    difficulty_id: int | None = None
    ingredients: list[RecipeIngredientIn] = []

    @model_validator(mode="after")
    def _title_not_blank(self) -> "RecipeCreate":
        if not self.title.strip():
            raise ValueError("Titel mag niet leeg zijn.")
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
