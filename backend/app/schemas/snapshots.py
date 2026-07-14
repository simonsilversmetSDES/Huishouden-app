"""Schemas voor rekeningstatus (§6) en vermogensbalans (§9).

Bedragen over de draad als integer-centen. Snapshotdatum is de 1e van de maand
(maandelijkse stand); de UI kiest een maand, de dag is altijd 1.
"""

from datetime import date

from pydantic import BaseModel

from app.models.enums import AccountType, AssetClass


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


# --- Vermogensbalans (§9) ---


class AssetValue(BaseModel):
    asset_class: AssetClass
    value_cents: int


class NetWorthRow(BaseModel):
    snapshot_date: date
    assets: list[AssetValue]
    total_cents: int
    change_cents: int | None  # t.o.v. de vorige maand; None voor de eerste
    change_pct: float | None


class NetWorthOut(BaseModel):
    context_id: int
    rows: list[NetWorthRow]  # chronologisch, voor de evolutiegrafiek
    latest_date: date | None
    latest_total_cents: int  # 0 als er geen data is
    latest_change_cents: int | None
    latest_breakdown: list[AssetValue]  # laatste maand, voor de donut


class NetWorthIn(BaseModel):
    context_id: int
    snapshot_date: date
    asset_class: AssetClass
    value_cents: int


class NetWorthContextTotal(BaseModel):
    context_id: int
    name: str
    total_cents: int
    woning_cents: int  # aandeel woning in het totaal, voor de "zonder woning"-toggle


class NetWorthSummaryOut(BaseModel):
    contexts: list[NetWorthContextTotal]
    total_cents: int  # gezinstotaal over alle contexten
