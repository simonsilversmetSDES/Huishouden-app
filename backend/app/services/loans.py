"""Lening & woning-rekenlogica (spec §8).

De aflossingstabel wordt berekend uit de leningparameters (niet opgeslagen):
per maand `intrest = saldo × rente/12`, `kapitaal = maandlast − intrest`,
`saldo = vorig saldo − kapitaal`. Alle tussenstappen in volle Decimal-precisie;
pas aan de API-rand naar centen (net als de Excel, die intern op float rekent).

KPI's splitsen de tabel op "vandaag": betaalde rijen (datum ≤ vandaag) voeden
"totaal afbetaald" en het openstaande saldo; toekomstige rijen de resterende
looptijd. De woningwaardering indexeert de basiswaarde en telt de meerwaarde uit
investeringen erbij; de eigendomsverdeling verdeelt meerwaarde en afgelost
kapitaal gelijk over de inbrengers en telt ieders eigen inbreng erbij.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, Loan
from app.schemas.loans import (
    ContributionOut,
    InvestmentOut,
    LoanKpisOut,
    LoanOut,
    LoanOverviewOut,
    OwnerShareOut,
    OwnershipOut,
    PropertyValuationOut,
    ScheduleRowOut,
)
from app.services.budget import ZERO, to_cents

TWELVE = Decimal(12)


@dataclass
class ScheduleRow:
    n: int
    date: date
    payment: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal  # saldo na deze betaling
    paid: bool


def _add_months(start: date, months: int) -> date:
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def effective_monthly_payment(loan: Loan) -> Decimal:
    """De ingestelde maandlast, of anders de berekende annuïteit (Excel-formule:
    jaarlijkse rente en looptijd in jaren, gedeeld door 12)."""
    if loan.monthly_payment is not None:
        return loan.monthly_payment
    r = loan.annual_rate
    years = Decimal(loan.term_months) / TWELVE
    exponent = int(years) if years == years.to_integral_value() else years
    factor = (Decimal(1) + r) ** exponent
    return loan.principal * (r * factor) / (factor - 1) / TWELVE


def amortization_schedule(loan: Loan, today: date) -> list[ScheduleRow]:
    payment = effective_monthly_payment(loan)
    rate_monthly = loan.annual_rate / TWELVE
    balance = loan.principal
    rows: list[ScheduleRow] = []
    for i in range(loan.term_months):
        due = _add_months(loan.start_date, i)
        interest = balance * rate_monthly
        principal = payment - interest
        balance = balance - principal
        rows.append(
            ScheduleRow(
                n=i + 1,
                date=due,
                payment=payment,
                interest=interest,
                principal=principal,
                balance=balance,
                paid=due <= today,
            )
        )
    return rows


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _kpis(loan: Loan, rows: list[ScheduleRow], today: date) -> LoanKpisOut:
    paid = [r for r in rows if r.paid]
    total_payment = sum((r.payment for r in rows), ZERO)
    total_principal = sum((r.principal for r in rows), ZERO)
    total_interest = sum((r.interest for r in rows), ZERO)
    paid_payment = sum((r.payment for r in paid), ZERO)
    paid_principal = sum((r.principal for r in paid), ZERO)
    paid_interest = sum((r.interest for r in paid), ZERO)
    outstanding = paid[-1].balance if paid else loan.principal
    end_date = rows[-1].date
    remaining = len(rows) - len(paid)
    years_total = Decimal(loan.term_months) / TWELVE
    elapsed = 1 - ((end_date - today).days / 365) / float(years_total) if years_total else 0.0
    return LoanKpisOut(
        monthly_payment_cents=to_cents(effective_monthly_payment(loan)),
        total_payment_cents=to_cents(total_payment),
        total_principal_cents=to_cents(total_principal),
        total_interest_cents=to_cents(total_interest),
        end_date=end_date,
        remaining_months=remaining,
        remaining_label=f"{remaining // 12} jaar en {remaining % 12} maanden",
        elapsed_pct=elapsed,
        outstanding_cents=to_cents(outstanding),
        principal_paid_pct=_pct(paid_principal, loan.principal),
        paid_payment_cents=to_cents(paid_payment),
        paid_principal_cents=to_cents(paid_principal),
        paid_interest_cents=to_cents(paid_interest),
        paid_payment_pct=_pct(paid_payment, total_payment),
        paid_principal_pct=_pct(paid_principal, total_principal),
        paid_interest_pct=_pct(paid_interest, total_interest),
    )


def _indexed_value(loan: Loan, year: int) -> Decimal | None:
    if loan.property_base_value is None:
        return None
    rate = loan.indexation_rate or ZERO
    base_year = loan.property_base_year if loan.property_base_year is not None else year
    return loan.property_base_value * (Decimal(1) + rate) ** (year - base_year)


def _valuation_decimals(
    loan: Loan, today: date
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    """(schatting, geïndexeerde basiswaarde, som investeringen, betaalde prijs)."""
    indexed = _indexed_value(loan, today.year)
    if indexed is None or loan.property_value_paid is None:
        return None
    investments_total = sum((inv.added_value for inv in loan.investments), ZERO)
    estimate = indexed + investments_total
    return estimate, indexed, investments_total, loan.property_value_paid


def _valuation_out(loan: Loan, today: date) -> PropertyValuationOut | None:
    result = _valuation_decimals(loan, today)
    if result is None:
        return None
    estimate, indexed, investments_total, price_paid = result
    surplus = estimate - price_paid
    return PropertyValuationOut(
        estimate_cents=to_cents(estimate),
        price_paid_cents=to_cents(price_paid),
        surplus_cents=to_cents(surplus),
        surplus_pct=_pct(surplus, price_paid) if price_paid else None,
        investments_total_cents=to_cents(investments_total),
        indexed_value_cents=to_cents(indexed),
    )


def _ownership_out(
    db: Session, loan: Loan, rows: list[ScheduleRow], today: date
) -> OwnershipOut | None:
    valuation = _valuation_decimals(loan, today)
    if not loan.contributions or valuation is None:
        return None
    estimate, _indexed, _inv, price_paid = valuation
    surplus = estimate - price_paid
    paid_principal = sum((r.principal for r in rows if r.paid), ZERO)
    n = len(loan.contributions)
    names = {
        c.id: c.name for c in db.scalars(select(Context))
    }
    owners: list[OwnerShareOut] = []
    total_excl = ZERO
    for contribution in loan.contributions:
        excl = contribution.amount + paid_principal / n
        incl = excl + surplus / n
        total_excl += excl
        owners.append(
            OwnerShareOut(
                context_id=contribution.context_id,
                name=names.get(contribution.context_id, "?"),
                contribution_cents=to_cents(contribution.amount),
                equity_incl_surplus_cents=to_cents(incl),
                equity_excl_surplus_cents=to_cents(excl),
            )
        )
    return OwnershipOut(
        remaining_after_loan_cents=to_cents(price_paid - loan.principal),
        principal_paid_cents=to_cents(paid_principal),
        surplus_cents=to_cents(surplus),
        owners=owners,
        total_excl_surplus_cents=to_cents(total_excl),
        our_share_pct=_pct(total_excl, price_paid) if price_paid else None,
    )


def loan_out(db: Session, loan: Loan) -> LoanOut:
    names = {c.id: c.name for c in db.scalars(select(Context))}
    return LoanOut(
        id=loan.id,
        context_id=loan.context_id,
        name=loan.name,
        principal_cents=to_cents(loan.principal),
        annual_rate=str(loan.annual_rate),
        term_months=loan.term_months,
        start_date=loan.start_date,
        monthly_payment_cents=to_cents(loan.monthly_payment)
        if loan.monthly_payment is not None
        else None,
        property_value_paid_cents=to_cents(loan.property_value_paid)
        if loan.property_value_paid is not None
        else None,
        property_base_value_cents=to_cents(loan.property_base_value)
        if loan.property_base_value is not None
        else None,
        property_base_year=loan.property_base_year,
        indexation_rate=str(loan.indexation_rate) if loan.indexation_rate is not None else None,
        investments=[
            InvestmentOut(
                id=inv.id,
                label=inv.label,
                comment=inv.comment,
                added_value_cents=to_cents(inv.added_value),
            )
            for inv in loan.investments
        ],
        contributions=[
            ContributionOut(
                id=c.id,
                context_id=c.context_id,
                amount_cents=to_cents(c.amount),
                context_name=names.get(c.context_id, "?"),
            )
            for c in loan.contributions
        ],
    )


def build_loan_overview(db: Session, loan: Loan, today: date | None = None) -> LoanOverviewOut:
    if today is None:
        today = date.today()
    rows = amortization_schedule(loan, today)
    return LoanOverviewOut(
        loan=loan_out(db, loan),
        kpis=_kpis(loan, rows, today),
        valuation=_valuation_out(loan, today),
        ownership=_ownership_out(db, loan, rows, today),
        schedule=[
            ScheduleRowOut(
                n=r.n,
                date=r.date,
                payment_cents=to_cents(r.payment),
                interest_cents=to_cents(r.interest),
                principal_cents=to_cents(r.principal),
                balance_cents=to_cents(r.balance),
                paid=r.paid,
            )
            for r in rows
        ],
    )


def woning_equity_by_context(db: Session, today: date) -> dict[int, Decimal]:
    """Netto woning-equity (incl. meerwaarde) per context (spec §8/§9), zodat de
    vermogensbalans de 'woning'-activaklasse per persoon automatisch kan voeden."""
    equity: dict[int, Decimal] = {}
    for loan in db.scalars(select(Loan)):
        valuation = _valuation_decimals(loan, today)
        if not loan.contributions or valuation is None:
            continue
        estimate, _indexed, _inv, price_paid = valuation
        surplus = estimate - price_paid
        rows = amortization_schedule(loan, today)
        paid_principal = sum((r.principal for r in rows if r.paid), ZERO)
        n = len(loan.contributions)
        for contribution in loan.contributions:
            share = contribution.amount + surplus / n + paid_principal / n
            equity[contribution.context_id] = equity.get(contribution.context_id, ZERO) + share
    return equity
