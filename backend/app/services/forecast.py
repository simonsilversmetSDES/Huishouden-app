"""Vermogensforecast — de forecast-kolommen van het Excel-werkblad "Status balans".

Startpunt is de laatst gekende werkelijke balans per activaklasse (uit de
net-worth-opbouw, spec §9); daarna keten door de gebruiker aanpasbare formules
maand per maand door: `vorige`, `budget("Categorie")` (gepland maandbedrag uit
de budgettabel) en `kapitaalaflossing` (kapitaaldeel van de leningbetaling die
maand). Standaardformules staan hieronder hardcoded; enkel afwijkingen worden
in `forecast_formulas` bewaard (rij-default of cel-override).

Alle rekenwerk in Decimal; centen enkel aan de API-rand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Context, ForecastFormula, ForecastNote, Loan
from app.models.enums import AssetClass
from app.schemas.forecast import (
    ForecastCellOut,
    ForecastFormulaIn,
    ForecastMatrixOut,
    ForecastNetWorthOut,
    ForecastNoteIn,
    ForecastRowOut,
)
from app.schemas.snapshots import AssetValue, NetWorthRow
from app.services.budget import ZERO, from_cents, to_cents
from app.services.forecast_formula import (
    EvalContext,
    FormulaError,
    evaluate_formula,
    validate_formula,
)
from app.services.loans import amortization_schedule
from app.services.net_worth import build_net_worth

# Vaste rijvolgorde: die van de Excel-balans ("Dropdown data" I8:I13) + bitcoin.
ASSET_ORDER = [
    AssetClass.CONTANT,
    AssetClass.ETF_FONDSEN,
    AssetClass.PENSIOENSPAREN,
    AssetClass.GROEPSVERZEKERING,
    AssetClass.WONING,
    AssetClass.AANDELEN,
    AssetClass.BITCOIN,
]

# De formules uit het Excel-werkblad "Status balans" (rijen 79-97).
DEFAULT_FORMULAS: dict[AssetClass, str] = {
    AssetClass.CONTANT: 'vorige + budget("Spaarrekening")',
    AssetClass.ETF_FONDSEN: 'vorige + budget("Beleggingen")',
    AssetClass.PENSIOENSPAREN: 'vorige + budget("Pensioensparen")',
    AssetClass.GROEPSVERZEKERING: "vorige + 100",
    AssetClass.WONING: "vorige + kapitaalaflossing / 2",
    AssetClass.AANDELEN: "vorige",
    AssetClass.BITCOIN: "vorige",
}


class UnknownContextError(ValueError):
    """Formule-upsert verwijst naar een context die niet bestaat."""


def _next_month(month: date) -> date:
    return date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)


def _months_between(start: date, end: date) -> Iterator[date]:
    """Eerste-van-de-maand-datums van start t/m end (beide inclusief)."""
    month = start
    while month <= end:
        yield month
        month = _next_month(month)


def _budget_lookup_factory(
    db: Session, context: Context
) -> Callable[[date], Callable[[str], Decimal | None]]:
    """Per maand een lookup 'categorienaam → gepland bedrag'.

    Onbekende categorie ⇒ None (de evaluator maakt daar 0 + warning van);
    bekende categorie zonder budgetcel die maand ⇒ 0, zoals een lege Excel-cel.
    """
    known_names = set(
        db.scalars(select(Category.name).where(Category.context_id == context.id)).all()
    )
    rows = db.execute(
        select(Budget.year, Budget.month, Category.name, Budget.amount)
        .join(Category, Budget.category_id == Category.id)
        .where(Category.context_id == context.id)
    ).all()
    table: dict[tuple[int, int], dict[str, Decimal]] = {}
    for year, month, name, amount in rows:
        table.setdefault((year, month), {})[name] = amount

    def for_month(month: date) -> Callable[[str], Decimal | None]:
        amounts = table.get((month.year, month.month), {})

        def lookup(name: str) -> Decimal | None:
            if name not in known_names:
                return None
            return amounts.get(name, ZERO)

        return lookup

    return for_month


def _principal_by_month(db: Session, today: date) -> dict[tuple[int, int], Decimal]:
    """Kapitaaldeel van de leningbetaling per (jaar, maand), gesommeerd over leningen."""
    out: dict[tuple[int, int], Decimal] = {}
    for loan in db.scalars(select(Loan)):
        for row in amortization_schedule(loan, today):
            key = (row.date.year, row.date.month)
            out[key] = out.get(key, ZERO) + row.principal
    return out


def _formula_records(
    db: Session, context: Context
) -> tuple[dict[AssetClass, str], dict[tuple[AssetClass, int, int], str]]:
    """Opgeslagen formules: rij-defaults (year=0/month=0) en cel-overrides."""
    row_formulas: dict[AssetClass, str] = {}
    overrides: dict[tuple[AssetClass, int, int], str] = {}
    for record in db.scalars(
        select(ForecastFormula).where(ForecastFormula.context_id == context.id)
    ):
        if record.year == 0:
            row_formulas[record.asset_class] = record.formula
        else:
            overrides[(record.asset_class, record.year, record.month)] = record.formula
    return row_formulas, overrides


def _actuals(
    db: Session, context: Context, today: date
) -> tuple[date | None, dict[date, dict[AssetClass, Decimal]], dict[AssetClass, Decimal]]:
    """Werkelijke maandwaarden, de laatste werkelijke maand en de startwaarden.

    Startwaarde per klasse = waarde in de laatste maand, of carry-forward uit de
    meest recente eerdere maand met die klasse; nergens aanwezig ⇒ 0.
    """
    rows = build_net_worth(db, context, today).rows
    by_month: dict[date, dict[AssetClass, Decimal]] = {
        row.snapshot_date: {
            asset.asset_class: from_cents(asset.value_cents) for asset in row.assets
        }
        for row in rows
    }
    if not rows:
        return None, {}, {asset_class: ZERO for asset_class in ASSET_ORDER}
    start: dict[AssetClass, Decimal] = {asset_class: ZERO for asset_class in ASSET_ORDER}
    for row in rows:  # chronologisch: latere maanden overschrijven
        for asset in row.assets:
            start[asset.asset_class] = from_cents(asset.value_cents)
    return rows[-1].snapshot_date, by_month, start


class _Chain:
    """Ketent de formules per klasse maand per maand door, met foutpropagatie."""

    def __init__(
        self,
        db: Session,
        context: Context,
        today: date,
        start_values: dict[AssetClass, Decimal],
    ) -> None:
        self.values = dict(start_values)
        self.errors: dict[AssetClass, str] = {}
        self.warnings: dict[AssetClass, list[str]] = {ac: [] for ac in ASSET_ORDER}
        self.row_formulas, self.overrides = _formula_records(db, context)
        self.budget_for_month = _budget_lookup_factory(db, context)
        self.principal = _principal_by_month(db, today)

    def row_formula(self, asset_class: AssetClass) -> tuple[str, bool]:
        stored = self.row_formulas.get(asset_class)
        if stored is not None:
            return stored, False
        return DEFAULT_FORMULAS[asset_class], True

    def step(self, month: date) -> None:
        """Reken één maand door voor alle klassen."""
        lookup = self.budget_for_month(month)
        kapitaal = self.principal.get((month.year, month.month), ZERO)
        for asset_class in ASSET_ORDER:
            if asset_class in self.errors:
                continue
            formula = self.overrides.get(
                (asset_class, month.year, month.month)
            ) or self.row_formula(asset_class)[0]
            ctx = EvalContext(
                vorige=self.values[asset_class],
                kapitaalaflossing=kapitaal,
                budget_lookup=lookup,
                warnings=[],
            )
            try:
                self.values[asset_class] = evaluate_formula(formula, ctx)
            except FormulaError as exc:
                self.errors[asset_class] = f"{exc} ({month.month:02d}/{month.year})"
            for warning in ctx.warnings:
                if warning not in self.warnings[asset_class]:
                    self.warnings[asset_class].append(warning)


def build_forecast_matrix(
    db: Session, context: Context, year: int, today: date | None = None
) -> ForecastMatrixOut:
    if today is None:
        today = date.today()

    last_actual, actual_by_month, start_values = _actuals(db, context, today)
    chain = _Chain(db, context, today, start_values)

    chain_start = _next_month(last_actual) if last_actual else date(year, 1, 1)
    months = [date(year, m, 1) for m in range(1, 13)]

    # Doorrekenen vanaf de maand na de laatste werkelijke, t/m december van `year`;
    # maanden vóór het gevraagde jaar worden wel berekend maar niet getoond.
    forecast_cells: dict[tuple[AssetClass, date], ForecastCellOut] = {}
    for month in _months_between(chain_start, months[-1]):
        chain.step(month)
        if month.year != year:
            continue
        for asset_class in ASSET_ORDER:
            error = chain.errors.get(asset_class)
            override = chain.overrides.get((asset_class, month.year, month.month))
            forecast_cells[(asset_class, month)] = ForecastCellOut(
                value_cents=None if error else to_cents(chain.values[asset_class]),
                kind="error" if error else "forecast",
                override=override is not None,
                override_formula=override,
                error=error,
            )

    rows: list[ForecastRowOut] = []
    for asset_class in ASSET_ORDER:
        formula, is_default = chain.row_formula(asset_class)
        cells: list[ForecastCellOut] = []
        for month in months:
            forecast = forecast_cells.get((asset_class, month))
            if forecast is not None:
                cells.append(forecast)
                continue
            value = actual_by_month.get(month, {}).get(asset_class)
            cells.append(
                ForecastCellOut(
                    value_cents=None if value is None else to_cents(value),
                    kind="werkelijk",
                )
            )
        rows.append(
            ForecastRowOut(
                asset_class=asset_class,
                formula=formula,
                is_default=is_default,
                warnings=chain.warnings[asset_class],
                cells=cells,
            )
        )

    # Celnotities (Excel-achtig) aan de cellen hangen; puur weergave, geen invloed
    # op de berekening of de totalen.
    row_by_class = {row.asset_class: row for row in rows}
    for note in db.scalars(
        select(ForecastNote).where(
            ForecastNote.context_id == context.id, ForecastNote.year == year
        )
    ):
        row = row_by_class.get(AssetClass(note.asset_class))
        if row is not None:
            row.cells[note.month - 1].note = note.note

    totals: list[ForecastCellOut] = []
    for index, _month in enumerate(months):
        column = [row.cells[index] for row in rows]
        if any(cell.kind == "error" for cell in column):
            totals.append(ForecastCellOut(value_cents=None, kind="error"))
            continue
        kind = column[0].kind  # per kolom is elke cel werkelijk óf forecast
        values = [cell.value_cents for cell in column if cell.value_cents is not None]
        totals.append(
            ForecastCellOut(
                value_cents=sum(values) if (values or kind == "forecast") else None,
                kind=kind,
            )
        )

    return ForecastMatrixOut(
        context_id=context.id,
        year=year,
        last_actual_month=last_actual,
        rows=rows,
        totals=totals,
    )


def upsert_formula(db: Session, item: ForecastFormulaIn) -> None:
    """Zet of wist een formule; lege formule = terug naar de standaardformule."""
    if db.get(Context, item.context_id) is None:
        raise UnknownContextError(f"Onbekende context: {item.context_id}")
    if (item.year is None) != (item.month is None):
        raise ValueError("Een cel-override vereist jaar én maand (of geen van beide)")
    year = item.year or 0
    month = item.month or 0
    if year and not 1 <= month <= 12:
        raise ValueError("maand moet tussen 1 en 12 liggen")

    text = item.formula.strip()
    if text:
        validate_formula(text)

    existing = db.scalars(
        select(ForecastFormula).where(
            ForecastFormula.context_id == item.context_id,
            ForecastFormula.asset_class == item.asset_class,
            ForecastFormula.year == year,
            ForecastFormula.month == month,
        )
    ).one_or_none()
    if text == "":
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(
            ForecastFormula(
                context_id=item.context_id,
                asset_class=item.asset_class,
                year=year,
                month=month,
                formula=text,
            )
        )
    else:
        existing.formula = text
    db.commit()


def upsert_forecast_note(db: Session, item: ForecastNoteIn) -> None:
    """Zet of wist een celnotitie (lege/witruimte-notitie = verwijderen)."""
    if db.get(Context, item.context_id) is None:
        raise UnknownContextError(f"Onbekende context: {item.context_id}")
    existing = db.scalars(
        select(ForecastNote).where(
            ForecastNote.context_id == item.context_id,
            ForecastNote.asset_class == item.asset_class,
            ForecastNote.year == item.year,
            ForecastNote.month == item.month,
        )
    ).one_or_none()
    text = item.note.strip()
    if text == "":
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(
            ForecastNote(
                context_id=item.context_id,
                asset_class=item.asset_class,
                year=item.year,
                month=item.month,
                note=text,
            )
        )
    else:
        existing.note = text
    db.commit()


def _budget_horizon_year(db: Session, contexts: list[Context], today: date) -> int:
    """Laatste jaar met budgetdata voor deze contexten, minimum het huidige jaar."""
    context_ids = [c.id for c in contexts]
    max_year = db.scalar(
        select(Budget.year)
        .join(Category, Budget.category_id == Category.id)
        .where(Category.context_id.in_(context_ids))
        .order_by(Budget.year.desc())
        .limit(1)
    )
    return max(today.year, max_year or 0)


def build_forecast_net_worth(
    db: Session, contexts: list[Context], today: date | None = None
) -> ForecastNetWorthOut:
    """Forecast van de (gecombineerde) nettowaarde voor de evolutiegrafiek.

    Eerste rij = de globale laatste werkelijke maand (verbindingspunt met de
    werkelijke reeks); contexten waarvan de eigen reeks vroeger stopt worden tot
    daar doorgerekend. Een formulefout laat die klasse ongewijzigd doorlopen —
    fouten worden in de matrix op de Budget-tab getoond, niet in de grafiek.
    """
    if today is None:
        today = date.today()

    starts: list[tuple[Context, date | None, dict[AssetClass, Decimal]]] = []
    last_months: list[date] = []
    for context in contexts:
        last_actual, _, start_values = _actuals(db, context, today)
        starts.append((context, last_actual, start_values))
        if last_actual is not None:
            last_months.append(last_actual)
    if not last_months:
        return ForecastNetWorthOut(rows=[])

    global_last = max(last_months)
    horizon = date(_budget_horizon_year(db, contexts, today), 12, 1)
    months = [global_last, *_months_between(_next_month(global_last), horizon)]

    per_month: dict[date, dict[AssetClass, Decimal]] = {m: {} for m in months}
    for context, last_actual, start_values in starts:
        chain = _Chain(db, context, today, start_values)
        chain_start = _next_month(last_actual) if last_actual else _next_month(global_last)
        for month in _months_between(chain_start, horizon):
            previous = dict(chain.values)
            chain.step(month)
            # Formulefout ⇒ waarde ongewijzigd laten doorlopen (zie docstring).
            for asset_class in chain.errors:
                chain.values[asset_class] = previous.get(asset_class, ZERO)
            chain.errors.clear()
            if month in per_month:
                for asset_class in ASSET_ORDER:
                    bucket = per_month[month]
                    bucket[asset_class] = bucket.get(asset_class, ZERO) + chain.values[asset_class]
        # Bijdrage op het verbindingspunt: de eigen werkelijke (of doorgerekende) stand.
        if last_actual == global_last:
            bucket = per_month[global_last]
            for asset_class, value in start_values.items():
                bucket[asset_class] = bucket.get(asset_class, ZERO) + value

    rows: list[NetWorthRow] = []
    for month in months:
        assets = per_month[month]
        total = sum(assets.values(), ZERO)
        rows.append(
            NetWorthRow(
                snapshot_date=month,
                assets=[
                    AssetValue(asset_class=ac, value_cents=to_cents(v))
                    for ac, v in assets.items()
                ],
                total_cents=to_cents(total),
                change_cents=None,
                change_pct=None,
            )
        )
    return ForecastNetWorthOut(rows=rows)
