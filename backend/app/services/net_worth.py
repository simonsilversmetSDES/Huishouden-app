"""Vermogensbalans-rekenlogica (spec §9): nettowaarde per context per maand.

Per snapshotdatum de waarde per activaklasse en het totaal (Σ activaklassen, mag
negatief), plus de verandering (abs + %) t.o.v. de vorige maand. De laatste maand
levert de donut-verdeling. Alle rekenwerk in Decimal; centen aan de API-rand.

Activaklassen worden zoveel mogelijk **automatisch afgeleid**:
- `contant`, `pensioensparen`, `groepsverzekering` uit de rekeningstanden (§6),
  volgens het rekening-type (ACCOUNT_TYPE_ASSET_CLASS). Deze overschrijven per
  maand de eventuele handmatige waarde.
- `etf_fondsen`, `aandelen`, `bitcoin` uit de beleggingen (§7), gegroepeerd op
  `Security.soort`. Enkel de **huidige maand** wordt automatisch gevuld; oudere
  maanden houden hun bestaande handmatige snapshot.
- `woning` blijft (voorlopig) volledig handmatig.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Context, NetWorthSnapshot, Security
from app.models.enums import ACCOUNT_TYPE_ASSET_CLASS, AssetClass
from app.schemas.snapshots import AssetValue, NetWorthOut, NetWorthRow
from app.services.budget import ZERO, to_cents
from app.services.investments import build_portfolio


def _account_values_by_month(db: Session, context_id: int) -> dict[date, dict[AssetClass, Decimal]]:
    """Rekeningsaldi per snapshotdatum, gegroepeerd op de klasse van het rekening-type (§6)."""
    rows = db.execute(
        select(AccountSnapshot.snapshot_date, Account.type, AccountSnapshot.balance)
        .join(Account, AccountSnapshot.account_id == Account.id)
        .where(Account.context_id == context_id)
    ).all()
    out: dict[date, dict[AssetClass, Decimal]] = {}
    for snapshot_date, acc_type, balance in rows:
        asset_class = ACCOUNT_TYPE_ASSET_CLASS[acc_type]
        month = out.setdefault(snapshot_date, {})
        month[asset_class] = month.get(asset_class, ZERO) + balance
    return out


def _beleggingen_by_class(db: Session, context: Context) -> dict[AssetClass, Decimal]:
    """Actuele beleggingswaarde per activaklasse, gegroepeerd op Security.soort (§7)."""
    kinds = {
        sid: soort
        for sid, soort in db.execute(
            select(Security.id, Security.soort).where(Security.owner_context_id == context.id)
        ).all()
    }
    if not kinds:
        return {}
    portfolio = build_portfolio(db, context)
    totals: dict[AssetClass, Decimal] = {}
    for pos in portfolio.positions:
        if pos.value_cents is None:
            continue
        asset_class = AssetClass(kinds[pos.security_id].value)  # soort-waarde == klasse-waarde
        totals[asset_class] = totals.get(asset_class, ZERO) + Decimal(pos.value_cents) / 100
    return totals


def build_net_worth(db: Session, context: Context, today: date | None = None) -> NetWorthOut:
    if today is None:
        today = date.today()

    by_date: dict[date, dict[AssetClass, Decimal]] = {}
    for snap in db.scalars(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.context_id == context.id)
        .order_by(NetWorthSnapshot.snapshot_date)
    ):
        by_date.setdefault(snap.snapshot_date, {})[snap.asset_class] = snap.value

    # Rekeningstanden overschrijven per maand de afgeleide klassen (contant/pensioen/groeps).
    for snapshot_date, class_values in _account_values_by_month(db, context.id).items():
        month = by_date.setdefault(snapshot_date, {})
        for asset_class, value in class_values.items():
            month[asset_class] = value

    # Beleggingen enkel op de huidige maand; oudere maanden houden hun manuele snapshot.
    beleggingen = _beleggingen_by_class(db, context)
    if beleggingen:
        current_month = date(today.year, today.month, 1)
        month = by_date.setdefault(current_month, {})
        for asset_class, value in beleggingen.items():
            month[asset_class] = value

    rows: list[NetWorthRow] = []
    prev_total: Decimal | None = None
    for snapshot_date in sorted(by_date):
        assets = by_date[snapshot_date]
        total = sum(assets.values(), ZERO)
        change_cents: int | None = None
        change_pct: float | None = None
        if prev_total is not None:
            change = total - prev_total
            change_cents = to_cents(change)
            if prev_total != ZERO:
                change_pct = float(change / prev_total * 100)
        rows.append(
            NetWorthRow(
                snapshot_date=snapshot_date,
                assets=[
                    AssetValue(asset_class=ac, value_cents=to_cents(v))
                    for ac, v in assets.items()
                ],
                total_cents=to_cents(total),
                change_cents=change_cents,
                change_pct=change_pct,
            )
        )
        prev_total = total

    if rows:
        latest = rows[-1]
        return NetWorthOut(
            context_id=context.id,
            rows=rows,
            latest_date=latest.snapshot_date,
            latest_total_cents=latest.total_cents,
            latest_change_cents=latest.change_cents,
            latest_breakdown=latest.assets,
        )
    return NetWorthOut(
        context_id=context.id,
        rows=[],
        latest_date=None,
        latest_total_cents=0,
        latest_change_cents=None,
        latest_breakdown=[],
    )
