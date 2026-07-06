"""Schemas voor de CSV-importflow (spec §5.2): preview → bevestigen → opslaan.

Bedragen over de draad als signed integer-centen (opslagconventie: + = inkomen,
− = uitgave/sparen) — bank-CSV's leveren al getekende bedragen.
"""

from datetime import date

from pydantic import BaseModel

from app.models.enums import Bank, CategoryType


class AccountRef(BaseModel):
    id: int
    name: str
    context_id: int
    context_name: str


class PreviewRowOut(BaseModel):
    date: date
    effective_date: date  # default = date; budgetmaand, aanpasbaar in de preview
    amount_cents: int  # signed
    type: CategoryType  # suggestie: uit de regelmatch, anders uit het teken
    counterparty_name: str | None
    counterparty_iban: str | None
    description: str | None
    import_hash: str
    duplicate: bool  # al in de database (of eerder in ditzelfde bestand)
    is_internal_transfer: bool
    suggested_category_id: int | None
    suggested_category_name: str | None
    matched_rule_id: int | None


class ImportPreviewOut(BaseModel):
    bank: Bank
    filename: str
    account: AccountRef | None  # None = rekeningnummer niet gekend (zie unmatched_ibans)
    unmatched_ibans: list[str]
    rows: list[PreviewRowOut]
    new_count: int
    duplicate_count: int
    uncategorized_count: int  # nieuw, niet-intern, zonder categoriesuggestie
    skipped: list[str]
