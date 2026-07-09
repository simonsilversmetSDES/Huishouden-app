"""Lening & woning-rekenlogica (spec §8, tests-first).

Referentiewaarden uit de Excel (§10):
- annuïteit jaar 1: intrest € 5.993,93 / kapitaal € 13.584,31; saldo € 231.415,69;
- totaal intrest € 49.386,80 / totaal kapitaal € 244.286,80; einddatum 05/09/2039;
- woningschatting € 400.485,50 bij 1,5 % indexatie (2026); meerwaarde −€ 114,50;
- eigendomsaandeel op 02/07/2026 = 44,83 %.
Alle bedragen met de manuele maandlast € 1.631,52.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Context, Loan, LoanContribution, PropertyInvestment
from app.services.loans import (
    amortization_schedule,
    build_loan_overview,
    effective_monthly_payment,
)


def _ctx(db: Session, name: str) -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _loan(
    db: Session,
    *,
    monthly_payment: str | None = "1631.52",
    with_woning: bool = False,
    with_owners: bool = False,
) -> Loan:
    loan = Loan(
        context_id=_ctx(db, "Gemeenschappelijk").id,
        name="Woonlening",
        principal=Decimal("245000"),
        annual_rate=Decimal("0.0251"),
        term_months=180,
        start_date=date(2024, 10, 5),
        monthly_payment=Decimal(monthly_payment) if monthly_payment else None,
    )
    if with_woning:
        loan.property_value_paid = Decimal("400600")
        loan.property_base_value = Decimal("380000")
        loan.property_base_year = 2024
        loan.indexation_rate = Decimal("0.015")
        loan.investments = [
            PropertyInvestment(label="Keuken", added_value=Decimal("7000")),
            PropertyInvestment(label="Tuinhuis", added_value=Decimal("2000")),
        ]
    if with_owners:
        loan.contributions = [
            LoanContribution(context_id=_ctx(db, "Simon").id, amount=Decimal("85769")),
            LoanContribution(context_id=_ctx(db, "Jozefien").id, amount=Decimal("69831")),
        ]
    db.add(loan)
    db.commit()
    return loan


class TestMaandlast:
    def test_manueel(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db)
        assert effective_monthly_payment(loan) == Decimal("1631.52")

    def test_berekend_annuiteit(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db, monthly_payment=None)
        # Excel D12 = (P·(r·(1+r)^jaren)/((1+r)^jaren−1))/12
        assert float(effective_monthly_payment(loan)) == pytest.approx(1650.1951, abs=1e-3)


class TestAflossingstabel:
    def test_referentiewaarden(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db)
        rows = amortization_schedule(loan, today=date(2050, 1, 1))

        assert len(rows) == 180
        assert rows[-1].date == date(2039, 9, 5)
        assert float(rows[0].interest) == pytest.approx(512.4583, abs=1e-3)

        jaar1_intrest = sum(r.interest for r in rows[:12])
        jaar1_kapitaal = sum(r.principal for r in rows[:12])
        assert float(jaar1_intrest) == pytest.approx(5993.9313, abs=1e-2)
        assert float(jaar1_kapitaal) == pytest.approx(13584.3087, abs=1e-2)
        assert float(rows[11].balance) == pytest.approx(231415.6913, abs=1e-2)

        assert float(sum(r.interest for r in rows)) == pytest.approx(49386.8009, abs=1e-2)
        assert float(sum(r.principal for r in rows)) == pytest.approx(244286.7991, abs=1e-2)

    def test_betaald_vlag_splitst_op_vandaag(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db)
        rows = amortization_schedule(loan, today=date(2026, 7, 2))
        paid = [r for r in rows if r.paid]
        # 2024-10-05 t.e.m. 2026-06-05 = 21 betalingen; 2026-07-05 valt na vandaag
        assert len(paid) == 21
        assert paid[-1].date == date(2026, 6, 5)
        assert float(paid[-1].balance) == pytest.approx(221001.58, abs=1e-2)


class TestKpis:
    def test_kpis_op_vaste_datum(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db, with_woning=True, with_owners=True)
        ov = build_loan_overview(seeded_db, loan, today=date(2026, 7, 2))
        k = ov.kpis
        assert k.monthly_payment_cents == 163152
        assert k.end_date == date(2039, 9, 5)
        assert k.remaining_months == 159
        assert k.remaining_label == "13 jaar en 3 maanden"
        assert k.outstanding_cents / 100 == pytest.approx(221001.58, abs=0.01)
        assert k.total_interest_cents / 100 == pytest.approx(49386.80, abs=0.01)
        assert k.paid_principal_cents / 100 == pytest.approx(23998.42, abs=0.01)


class TestWoningwaardering:
    def test_schatting_en_meerwaarde(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db, with_woning=True)
        ov = build_loan_overview(seeded_db, loan, today=date(2026, 7, 2))
        v = ov.valuation
        assert v is not None
        assert v.investments_total_cents == 900000
        # 380000 × 1,015^(2026−2024) + 9000 = 391485,50 + 9000 = 400485,50
        assert v.estimate_cents / 100 == pytest.approx(400485.50, abs=0.01)
        assert v.surplus_cents / 100 == pytest.approx(-114.50, abs=0.01)


class TestEigendom:
    def test_verdeling_en_aandeel(self, seeded_db: Session) -> None:
        loan = _loan(seeded_db, with_woning=True, with_owners=True)
        ov = build_loan_overview(seeded_db, loan, today=date(2026, 7, 2))
        o = ov.ownership
        assert o is not None
        assert o.remaining_after_loan_cents == (40060000 - 24500000)
        by_name = {owner.name: owner for owner in o.owners}
        # Simon: inbreng 85769 + kapitaal/2 (excl.), + meerwaarde/2 (incl.).
        # Tolerantie 2 cent: to_cents kapt af waar de Excel afrondt (de /2-deling
        # levert een halve cent op) — een rondingsverschil, geen rekenfout.
        assert by_name["Simon"].equity_excl_surplus_cents / 100 == pytest.approx(97768.21, abs=0.02)
        assert by_name["Simon"].equity_incl_surplus_cents / 100 == pytest.approx(97710.96, abs=0.02)
        jozefien = by_name["Jozefien"].equity_excl_surplus_cents / 100
        assert jozefien == pytest.approx(81830.21, abs=0.02)
        assert o.our_share_pct == pytest.approx(0.44832, abs=1e-4)


class TestRoutes:
    def test_get_zonder_lening_404(self, logged_in: TestClient) -> None:
        assert logged_in.get("/api/loan").status_code == 404

    def test_upsert_en_ophalen(self, logged_in: TestClient, seeded_db: Session) -> None:
        simon = _ctx(seeded_db, "Simon").id
        jozefien = _ctx(seeded_db, "Jozefien").id
        body = {
            "name": "Woonlening",
            "principal_cents": 24500000,
            "annual_rate": "0.0251",
            "term_months": 180,
            "start_date": "2024-10-05",
            "monthly_payment_cents": 163152,
            "property_value_paid_cents": 40060000,
            "property_base_value_cents": 38000000,
            "property_base_year": 2024,
            "indexation_rate": "0.015",
            "investments": [
                {
                    "label": "Keuken",
                    "comment": "50% van de aankoopprijs van de keuken",
                    "added_value_cents": 700000,
                }
            ],
            "contributions": [
                {"context_id": simon, "amount_cents": 8576900},
                {"context_id": jozefien, "amount_cents": 6983100},
            ],
        }
        resp = logged_in.put("/api/loan", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["end_date"] == "2039-09-05"
        assert len(data["schedule"]) == 180
        assert data["valuation"] is not None
        assert len(data["ownership"]["owners"]) == 2
        inv = data["loan"]["investments"][0]
        assert inv["comment"] == "50% van de aankoopprijs van de keuken"

        # Tweede keer = update (geen tweede lening), investeringen wholesale vervangen
        body["investments"] = []
        again = logged_in.put("/api/loan", json=body)
        assert again.status_code == 200
        assert again.json()["loan"]["investments"] == []
        assert logged_in.get("/api/loan").status_code == 200

    def test_ongeldige_rente_422(self, logged_in: TestClient) -> None:
        body = {
            "name": "X",
            "principal_cents": 100000,
            "annual_rate": "abc",
            "term_months": 120,
            "start_date": "2024-01-01",
        }
        assert logged_in.put("/api/loan", json=body).status_code == 422
