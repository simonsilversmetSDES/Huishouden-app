"""Lening & woning-schemas (spec §8).

Geld gaat als integer-centen over de draad; rente en indexatie als exacte
Decimal-string (bv. "0.0251"). De aflossingstabel en KPI's worden berekend uit
de leningparameters (niet opgeslagen)."""

from datetime import date

from pydantic import BaseModel


class InvestmentIn(BaseModel):
    label: str
    comment: str | None = None  # bv. "50% van de aankoopprijs van de keuken"
    added_value_cents: int


class InvestmentOut(InvestmentIn):
    id: int


class ContributionIn(BaseModel):
    context_id: int
    amount_cents: int


class ContributionOut(ContributionIn):
    id: int
    context_name: str


class LoanIn(BaseModel):
    name: str
    principal_cents: int
    annual_rate: str
    term_months: int
    start_date: date
    monthly_payment_cents: int | None = None  # None = berekenen via annuïteit
    property_value_paid_cents: int | None = None
    property_base_value_cents: int | None = None
    property_base_year: int | None = None
    indexation_rate: str | None = None
    investments: list[InvestmentIn] = []
    contributions: list[ContributionIn] = []


class LoanOut(BaseModel):
    id: int
    context_id: int
    name: str
    principal_cents: int
    annual_rate: str
    term_months: int
    start_date: date
    monthly_payment_cents: int | None  # None = berekend (zie kpis.monthly_payment_cents)
    property_value_paid_cents: int | None
    property_base_value_cents: int | None
    property_base_year: int | None
    indexation_rate: str | None
    investments: list[InvestmentOut]
    contributions: list[ContributionOut]


class ScheduleRowOut(BaseModel):
    n: int  # 1-gebaseerde maandindex
    date: date
    payment_cents: int
    interest_cents: int
    principal_cents: int
    balance_cents: int  # saldo na deze betaling
    paid: bool  # datum ≤ vandaag


class LoanKpisOut(BaseModel):
    monthly_payment_cents: int  # effectieve maandlast (ingesteld of berekend)
    total_payment_cents: int
    total_principal_cents: int
    total_interest_cents: int
    end_date: date
    remaining_months: int  # aantal toekomstige aflossingen
    remaining_label: str  # bv. "13 jaar en 3 maanden"
    elapsed_pct: float
    outstanding_cents: int  # huidig openstaand saldo
    principal_paid_pct: float  # afgelost kapitaal / geleend bedrag
    paid_payment_cents: int  # totaal afbetaald tot vandaag
    paid_principal_cents: int
    paid_interest_cents: int
    paid_payment_pct: float
    paid_principal_pct: float
    paid_interest_pct: float


class PropertyValuationOut(BaseModel):
    estimate_cents: int  # schatting incl. meerwaarde
    price_paid_cents: int
    surplus_cents: int  # meerwaarde = schatting − betaalde prijs
    surplus_pct: float | None
    investments_total_cents: int
    indexed_value_cents: int  # geïndexeerde basiswaarde voor het huidige jaar


class OwnerShareOut(BaseModel):
    context_id: int
    name: str
    contribution_cents: int
    equity_incl_surplus_cents: int  # inbreng + meerwaarde/n + afgelost kapitaal/n
    equity_excl_surplus_cents: int  # inbreng + afgelost kapitaal/n


class OwnershipOut(BaseModel):
    remaining_after_loan_cents: int  # betaalde prijs − geleend bedrag
    principal_paid_cents: int  # afgelost kapitaal tot vandaag
    surplus_cents: int
    owners: list[OwnerShareOut]
    total_excl_surplus_cents: int
    our_share_pct: float | None  # totaal excl. meerwaarde / betaalde prijs


class LoanOverviewOut(BaseModel):
    loan: LoanOut
    kpis: LoanKpisOut
    valuation: PropertyValuationOut | None
    ownership: OwnershipOut | None
    schedule: list[ScheduleRowOut]
