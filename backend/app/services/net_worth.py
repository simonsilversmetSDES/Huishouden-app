"""Vermogensbalans-rekenlogica (spec §9): nettowaarde per context per maand.

Per snapshotdatum de waarde per activaklasse en het totaal (Σ activaklassen, mag
negatief), plus de verandering (abs + %) t.o.v. de vorige maand. De laatste maand
levert de donut-verdeling. Alle rekenwerk in Decimal; centen aan de API-rand.

**Contant geld** wordt automatisch afgeleid uit de rekeningstanden (§6): voor elke
maand met rekeningsnapshots is `contant` = som van de rekeningsaldi en overschrijft
die de handmatige waarde. Maanden zonder rekeningdata vallen terug op de manuele
NetWorthSnapshot. De overige activaklassen blijven (voorlopig) handmatig.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Context, NetWorthSnapshot
from app.models.enums import AssetClass
from app.schemas.snapshots import AssetValue, NetWorthOut, NetWorthRow
from app.services.budget import ZERO, to_cents


def _contant_by_month(db: Session, context_id: int) -> dict[date, Decimal]:
    """Som van de rekeningsaldi per snapshotdatum (§6) voor deze context."""
    rows = db.execute(
        select(AccountSnapshot.snapshot_date, AccountSnapshot.balance)
        .join(Account, AccountSnapshot.account_id == Account.id)
        .where(Account.context_id == context_id)
    ).all()
    totals: dict[date, Decimal] = {}
    for snapshot_date, balance in rows:
        totals[snapshot_date] = totals.get(snapshot_date, ZERO) + balance
    return totals


def build_net_worth(db: Session, context: Context) -> NetWorthOut:
    snapshots = list(
        db.scalars(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.context_id == context.id)
            .order_by(NetWorthSnapshot.snapshot_date)
        )
    )
    by_date: dict[date, dict[AssetClass, Decimal]] = {}
    for snap in snapshots:
        by_date.setdefault(snap.snapshot_date, {})[snap.asset_class] = snap.value

    # Auto contant uit de rekeningstanden overschrijft de handmatige waarde.
    for snapshot_date, value in _contant_by_month(db, context.id).items():
        by_date.setdefault(snapshot_date, {})[AssetClass.CONTANT] = value

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
