"""Eenmalige backfill van historische koersen (spec §7) via yfinance.

Haalt per effect met ticker de dagelijkse slotkoersen op vanaf de eerste
transactie tot vandaag, rekent ze per beursdag naar euro om en cachet ze in
`security_prices`. Zo krijgen het jaarrendement en historische grafieken echte
cijfers i.p.v. enkel de laatste dagen.

Gebruik (vanuit de repo-root, met de backend-venv):
    backend/.venv/Scripts/python scripts/backfill_prices.py --inspect
    backend/.venv/Scripts/python scripts/backfill_prices.py --db sqlite:///data/db/kopie.db

--inspect toont enkel wat er opgehaald zou worden (geen netwerk, geen schrijven).
De backfill zelf vereist --db met de URL van een KOPIE van de database
(CLAUDE.md: migratiescripts eerst op een kopie draaien). upsert_price werkt
idempotent: opnieuw draaien overschrijft dezelfde datums, dupliceert niet.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Windows-console: forceer UTF-8 zodat €, − en … niet crashen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _start_dates(db) -> dict[int, date]:  # type: ignore[no-untyped-def]
    """Eerste transactiedatum per effect (startpunt voor de historiek).

    Een referentie-index (`is_benchmark`) krijgt een vroeger startpunt: december
    vóór het eerste transactiejaar van zijn context. Zo bestaat er een koers op
    élke jaargrens die het jaarrendement toont, en is de referentie-kolom niet
    "onvolledig" voor jaren waarin het effect zelf nog niet gekocht was."""
    from sqlalchemy import func, select

    from app.models import Security, SecurityTransaction

    rows = db.execute(
        select(SecurityTransaction.security_id, func.min(SecurityTransaction.date)).group_by(
            SecurityTransaction.security_id
        )
    ).all()
    starts = {security_id: first for security_id, first in rows}

    first_by_context = db.execute(
        select(Security.owner_context_id, func.min(SecurityTransaction.date))
        .join(Security, Security.id == SecurityTransaction.security_id)
        .group_by(Security.owner_context_id)
    ).all()
    context_first = {context_id: first for context_id, first in first_by_context}
    for sec in db.scalars(select(Security).where(Security.is_benchmark.is_(True))):
        first = context_first.get(sec.owner_context_id)
        if first is None:
            continue
        bench_start = date(first.year - 1, 12, 1)  # dekt de jaargrens binnen de tolerantie
        current = starts.get(sec.id)
        starts[sec.id] = bench_start if current is None else min(current, bench_start)
    return starts


def inspect(db_url: str | None) -> None:
    """Toon per effect de ticker en het startpunt, zonder netwerk of schrijven."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models import Security

    engine = create_engine(db_url or get_settings().database_url)
    with Session(engine) as db:
        starts = _start_dates(db)
        securities = list(db.scalars(select(Security).order_by(Security.name)))
        print(f"{'Effect':32} {'Ticker':14} {'Vanaf':10}")
        print("-" * 58)
        for s in securities:
            start = starts.get(s.id)
            ticker = s.ticker or "— (manueel)"
            vanaf = start.isoformat() if start else "— (geen tx)"
            print(f"{s.name[:32]:32} {ticker[:14]:14} {vanaf:10}")


def run_backfill(db_url: str) -> None:
    """Historiek ophalen + cachen. Draai op een KOPIE van de db."""
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.models import Security, SecurityPrice
    from app.services.prices import fetch_price_history

    engine = create_engine(db_url)
    with Session(engine) as db:
        starts = _start_dates(db)
        securities = list(db.scalars(select(Security).order_by(Security.name)))
        print(f"Backfill voor {len(securities)} effecten tot vandaag…\n")
        result = fetch_price_history(db, securities, starts, date.today())
        db.commit()

        for name, n in sorted(result.per_security.items()):
            print(f"  {name[:34]:34} {n:5} koersen")
        if result.skipped:
            print(f"\n  Overgeslagen (geen ticker): {', '.join(result.skipped)}")
        if result.failed:
            print(f"\n  Mislukt (geen historiek): {', '.join(result.failed)}")
        print(f"\nTotaal geschreven: {result.fetched} koersrijen.")

        # Verificatie: welke jaargrenzen zijn nu gedekt?
        years = [
            r[0]
            for r in db.execute(
                select(func.strftime("%Y", SecurityPrice.date))
                .distinct()
                .order_by(func.strftime("%Y", SecurityPrice.date))
            ).all()
        ]
        print(f"Jaren met koersen na backfill: {', '.join(years)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historische koersen via yfinance.")
    parser.add_argument("--inspect", action="store_true", help="alleen tonen, niets schrijven")
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "SQLAlchemy-URL van een KOPIE van de db (bv. sqlite:///data/db/kopie.db). "
            "Verplicht voor de backfill; zonder --db gebeurt er niets."
        ),
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "backend"))

    if args.inspect:
        inspect(args.db)
        return
    if not args.db:
        sys.exit(
            "Backfill vereist --db met de URL van een KOPIE van de database "
            "(bv. --db sqlite:///data/db/kopie.db). Zonder --db gebeurt er niets."
        )
    run_backfill(args.db)


if __name__ == "__main__":
    main()
