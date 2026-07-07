"""Eenmalige migratie (spec §10) van de beleggingstransacties uit CSV.

Bron: per persoon een CSV (`;`-delimiter, punt-decimalen, datum dd/mm/jjjj) met
kolommen Datum, Share name, Aantal shares, prijs per share, Transactiekost,
Transactiebelasting, Totaal. De CSV is de betrouwbare bron (de .xlsm-namen waren
`#VALUE!`). Alle rijen zijn aankopen (geen verkoopkolom).

Per unieke Share name wordt één `Security` (owner = context) aangemaakt; elke rij
wordt een `SecurityTransaction` (side=buy). Geld/hoeveelheden als exacte Decimal
(nooit float). Idempotent op effect-niveau: een effect dat al transacties heeft
wordt overgeslagen, zodat opnieuw draaien niets dupliceert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Context, Security, SecurityTransaction
from app.models.enums import SecuritySide
from app.services.securities import transaction_total


@dataclass(frozen=True)
class InvestmentRow:
    date: date
    name: str
    shares: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal


@dataclass
class SecurityImportReport:
    name: str
    created: bool = False
    transactions_new: int = 0
    skipped_existing: bool = False


@dataclass
class InvestmentsImportReport:
    context: str
    securities: list[SecurityImportReport] = field(default_factory=list)


def import_rows(
    db: Session, context: Context, rows: list[InvestmentRow]
) -> InvestmentsImportReport:
    """Rijen (van één persoon) importeren; caller commit."""
    report = InvestmentsImportReport(context=context.name)
    existing = {
        s.name: s
        for s in db.scalars(select(Security).where(Security.owner_context_id == context.id))
    }

    grouped: dict[str, list[InvestmentRow]] = {}
    for row in rows:
        grouped.setdefault(row.name, []).append(row)

    for name, group in grouped.items():
        security = existing.get(name)
        created = security is None
        if security is None:
            security = Security(name=name, ticker=None, isin=None, owner_context_id=context.id)
            db.add(security)
            db.flush()
            existing[name] = security

        sec_report = SecurityImportReport(name=name, created=created)
        has_tx = (
            db.scalar(
                select(func.count())
                .select_from(SecurityTransaction)
                .where(SecurityTransaction.security_id == security.id)
            )
            or 0
        )
        if has_tx:
            sec_report.skipped_existing = True
            report.securities.append(sec_report)
            continue

        for row in group:
            total = transaction_total(SecuritySide.BUY, row.shares, row.price, row.fee, row.tax)
            db.add(
                SecurityTransaction(
                    security_id=security.id,
                    date=row.date,
                    side=SecuritySide.BUY,
                    shares=row.shares,
                    price_per_share=row.price,
                    fee=row.fee,
                    tax=row.tax,
                    total=total,
                )
            )
            sec_report.transactions_new += 1
        report.securities.append(sec_report)

    return report
