"""API-schemas voor het dashboard: budget vs. werkelijk per maand."""

from pydantic import BaseModel

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
