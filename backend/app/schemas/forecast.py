"""Schemas voor de vermogensforecast ("Status balans"). Bedragen als integer-centen."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.enums import AssetClass
from app.schemas.snapshots import NetWorthRow

CellKind = Literal["werkelijk", "forecast", "error"]


class ForecastCellOut(BaseModel):
    value_cents: int | None  # None = blanco (werkelijke maand zonder waarde) of error
    kind: CellKind
    override: bool = False  # cel heeft een eigen formule-override
    error: str | None = None


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


class ForecastNetWorthOut(BaseModel):
    """Forecastreeks voor de nettowaarde-grafiek. De eerste rij is de laatste
    werkelijke maand (het verbindingspunt); alle volgende rijen zijn forecast."""

    rows: list[NetWorthRow]
