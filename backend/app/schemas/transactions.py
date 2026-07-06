"""Transactie-schemas. Bedragen over de draad altijd als integer-centen.

Asymmetrie in de bedrag-conventie (bewust, zoals de Excel-import):
- In (POST/PUT): amount_cents is een positieve magnitude; de server past het
  teken toe op basis van type (+ voor Inkomen, − voor Uitgaven/Sparen).
  Negatieve invoer mag als bewuste correctie/terugbetaling en flipt mee.
- Uit (responses): amount_cents is signed — de opslagconventie
  (+ = inkomen, − = uitgave/sparen).
"""

from datetime import date

from pydantic import BaseModel, field_validator

from app.models.enums import CategoryType, TransactionSource


class TransactionIn(BaseModel):
    context_id: int
    date: date
    effective_date: date | None = None  # None → gelijk aan date (budgetmaand)
    type: CategoryType
    amount_cents: int  # magnitude; server past het teken toe
    category_id: int | None = None
    description: str | None = None

    @field_validator("amount_cents")
    @classmethod
    def _niet_nul(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Bedrag mag niet 0 zijn")
        return value


class TransactionOut(BaseModel):
    id: int
    context_id: int
    date: date
    effective_date: date
    type: CategoryType
    amount_cents: int  # signed: + = inkomen, − = uitgave/sparen
    category_id: int | None
    category_name: str | None
    description: str | None
    source: TransactionSource
    is_internal_transfer: bool
