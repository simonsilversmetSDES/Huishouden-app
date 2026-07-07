"""Schemas voor rekeningstatus (§6) en vermogensbalans (§9).

Bedragen over de draad als integer-centen. Snapshotdatum is de 1e van de maand
(maandelijkse stand); de UI kiest een maand, de dag is altijd 1.
"""

from datetime import date

from pydantic import BaseModel

from app.models.enums import AccountType


class AccountRef(BaseModel):
    id: int
    name: str
    type: AccountType


class AccountBalance(BaseModel):
    account_id: int
    balance_cents: int


class AccountStatusRow(BaseModel):
    snapshot_date: date
    balances: list[AccountBalance]
    total_cents: int
    change_cents: int | None  # t.o.v. de vorige maand; None voor de eerste
    change_pct: float | None


class AccountStatusOut(BaseModel):
    context_id: int
    accounts: list[AccountRef]
    rows: list[AccountStatusRow]
    missing_current_month: bool
    missing_account_ids: list[int]


class AccountSnapshotIn(BaseModel):
    account_id: int
    snapshot_date: date
    balance_cents: int
