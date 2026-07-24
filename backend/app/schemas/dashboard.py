"""API-schemas voor het dashboard: budget vs. werkelijk per maand."""

from pydantic import BaseModel, Field

from app.models.enums import CategoryType


class TypeTotal(BaseModel):
    type: CategoryType
    budget_cents: int
    actual_cents: int  # positieve grootte binnen het type


class CategoryStatus(BaseModel):
    category_id: int
    name: str
    type: CategoryType
    budget_cents: int
    actual_cents: int


class MonthTotals(BaseModel):
    month: int
    totals: list[TypeTotal]


class MonthNoteOut(BaseModel):
    month: int
    note: str


class MonthNoteIn(BaseModel):
    """Maandnotitie zetten of wissen: een lege/witruimte-notitie verwijdert ze."""

    context_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    note: str


class DashboardOut(BaseModel):
    context_id: int
    year: int
    month: int | None  # gekozen losse maand; None bij YTD of heel jaar
    month_to: int | None = None  # YTD-eindmaand (1..month_to); None = losse maand of heel jaar
    to_be_allocated_cents: int  # gebudgetteerde TBA van de periode
    type_totals: list[TypeTotal]
    categories: list[CategoryStatus]
    uncategorized_count: int
    months: list[MonthTotals]  # altijd 12, voor de staafgrafiek werkelijk vs. budget
    month_notes: list[MonthNoteOut]  # enkel maanden mét notitie, oplopend op maand
