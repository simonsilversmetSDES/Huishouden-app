"""Schemas voor de categorisatieregels (spec §5.3): CRUD + retroactief toepassen.

Een regel matcht op tegenpartijnaam, IBAN of omschrijving (contains/equals/regex)
en wijst een categorie toe. `created_from_correction` markeert regels die uit het
leereffect ontstaan (een gebruikerscorrectie).
"""

from pydantic import BaseModel

from app.models.enums import MatchField, MatchType


class RuleIn(BaseModel):
    context_id: int
    match_field: MatchField
    match_type: MatchType
    match_value: str
    category_id: int
    priority: int = 0
    created_from_correction: bool = False


class RuleOut(BaseModel):
    id: int
    context_id: int
    priority: int
    match_field: MatchField
    match_type: MatchType
    match_value: str
    category_id: int
    category_name: str | None
    created_from_correction: bool


class RuleApplyResult(BaseModel):
    updated_count: int
