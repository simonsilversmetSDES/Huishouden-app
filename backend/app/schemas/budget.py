"""API-schemas voor de budgetmatrix. Bedragen over de draad altijd als integer-centen."""

from pydantic import BaseModel, Field

from app.models.enums import CategoryType


class BudgetCellIn(BaseModel):
    category_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    amount_cents: int


class BudgetUpsertIn(BaseModel):
    items: list[BudgetCellIn]


class BudgetNoteIn(BaseModel):
    """Celnotitie zetten of wissen: een lege/witruimte-notitie verwijdert ze."""

    category_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    note: str


class BudgetCategoryRow(BaseModel):
    category_id: int
    name: str
    month_cents: list[int]  # 12 waarden, jan t/m dec
    month_notes: list[str | None]  # 12 waarden; None = geen notitie
    total_cents: int


class BudgetTypeGroup(BaseModel):
    type: CategoryType
    categories: list[BudgetCategoryRow]
    monthly_total_cents: list[int]
    total_cents: int


class BudgetMatrixOut(BaseModel):
    context_id: int
    year: int
    groups: list[BudgetTypeGroup]
    to_be_allocated_cents: list[int]  # per maand: Σ Inkomen − Σ Uitgaven − Σ Sparen
    to_be_allocated_total_cents: int
