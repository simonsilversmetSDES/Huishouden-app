"""Formule-DSL voor de vermogensforecast: parser en evaluator.

De formules komen 1-op-1 uit het Excel-werkblad "Status balans"
(bv. `vorige + budget("Spaarrekening")`, `vorige + kapitaalaflossing / 2`).
Alle rekenwerk in Decimal — nooit float.
"""

from decimal import Decimal

import pytest

from app.services.forecast_formula import (
    MAX_FORMULA_LENGTH,
    EvalContext,
    FormulaError,
    evaluate_formula,
    validate_formula,
)


def ctx(
    vorige: str = "0",
    kapitaalaflossing: str = "0",
    budgets: dict[str, str] | None = None,
) -> EvalContext:
    table = {name: Decimal(value) for name, value in (budgets or {}).items()}
    return EvalContext(
        vorige=Decimal(vorige),
        kapitaalaflossing=Decimal(kapitaalaflossing),
        budget_lookup=table.get,
        warnings=[],
    )


class TestRekenen:
    def test_getal(self) -> None:
        assert evaluate_formula("100", ctx()) == Decimal("100")

    def test_decimalen_punt_en_komma(self) -> None:
        assert evaluate_formula("1.5 + 1,5", ctx()) == Decimal("3")

    def test_precedentie(self) -> None:
        assert evaluate_formula("2 + 3 * 4", ctx()) == Decimal("14")
        assert evaluate_formula("10 - 4 / 2", ctx()) == Decimal("8")

    def test_haakjes(self) -> None:
        assert evaluate_formula("(2 + 3) * 4", ctx()) == Decimal("20")

    def test_unaire_min(self) -> None:
        assert evaluate_formula("-5 + 3", ctx()) == Decimal("-2")
        assert evaluate_formula("2 * -3", ctx()) == Decimal("-6")

    def test_decimal_exact(self) -> None:
        """0,1 + 0,2 moet exact 0,3 zijn — het klassieke float-lek."""
        assert evaluate_formula("0,1 + 0,2", ctx()) == Decimal("0.3")

    def test_links_associatief(self) -> None:
        assert evaluate_formula("10 - 3 - 2", ctx()) == Decimal("5")
        assert evaluate_formula("24 / 4 / 2", ctx()) == Decimal("3")


class TestVariabelen:
    def test_vorige(self) -> None:
        assert evaluate_formula("vorige", ctx(vorige="123.45")) == Decimal("123.45")

    def test_kapitaalaflossing_met_deling(self) -> None:
        """De woning-formule uit de Excel: vorige + kapitaalaflossing / 2."""
        result = evaluate_formula(
            "vorige + kapitaalaflossing / 2",
            ctx(vorige="77150", kapitaalaflossing="1104.36"),
        )
        assert result == Decimal("77702.18")

    def test_budget_bestaande_categorie(self) -> None:
        result = evaluate_formula(
            'vorige + budget("Spaarrekening")',
            ctx(vorige="1000", budgets={"Spaarrekening": "400"}),
        )
        assert result == Decimal("1400")

    def test_budget_enkele_quotes(self) -> None:
        result = evaluate_formula(
            "budget('Beleggingen')", ctx(budgets={"Beleggingen": "250"})
        )
        assert result == Decimal("250")

    def test_budget_onbestaande_categorie_is_nul_met_warning(self) -> None:
        """Onbestaande categorie mag de keten niet breken (bv. 'Pensioensparen'
        bestaat niet in elke context): waarde 0 plus een warning."""
        c = ctx(vorige="500")
        assert evaluate_formula('vorige + budget("Pensioensparen")', c) == Decimal("500")
        assert len(c.warnings) == 1
        assert "Pensioensparen" in c.warnings[0]

    def test_budget_warning_niet_dubbel(self) -> None:
        c = ctx()
        evaluate_formula('budget("X") + budget("X")', c)
        assert len(c.warnings) == 1


class TestFouten:
    def test_syntaxfout_meldt_positie(self) -> None:
        with pytest.raises(FormulaError) as exc:
            evaluate_formula("2 +", ctx())
        assert exc.value.position == 3

    def test_onbekende_variabele(self) -> None:
        with pytest.raises(FormulaError, match="huidige"):
            evaluate_formula("huidige + 1", ctx())

    def test_deling_door_nul(self) -> None:
        with pytest.raises(FormulaError, match="[Dd]eling door nul"):
            evaluate_formula("100 / 0", ctx())

    def test_lege_formule(self) -> None:
        with pytest.raises(FormulaError):
            evaluate_formula("   ", ctx())

    def test_rommel_na_expressie(self) -> None:
        with pytest.raises(FormulaError):
            evaluate_formula("1 + 2 3", ctx())

    def test_budget_zonder_string(self) -> None:
        with pytest.raises(FormulaError):
            evaluate_formula("budget(vorige)", ctx())

    def test_te_lang(self) -> None:
        with pytest.raises(FormulaError, match="lang"):
            evaluate_formula("1" + " + 1" * MAX_FORMULA_LENGTH, ctx())

    def test_validate_formula_syntax(self) -> None:
        with pytest.raises(FormulaError):
            validate_formula("vorige +")

    def test_validate_formula_ok_zonder_context(self) -> None:
        """Valideren kan zonder waarden — er wordt niet geëvalueerd."""
        validate_formula('vorige + budget("Wat dan ook") * 2')
