"""Rekeningstatus-rekenlogica (spec §6): maandtotalen + verandering per context.

Per snapshotdatum (maandelijkse stand) het saldo per rekening, het contexttotaal
en de verandering (absoluut + %) t.o.v. de vorige maand. Alle rekenwerk in Decimal
(nooit float); centen enkel aan de API-rand. Daarnaast: welke actieve rekeningen
de snapshot van de huidige maand nog missen (reminder op het dashboard).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Context
from app.schemas.snapshots import AccountBalance, AccountRef, AccountStatusOut, AccountStatusRow
from app.services.budget import ZERO, to_cents


def build_account_status(
    db: Session, context: Context, today: date | None = None
) -> AccountStatusOut:
    if today is None:
        today = date.today()

    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.context_id == context.id, Account.active)
            .order_by(Account.type, Account.name)
        )
    )
    account_ids = [a.id for a in accounts]
    refs = [AccountRef(id=a.id, name=a.name, type=a.type) for a in accounts]
    if not account_ids:
        return AccountStatusOut(
            context_id=context.id,
            accounts=[],
            rows=[],
            missing_current_month=False,
            missing_account_ids=[],
        )

    snapshots = list(
        db.scalars(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id.in_(account_ids))
            .order_by(AccountSnapshot.snapshot_date)
        )
    )
    by_date: dict[date, dict[int, Decimal]] = {}
    for snap in snapshots:
        by_date.setdefault(snap.snapshot_date, {})[snap.account_id] = snap.balance

    rows: list[AccountStatusRow] = []
    prev_total: Decimal | None = None
    for snapshot_date in sorted(by_date):
        balances = by_date[snapshot_date]
        total = sum(balances.values(), ZERO)
        change_cents: int | None = None
        change_pct: float | None = None
        if prev_total is not None:
            change = total - prev_total
            change_cents = to_cents(change)
            if prev_total != ZERO:
                change_pct = float(change / prev_total * 100)
        rows.append(
            AccountStatusRow(
                snapshot_date=snapshot_date,
                balances=[
                    AccountBalance(account_id=aid, balance_cents=to_cents(bal))
                    for aid, bal in balances.items()
                ],
                total_cents=to_cents(total),
                change_cents=change_cents,
                change_pct=change_pct,
            )
        )
        prev_total = total

    current = (today.year, today.month)
    have_current = {
        snap.account_id
        for snap in snapshots
        if (snap.snapshot_date.year, snap.snapshot_date.month) == current
    }
    missing_ids = [aid for aid in account_ids if aid not in have_current]
    return AccountStatusOut(
        context_id=context.id,
        accounts=refs,
        rows=rows,
        missing_current_month=len(missing_ids) > 0,
        missing_account_ids=missing_ids,
    )
