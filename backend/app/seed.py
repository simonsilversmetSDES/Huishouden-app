"""Idempotente seed: contexten, categorieën (per context), rekeningen en users.

Draait bij elke opstart (entrypoint) en is veilig om te herhalen: bestaande
rijen worden hergebruikt, user-email/hash wordt bijgewerkt vanuit .env.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Account, Category, Context, User
from app.models.enums import AccountType, Bank, CategoryType

logger = logging.getLogger(__name__)

CONTEXT_NAMES = ["Gemeenschappelijk", "Simon", "Jozefien"]

# Spec §3 — seed-categorieën; elke context krijgt dezelfde startlijst.
CATEGORIES: dict[CategoryType, list[str]] = {
    CategoryType.INKOMEN: [
        "Gemeenschappelijke bijdrage",
        "Maaltijdcheques",
        "Elektriciteit wagen",
        "Terugbetalingen / Uitzonderlijk",
        "Sparen reis",
    ],
    CategoryType.UITGAVEN: [
        "Lening",
        "Energie en Water",
        "Internet",
        "Boodschappen",
        "Restaurant / Café",
        "Cadeaus",
        "Verzekeringen / Belastingen",
        "Huis & Wonen",
        "Ontspanning/Sport/Boeken",
        "Reizen / weekendje weg",
        "Verzorging",
        "Kadastraal inkomen",
        "Andere",
        "Katten",
    ],
    CategoryType.SPAREN: [
        "Spaarrekening",
        "Beleggingen",
    ],
}

ACCOUNTS = [
    ("Gemeenschappelijk", "KBC Zichtrekening", Bank.KBC, AccountType.ZICHT),
    ("Simon", "Fortis Zichtrekening", Bank.FORTIS, AccountType.ZICHT),
]


def seed_contexts(db: Session) -> dict[str, Context]:
    result: dict[str, Context] = {}
    for name in CONTEXT_NAMES:
        ctx = db.scalars(select(Context).where(Context.name == name)).one_or_none()
        if ctx is None:
            ctx = Context(name=name)
            db.add(ctx)
            db.flush()
        result[name] = ctx
    return result


def seed_categories(db: Session, contexts: dict[str, Context]) -> None:
    for ctx in contexts.values():
        sort_order = 0
        for cat_type, names in CATEGORIES.items():
            for name in names:
                exists = db.scalars(
                    select(Category).where(
                        Category.context_id == ctx.id,
                        Category.type == cat_type,
                        Category.name == name,
                    )
                ).one_or_none()
                if exists is None:
                    db.add(
                        Category(
                            context_id=ctx.id, name=name, type=cat_type, sort_order=sort_order
                        )
                    )
                sort_order += 1


def seed_accounts(db: Session, contexts: dict[str, Context]) -> None:
    for context_name, name, bank, acc_type in ACCOUNTS:
        ctx = contexts[context_name]
        exists = db.scalars(
            select(Account).where(Account.context_id == ctx.id, Account.name == name)
        ).one_or_none()
        if exists is None:
            db.add(Account(context_id=ctx.id, name=name, bank=bank, type=acc_type))


def seed_users(db: Session, settings: Settings) -> None:
    for name, email, password_hash in (
        ("Simon", settings.simon_email, settings.simon_password_hash),
        ("Jozefien", settings.jozefien_email, settings.jozefien_password_hash),
    ):
        if not email or not password_hash:
            logger.warning("Geen email/hash voor %s in .env — user niet geseed", name)
            continue
        user = db.scalars(select(User).where(User.name == name)).one_or_none()
        if user is None:
            db.add(User(name=name, email=email, password_hash=password_hash))
        else:
            user.email = email
            user.password_hash = password_hash


def seed_all(db: Session, settings: Settings) -> None:
    contexts = seed_contexts(db)
    seed_categories(db, contexts)
    seed_accounts(db, contexts)
    seed_users(db, settings)
    db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        seed_all(db, get_settings())
    logger.info("Seed voltooid")


if __name__ == "__main__":
    main()
