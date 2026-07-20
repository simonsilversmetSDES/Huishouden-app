"""Eenmalige overzet van Weekmenu-data (recepten, planning, boodschappenlijst)
van de laptop-devdatabase naar de productiedatabase op ginnybeehome.

Kopieert UITSLUITEND de Weekmenu-tabellen (nul Financiën-tabellen aangeraakt),
in FK-veilige volgorde. Alle Weekmenu-FK's verwijzen uitsluitend naar andere
Weekmenu-tabellen (zie app/weekmenu/models.py), dus dit kan niet in de
Financiën-data schrijven.

Vereist: de doeldatabase heeft de Weekmenu-tabellen al aangemaakt via
`alembic upgrade head` (leeg is prima, dit script verwacht dat zelfs).

Gebruik (--inspect eerst, dan --apply — en altijd eerst op een KOPIE van de
productie-db testen, nooit meteen op de echte):
    python scripts/copy_weekmenu_data.py --source data/db/huishouden.db \
        --target /pad/naar/kopie-van-productie.db --inspect

    python scripts/copy_weekmenu_data.py --source data/db/huishouden.db \
        --target /pad/naar/productie.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Volgorde is FK-veilig: eerst attribuuttabellen zonder afhankelijkheden,
# dan tabellen die ernaar verwijzen.
TABLES_IN_ORDER = [
    "recipe_moments",
    "recipe_categories",
    "recipe_times",
    "recipe_difficulties",
    "shopping_categories",
    "ingredients",
    "recipes",
    "recipe_category_links",
    "recipe_ingredients",
    "week_plan_entries",
    "shopping_list_items",
]


def inspect(conn: sqlite3.Connection) -> None:
    print("Tabel                    bron-rijen  doel-rijen")
    for table in TABLES_IN_ORDER:
        src_count = conn.execute(f"SELECT COUNT(*) FROM src.{table}").fetchone()[0]
        dst_count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        print(f"{table:<24} {src_count:>10} {dst_count:>11}")
        if dst_count:
            print(f"  WAARSCHUWING: {table} in doel is niet leeg — --apply slaat deze niet over!")


def apply(conn: sqlite3.Connection) -> None:
    for table in TABLES_IN_ORDER:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        col_list = ", ".join(cols)
        conn.execute(f"INSERT INTO main.{table} ({col_list}) SELECT {col_list} FROM src.{table}")
        n = conn.execute(f"SELECT COUNT(*) FROM src.{table}").fetchone()[0]
        print(f"{table}: {n} rijen gekopieerd")
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Laptop-devdatabase (bron)")
    parser.add_argument("--target", required=True, help="Productiedatabase (doel)")
    parser.add_argument("--inspect", action="store_true", help="Enkel rijtellingen tonen")
    parser.add_argument("--apply", action="store_true", help="Effectief kopiëren")
    args = parser.parse_args()

    if args.inspect == args.apply:
        sys.exit("Kies precies één van --inspect of --apply")

    source = Path(args.source)
    target = Path(args.target)
    if not source.exists():
        sys.exit(f"Bronbestand niet gevonden: {source}")
    if not target.exists():
        sys.exit(f"Doelbestand niet gevonden: {target}")

    conn = sqlite3.connect(target)
    conn.execute("ATTACH DATABASE ? AS src", (str(source),))

    if args.inspect:
        inspect(conn)
    else:
        apply(conn)

    conn.close()


if __name__ == "__main__":
    main()
