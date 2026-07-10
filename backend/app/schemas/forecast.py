"""Schemas voor de vermogensforecast ("Status balans"). Bedragen als integer-centen."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import AssetClass
from app.schemas.snapshots import NetWorthRow

CellKind = Literal["werkelijk", "forecast", "error"]


class ForecastCellOut(BaseModel):
    value_cents: int | None  # None = blanco (werkelijke maand zonder waarde) of error
    kind: CellKind
    override: bool = False  # cel heeft een eigen formule-override
    override_formula: str | None = None  # de override-tekst, voor de formulebalk
    error: str | None = None
    note: str | None = None  # celnotitie (Excel-achtig), los van de formule


class ForecastRowOut(BaseModel):
    asset_class: AssetClass
    formula: str  # effectieve rij-formule (default of aangepast)
    is_default: bool
    warnings: list[str]
    cells: list[ForecastCellOut]  # 12 maanden


class ForecastMatrixOut(BaseModel):
    context_id: int
    year: int
    last_actual_month: date | None  # laatste maand met werkelijke balans
    rows: list[ForecastRowOut]
    totals: list[ForecastCellOut]  # totaalrij, 12 maanden


class ForecastFormulaIn(BaseModel):
    context_id: int
    asset_class: AssetClass
    year: int | None = None  # None = rij-default; jaar+maand = cel-override
    month: int | None = None
    formula: str  # leeg = wissen (terug naar default)


class ForecastNoteIn(BaseModel):
    """Celnotitie zetten of wissen: een lege/witruimte-notitie verwijdert ze."""

    context_id: int
    asset_class: AssetClass
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    note: str


class ForecastNetWorthOut(BaseModel):
    """Forecastreeks voor de nettowaarde-grafiek. De eerste rij is de laatste
    werkelijke maand (het verbindingspunt); alle volgende rijen zijn forecast."""

    rows: list[NetWorthRow]
