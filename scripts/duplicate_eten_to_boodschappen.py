"""Eenmalige migratie: dupliceer alle categorisatieregels met categorie 'Eten'
naar een variant met categorie 'Boodschappen', enkel van toepassing voor de
context 'Gemeenschappelijk'.

- De originele Eten-regels blijven volledig ongemoeid.
- Elk duplicaat behoudt match_field / match_type / match_value / priority.
- Duplicaat krijgt category_id van de actieve 'Boodschappen'-categorie in
  Gemeenschappelijk, eigen context_id = Gemeenschappelijk, en één rule_contexts-
  rij naar Gemeenschappelijk (dus 'geldt voor' = enkel Gemeenschappelijk).
- Idempotent: bestaat er al een identiek duplicaat, dan wordt het overgeslagen.

Gebruik:
    python scripts/duplicate_eten_to_boodschappen.py            # dry-run (rollback)
    python scripts/duplicate_eten_to_boodschappen.py --apply    # commit
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/db/huishouden-dev.db")
GEM = "Gemeenschappelijk"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="commit i.p.v. rollback")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    c = db.cursor()

    # Doelcategorie: actieve 'Boodschappen' in Gemeenschappelijk.
    row = c.execute(
        """SELECT cat.id FROM categories cat JOIN contexts ctx ON ctx.id = cat.context_id
           WHERE ctx.name = ? AND cat.name = 'Boodschappen' AND cat.active = 1""",
        (GEM,),
    ).fetchone()
    if row is None:
        print(f"FOUT: geen actieve categorie 'Boodschappen' in {GEM}.", file=sys.stderr)
        return 1
    boodschappen_id = row["id"]

    gem_id = c.execute("SELECT id FROM contexts WHERE name = ?", (GEM,)).fetchone()["id"]

    # Alle regels met categorie 'Eten' (welke context dan ook).
    eten_rules = c.execute(
        """SELECT r.id, r.priority, r.match_field, r.match_type, r.match_value
           FROM categorization_rules r JOIN categories cat ON cat.id = r.category_id
           WHERE cat.name = 'Eten' ORDER BY r.id"""
    ).fetchall()

    created, skipped = [], []
    for r in eten_rules:
        # Idempotentie: bestaat er al een Boodschappen-duplicaat in Gemeenschappelijk
        # met dezelfde match-definitie?
        exists = c.execute(
            """SELECT 1 FROM categorization_rules
               WHERE context_id = ? AND category_id = ?
                 AND match_field = ? AND match_type = ? AND match_value = ?""",
            (gem_id, boodschappen_id, r["match_field"], r["match_type"], r["match_value"]),
        ).fetchone()
        if exists:
            skipped.append(r["match_value"])
            continue

        cur = c.execute(
            """INSERT INTO categorization_rules
                 (context_id, priority, match_field, match_type, match_value,
                  category_id, created_from_correction)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (gem_id, r["priority"], r["match_field"], r["match_type"],
             r["match_value"], boodschappen_id),
        )
        new_id = cur.lastrowid
        c.execute(
            "INSERT INTO rule_contexts (rule_id, context_id) VALUES (?, ?)",
            (new_id, gem_id),
        )
        created.append((new_id, r["id"], r["match_field"], r["match_value"]))

    print(f"Bron: {len(eten_rules)} Eten-regels gevonden.")
    print(f"Nieuw aangemaakt: {len(created)}")
    for new_id, src_id, field, value in created:
        print(f"  +regel {new_id:>4}  (kopie van {src_id})  {field}~'{value}'  -> Boodschappen [{GEM}]")
    if skipped:
        print(f"Overgeslagen (bestond al): {len(skipped)} -> {', '.join(skipped)}")

    if args.apply:
        db.commit()
        print("\nGECOMMIT.")
    else:
        db.rollback()
        print("\nDRY-RUN (rollback) — draai met --apply om weg te schrijven.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
