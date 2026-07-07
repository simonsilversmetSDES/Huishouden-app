"""Vermogensbalans-rekenlogica (spec §9): nettowaarde per context per maand.

Per snapshotdatum de waarde per activaklasse en het totaal (Σ activaklassen, mag
negatief), plus de verandering (abs + %) t.o.v. de vorige maand. De laatste maand
levert de donut-verdeling. Alle rekenwerk in Decimal; centen aan de API-rand.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, NetWorthSnapshot
from app.schemas.snapshots import AssetValue, NetWorthOut, NetWorthRow
from app.services.budget import ZERO, to_cents


def build_net_worth(db: Session, context: Context) -> NetWorthOut:
    snapshots = list(
        db.scalars(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.context_id == context.id)
            .order_by(NetWorthSnapshot.snapshot_date)
        )
    )
    by_date: dict[date, list[NetWorthSnapshot]] = {}
    for snap in snapshots:
        by_date.setdefault(snap.snapshot_date, []).append(snap)

    rows: list[NetWorthRow] = []
    prev_total: Decimal | None = None
    for snapshot_date in sorted(by_date):
        entries = by_date[snapshot_date]
        total = sum((e.value for e in entries), ZERO)
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
                    AssetValue(asset_class=e.asset_class, value_cents=to_cents(e.value))
                    for e in entries
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
