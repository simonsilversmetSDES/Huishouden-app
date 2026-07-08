"""Eenmalig: laat elke bestaande categorisatieregel voor álle entiteiten gelden (#9).

Idempotent — voegt enkel ontbrekende (rule_id, context_id)-koppelingen toe. Gebruikt de
DATABASE_URL uit de omgeving/.env. Draai eerst op een kopie van de database.

    python scripts/link_all_rules.py
"""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CategorizationRule, Context, RuleContext


def main() -> None:
    db = SessionLocal()
    try:
        rule_ids = list(db.scalars(select(CategorizationRule.id)))
        context_ids = list(db.scalars(select(Context.id)))
        existing = {
            (rid, cid)
            for rid, cid in db.execute(select(RuleContext.rule_id, RuleContext.context_id))
        }
        added = 0
        for rid in rule_ids:
            for cid in context_ids:
                if (rid, cid) not in existing:
                    db.add(RuleContext(rule_id=rid, context_id=cid))
                    added += 1
        db.commit()
        print(
            f"{len(rule_ids)} regels × {len(context_ids)} contexts — "
            f"{added} koppeling(en) toegevoegd (totaal nu "
            f"{len(rule_ids) * len(context_ids)})"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
