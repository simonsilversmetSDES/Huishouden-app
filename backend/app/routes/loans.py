"""Lening & woning-endpoints (spec §8).

Eén gedeelde woonlening: GET geeft het volledige overzicht (params, aflossingstabel,
KPI's, woningwaardering, eigendomsverdeling); PUT maakt of werkt de lening bij,
inclusief de lijst investeringen en de eigen inbreng per persoon (wholesale
vervangen — de UI stuurt telkens de volledige set)."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context, Loan, LoanContribution, PropertyInvestment
from app.schemas.loans import LoanIn, LoanOverviewOut
from app.services.budget import from_cents
from app.services.loans import build_loan_overview

router = APIRouter(prefix="/api/loan", tags=["loan"])


def _get_loan(db: Session) -> Loan | None:
    """De (enige) woonlening; None als er nog geen is."""
    return db.scalars(select(Loan).order_by(Loan.id)).first()


def _rate(value: str, field: str) -> Decimal:
    bad = status.HTTP_422_UNPROCESSABLE_CONTENT
    try:
        rate = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(bad, detail=f"Ongeldige {field}") from exc
    if rate < 0:
        raise HTTPException(bad, detail=f"{field} mag niet negatief zijn")
    return rate


def _apply(db: Session, loan: Loan, body: LoanIn) -> None:
    loan.name = body.name
    loan.principal = from_cents(body.principal_cents)
    loan.annual_rate = _rate(body.annual_rate, "rente")
    loan.term_months = body.term_months
    loan.start_date = body.start_date
    loan.monthly_payment = (
        from_cents(body.monthly_payment_cents) if body.monthly_payment_cents is not None else None
    )
    loan.property_value_paid = (
        from_cents(body.property_value_paid_cents)
        if body.property_value_paid_cents is not None
        else None
    )
    loan.property_base_value = (
        from_cents(body.property_base_value_cents)
        if body.property_base_value_cents is not None
        else None
    )
    loan.property_base_year = body.property_base_year
    loan.indexation_rate = (
        _rate(body.indexation_rate, "indexatie") if body.indexation_rate is not None else None
    )
    loan.investments = [
        PropertyInvestment(
            label=inv.label,
            comment=inv.comment,
            added_value=from_cents(inv.added_value_cents),
        )
        for inv in body.investments
    ]
    loan.contributions = [
        LoanContribution(context_id=c.context_id, amount=from_cents(c.amount_cents))
        for c in body.contributions
    ]


@router.get("", response_model=LoanOverviewOut)
def get_loan(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> LoanOverviewOut:
    loan = _get_loan(db)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Nog geen lening ingesteld")
    return build_loan_overview(db, loan)


@router.put("", response_model=LoanOverviewOut)
def upsert_loan(
    body: LoanIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> LoanOverviewOut:
    loan = _get_loan(db)
    if loan is None:
        # Nieuwe lening staat op de gedeelde context "Gemeenschappelijk".
        context = db.scalars(select(Context).where(Context.name == "Gemeenschappelijk")).first()
        if context is None:
            context = db.scalars(select(Context).order_by(Context.id)).first()
        if context is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Geen context beschikbaar")
        loan = Loan(context_id=context.id)
        db.add(loan)
    _apply(db, loan, body)
    db.commit()
    db.refresh(loan)
    return build_loan_overview(db, loan)
