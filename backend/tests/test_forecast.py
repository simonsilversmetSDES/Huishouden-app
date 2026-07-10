"""Vermogensforecast ("Status balans" uit de Excel): kettingberekening per maand.

Referentiekettingen zijn handmatig doorgerekend. Startpunt is telkens de laatst
gekende werkelijke balans (net-worth-snapshots); daarna keten de formules maand
per maand door, zoals de forecast-kolommen in het Excel-werkblad.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Context, Loan, NetWorthSnapshot
from app.models.enums import AssetClass
from app.schemas.forecast import ForecastFormulaIn
from app.services.forecast import (
    DEFAULT_FORMULAS,
    build_forecast_matrix,
    build_forecast_net_worth,
    upsert_formula,
)
from app.services.forecast_formula import FormulaError

TODAY = date(2025, 9, 15)


def _context(db: Session, name: str) -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _snap(db: Session, context_id: int, on: date, asset_class: AssetClass, amount: str) -> None:
    db.add(
        NetWorthSnapshot(
            context_id=context_id,
            snapshot_date=on,
            asset_class=asset_class,
            value=Decimal(amount),
        )
    )
    db.commit()


def _budget(
    db: Session, context_id: int, category_name: str, year: int, month: int, amount: str
) -> None:
    category = db.scalars(
        select(Category).where(
            Category.context_id == context_id, Category.name == category_name
        )
    ).one()
    db.add(Budget(category_id=category.id, year=year, month=month, amount=Decimal(amount)))
    db.commit()


def _row(matrix, asset_class: AssetClass):
    return next(r for r in matrix.rows if r.asset_class == asset_class)


class TestContantMetSpaarbudget:
    def test_ketting_en_werkelijke_cellen(self, seeded_db: Session) -> None:
        """Excel: contant = vorige + budget("Spaarrekening"); lege budgetcel telt als 0."""
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.CONTANT, "1000")
        _budget(seeded_db, simon.id, "Spaarrekening", 2025, 10, "400")
        _budget(seeded_db, simon.id, "Spaarrekening", 2025, 11, "300")

        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        assert matrix.last_actual_month == date(2025, 9, 1)

        row = _row(matrix, AssetClass.CONTANT)
        assert row.formula == DEFAULT_FORMULAS[AssetClass.CONTANT]
        assert row.is_default
        # jan-aug: werkelijk maar zonder waarde (blanco)
        assert [c.kind for c in row.cells[:9]] == ["werkelijk"] * 9
        assert [c.value_cents for c in row.cells[:8]] == [None] * 8
        assert row.cells[8].value_cents == 100_000  # sep, werkelijk
        # okt/nov/dec: 1000+400=1400, +300=1700, +0=1700
        assert [(c.kind, c.value_cents) for c in row.cells[9:]] == [
            ("forecast", 140_000),
            ("forecast", 170_000),
            ("forecast", 170_000),
        ]


class TestVasteStapEnConstant:
    def test_groepsverzekering_plus_100(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.GROEPSVERZEKERING, "5000")
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.GROEPSVERZEKERING)
        assert [c.value_cents for c in row.cells[9:]] == [510_000, 520_000, 530_000]

    def test_aandelen_constant_met_carry_forward_start(self, seeded_db: Session) -> None:
        """Aandelen: 'vorige'. Startwaarde komt uit een oudere maand (carry-forward)
        wanneer de laatste werkelijke maand die klasse niet bevat."""
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 6, 1), AssetClass.AANDELEN, "500")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.CONTANT, "1000")
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.AANDELEN)
        assert row.cells[5].value_cents == 50_000  # jun: werkelijk
        assert row.cells[8].value_cents is None  # sep: geen waarde die maand (blanco)
        assert [c.value_cents for c in row.cells[9:]] == [50_000] * 3


class TestWoningMetLening:
    def test_halve_kapitaalaflossing(self, seeded_db: Session) -> None:
        """Excel: woning = vorige + kapitaalaflossing/2. Lening zonder rente met
        maandlast 100 ⇒ kapitaal 100/maand ⇒ +50/maand."""
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        seeded_db.add(
            Loan(
                context_id=gem.id,
                name="Woonkrediet",
                principal=Decimal("1200"),
                annual_rate=Decimal("0"),
                term_months=12,
                start_date=date(2025, 1, 1),
                monthly_payment=Decimal("100"),
            )
        )
        seeded_db.commit()
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.WONING, "10000")
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.WONING)
        assert [c.value_cents for c in row.cells[9:]] == [1_005_000, 1_010_000, 1_015_000]


class TestJaargrens:
    def test_ketting_loopt_over_de_jaargrens(self, seeded_db: Session) -> None:
        """Laatste werkelijke maand nov 2025, matrix 2026: december 2025 wordt
        doorgerekend (niet getoond) en telt mee in januari 2026."""
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 11, 1), AssetClass.CONTANT, "1000")
        _budget(seeded_db, simon.id, "Spaarrekening", 2025, 12, "100")
        _budget(seeded_db, simon.id, "Spaarrekening", 2026, 1, "200")

        matrix = build_forecast_matrix(seeded_db, simon, 2026, today=date(2025, 11, 20))
        row = _row(matrix, AssetClass.CONTANT)
        assert row.cells[0].kind == "forecast"
        assert row.cells[0].value_cents == 130_000  # 1000 + 100 (dec) + 200 (jan)
        assert row.cells[11].value_cents == 130_000  # geen verdere budgetten


class TestFormuleBeheer:
    def test_rijformule_en_celoverride(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.GROEPSVERZEKERING, "100")
        upsert_formula(
            seeded_db,
            ForecastFormulaIn(
                context_id=simon.id,
                asset_class=AssetClass.GROEPSVERZEKERING,
                formula="vorige + 1",
            ),
        )
        upsert_formula(
            seeded_db,
            ForecastFormulaIn(
                context_id=simon.id,
                asset_class=AssetClass.GROEPSVERZEKERING,
                year=2025,
                month=11,
                formula="vorige + 10",
            ),
        )
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.GROEPSVERZEKERING)
        assert row.formula == "vorige + 1"
        assert not row.is_default
        # okt 101, nov 111 (override), dec 112 (weer rijformule)
        assert [c.value_cents for c in row.cells[9:]] == [10_100, 11_100, 11_200]
        assert [c.override for c in row.cells[9:]] == [False, True, False]

    def test_lege_formule_wist_terug_naar_default(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        item = ForecastFormulaIn(
            context_id=simon.id,
            asset_class=AssetClass.GROEPSVERZEKERING,
            formula="vorige + 999",
        )
        upsert_formula(seeded_db, item)
        upsert_formula(seeded_db, item.model_copy(update={"formula": "  "}))
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.GROEPSVERZEKERING)
        assert row.is_default
        assert row.formula == DEFAULT_FORMULAS[AssetClass.GROEPSVERZEKERING]

    def test_ongeldige_formule_geweigerd(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        with pytest.raises(FormulaError):
            upsert_formula(
                seeded_db,
                ForecastFormulaIn(
                    context_id=simon.id,
                    asset_class=AssetClass.CONTANT,
                    formula="vorige +",
                ),
            )

    def test_jaar_zonder_maand_geweigerd(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        with pytest.raises(ValueError, match="maand"):
            upsert_formula(
                seeded_db,
                ForecastFormulaIn(
                    context_id=simon.id,
                    asset_class=AssetClass.CONTANT,
                    year=2025,
                    formula="vorige",
                ),
            )


class TestFoutenEnWarnings:
    def test_fout_propageert_naar_latere_maanden(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.CONTANT, "1000")
        upsert_formula(
            seeded_db,
            ForecastFormulaIn(
                context_id=simon.id, asset_class=AssetClass.CONTANT, formula="vorige / 0"
            ),
        )
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.CONTANT)
        assert [c.kind for c in row.cells[9:]] == ["error"] * 3
        assert [c.value_cents for c in row.cells[9:]] == [None] * 3
        assert "Deling door nul" in (row.cells[9].error or "")
        # totaalrij kleurt mee
        assert matrix.totals[9].kind == "error"

    def test_onbestaande_categorie_geeft_warning_geen_fout(self, seeded_db: Session) -> None:
        """'Pensioensparen' bestaat niet als seed-categorie: waarde blijft staan,
        de rij krijgt een warning."""
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.PENSIOENSPAREN, "200")
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        row = _row(matrix, AssetClass.PENSIOENSPAREN)
        assert [c.value_cents for c in row.cells[9:]] == [20_000] * 3
        assert any("Pensioensparen" in w for w in row.warnings)


class TestTotalen:
    def test_totaalrij_sommeert_forecast(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.CONTANT, "1000")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.GROEPSVERZEKERING, "5000")
        _budget(seeded_db, simon.id, "Spaarrekening", 2025, 10, "400")
        matrix = build_forecast_matrix(seeded_db, simon, 2025, today=TODAY)
        assert matrix.totals[8].value_cents == 600_000  # sep werkelijk
        assert matrix.totals[8].kind == "werkelijk"
        # okt: contant 1400 + groeps 5100 = 6500
        assert matrix.totals[9].value_cents == 650_000
        assert matrix.totals[9].kind == "forecast"


class TestForecastNetWorth:
    def test_combined_met_verschillende_startmaanden(self, seeded_db: Session) -> None:
        """Simon eindigt in sep, Jozefien in aug: Jozefien wordt tot sep doorgerekend
        zodat het verbindingspunt (sep) beide bevat; daarna maandelijks sommeren."""
        simon = _context(seeded_db, "Simon")
        jozefien = _context(seeded_db, "Jozefien")
        _snap(seeded_db, simon.id, date(2025, 9, 1), AssetClass.CONTANT, "1000")
        _snap(seeded_db, jozefien.id, date(2025, 8, 1), AssetClass.CONTANT, "500")
        for month in (10, 11, 12):
            _budget(seeded_db, simon.id, "Spaarrekening", 2025, month, "400")
        for month in (9, 10, 11, 12):
            _budget(seeded_db, jozefien.id, "Spaarrekening", 2025, month, "100")
        # Groepsverzekering groeit standaard +100/maand (ook vanaf 0, zoals in de
        # Excel); op 'vorige' zetten zodat enkel contant de totalen bepaalt.
        for ctx in (simon, jozefien):
            upsert_formula(
                seeded_db,
                ForecastFormulaIn(
                    context_id=ctx.id,
                    asset_class=AssetClass.GROEPSVERZEKERING,
                    formula="vorige",
                ),
            )

        out = build_forecast_net_worth(seeded_db, [simon, jozefien], today=TODAY)
        assert [r.snapshot_date for r in out.rows] == [
            date(2025, m, 1) for m in (9, 10, 11, 12)
        ]
        # sep: Simon werkelijk 1000 + Jozefien doorgerekend 500+100=600
        assert out.rows[0].total_cents == 160_000
        # okt: 1400 + 700, nov: 1800 + 800, dec: 2200 + 900
        assert [r.total_cents for r in out.rows[1:]] == [210_000, 260_000, 310_000]

    def test_zonder_data_geen_rijen(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        out = build_forecast_net_worth(seeded_db, [simon], today=TODAY)
        assert out.rows == []


class TestForecastApi:
    """Routes; de rekenreferenties zitten in de service-tests hierboven."""

    def test_vereist_login(self, client) -> None:
        params = {"context_id": 1, "year": 2025}
        assert client.get("/api/forecast", params=params).status_code == 401
        assert client.put("/api/forecast/formulas", json={}).status_code == 401
        assert client.get("/api/forecast/net-worth", params={"context_ids": 1}).status_code == 401

    def test_matrix_en_formule_upsert(self, logged_in, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        year = date.today().year

        resp = logged_in.put(
            "/api/forecast/formulas",
            json={"context_id": simon.id, "asset_class": "groepsverzekering",
                  "formula": "vorige + 5"},
        )
        assert resp.status_code == 204

        resp = logged_in.get("/api/forecast", params={"context_id": simon.id, "year": year})
        assert resp.status_code == 200
        matrix = resp.json()
        assert matrix["year"] == year
        assert [r["asset_class"] for r in matrix["rows"]] == [
            "contant", "etf_fondsen", "pensioensparen", "groepsverzekering",
            "woning", "aandelen", "bitcoin",
        ]
        groeps = next(r for r in matrix["rows"] if r["asset_class"] == "groepsverzekering")
        assert groeps["formula"] == "vorige + 5"
        assert groeps["is_default"] is False
        assert len(groeps["cells"]) == 12
        assert len(matrix["totals"]) == 12

    def test_ongeldige_formule_422(self, logged_in, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        resp = logged_in.put(
            "/api/forecast/formulas",
            json={"context_id": simon.id, "asset_class": "contant", "formula": "vorige +"},
        )
        assert resp.status_code == 422
        assert "verwacht" in resp.json()["detail"]

    def test_onbekende_context_404(self, logged_in) -> None:
        assert (
            logged_in.get("/api/forecast", params={"context_id": 999, "year": 2025}).status_code
            == 404
        )
        resp = logged_in.put(
            "/api/forecast/formulas",
            json={"context_id": 999, "asset_class": "contant", "formula": "vorige"},
        )
        assert resp.status_code == 404

    def test_net_worth_forecast_meerdere_contexten(
        self, logged_in, seeded_db: Session
    ) -> None:
        simon = _context(seeded_db, "Simon")
        jozefien = _context(seeded_db, "Jozefien")
        current_month = date.today().replace(day=1)
        _snap(seeded_db, simon.id, current_month, AssetClass.CONTANT, "1000")
        resp = logged_in.get(
            "/api/forecast/net-worth",
            params={"context_ids": [simon.id, jozefien.id]},
        )
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        assert rows[0]["snapshot_date"] == current_month.isoformat()
        # verbindingspunt + forecast t/m december van het huidige jaar
        assert len(rows) == 12 - current_month.month + 1
