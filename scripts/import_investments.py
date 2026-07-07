"""Eenmalige migratie van de beleggingstransacties (spec §7/§10) uit CSV.

Twee CSV's in data/excel/ (per persoon), `;`-delimiter, punt-decimalen, datum
dd/mm/jjjj. De context wordt uit de bestandsnaam afgeleid (Simon/Jozefien).

Gebruik (vanuit de repo-root, met de backend-venv):
    backend/.venv/Scripts/python scripts/import_investments.py --inspect
    backend/.venv/Scripts/python scripts/import_investments.py --db sqlite:///data/db/kopie.db

Fase A (--inspect): effecten + aantallen + gemiddelde aankoopprijs tonen, niets
schrijven. Fase B (import): op een KOPIE van de database; met sanity-check
(VWCE Simon gemiddelde aankoopprijs = € 98,240055).
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCEL_DIR = REPO_ROOT / "data" / "excel"

# Bestandsnaam bevat de persoon → context.
CONTEXT_BY_KEYWORD = {"simon": "Simon", "jozefien": "Jozefien"}


def find_csvs() -> list[Path]:
    return sorted(DEFAULT_EXCEL_DIR.glob("*.csv"))


def context_for(path: Path) -> str | None:
    name = path.name.casefold()
    return next((ctx for kw, ctx in CONTEXT_BY_KEYWORD.items() if kw in name), None)


def parse_csv(path: Path) -> tuple[list, list[str]]:
    """CSV → (rijen, overgeslagen-redenen). Import lazily zodat de app niet afhangt."""
    from app.services.investments_import import InvestmentRow

    rows: list[InvestmentRow] = []
    skipped: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for i, raw in enumerate(csv.DictReader(handle, delimiter=";"), start=2):
            naam = (raw.get("Share name") or "").strip()
            datum = (raw.get("Datum") or "").strip()
            aantal = (raw.get("Aantal shares") or "").strip()
            if not naam or not datum or not aantal:
                continue  # lege staartrijen
            try:
                row = InvestmentRow(
                    date=datetime.strptime(datum, "%d/%m/%Y").date(),
                    name=naam,
                    shares=Decimal(aantal),
                    price=Decimal((raw.get("prijs per share") or "0").strip()),
                    fee=Decimal((raw.get("Transactiekost") or "0").strip()),
                    tax=Decimal((raw.get("Transactiebelasting") or "0").strip()),
                )
            except (ValueError, InvalidOperation) as exc:
                skipped.append(f"{path.name} r{i}: {exc}")
                continue
            rows.append(row)
    return rows, skipped


def inspect() -> None:
    from collections import defaultdict

    for path in find_csvs():
        ctx = context_for(path)
        rows, skipped = parse_csv(path)
        print(f"=== {path.name} → context {ctx or '??'} ({len(rows)} rijen) ===")
        per: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for row in rows:
            per[row.name][0] += row.shares
            per[row.name][1] += row.shares * row.price + row.fee + row.tax
        for name, (shares, total) in per.items():
            avg = (total / shares).quantize(Decimal("0.000001")) if shares else "-"
            print(f"  {str(shares):>10} st | gem {avg} | {name}")
        for reason in skipped:
            print(f"  · overgeslagen: {reason}")
        print()


def run_import(db_url: str) -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import Context
    from app.services.investments import build_portfolio
    from app.services.investments_import import import_rows

    engine = create_engine(db_url)
    with Session(engine) as db:
        contexts = {c.name: c for c in db.scalars(select(Context))}
        for path in find_csvs():
            ctx_name = context_for(path)
            if ctx_name is None or ctx_name not in contexts:
                print(f"· {path.name}: geen context herkend — overgeslagen")
                continue
            rows, skipped = parse_csv(path)
            report = import_rows(db, contexts[ctx_name], rows)
            print(f"— {path.name} → {ctx_name} —")
            for sec in report.securities:
                if sec.skipped_existing:
                    print(f"    · {sec.name}: reeds aanwezig, overgeslagen")
                else:
                    tag = "nieuw effect" if sec.created else "bestaand effect"
                    print(f"    ✓ {sec.name}: {sec.transactions_new} transacties ({tag})")
            for reason in skipped:
                print(f"    · {reason}")
        db.commit()

        # Sanity: VWCE (Simon) gemiddelde aankoopprijs = € 98,240055.
        simon = contexts.get("Simon")
        avg = None
        if simon is not None:
            portfolio = build_portfolio(db, simon)
            vwce = next((p for p in portfolio.positions if "VWCE" in p.name), None)
            avg = vwce.avg_buy_price if vwce else None
        verdict = "OK" if avg == "98.240055" else "WIJKT AF!"
        print(f"\nHercheck VWCE Simon gem. aankoopprijs: {avg} (verwacht 98,240055) → {verdict}")
        if avg != "98.240055":
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Beleggingen-migratie voor de Huishouden-app")
    parser.add_argument("--inspect", action="store_true", help="alleen verkennen, niets schrijven")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLAlchemy-URL van de DOELDATABASE (KOPIE). Zonder --db gebeurt er niets.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "backend"))

    if args.inspect:
        inspect()
        return
    if not args.db:
        sys.exit("Import vereist --db met de URL van een KOPIE van de database.")
    run_import(args.db)


if __name__ == "__main__":
    main()
