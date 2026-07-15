"""Idempotente seed: contexten, categorieën (per context), rekeningen en users.

Draait bij elke opstart (entrypoint) en is veilig om te herhalen: bestaande
rijen worden hergebruikt, user-email/hash wordt bijgewerkt vanuit .env.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Account, CategorizationRule, Category, Context, User
from app.models.enums import AccountType, Bank, CategoryType, MatchField, MatchType
from app.services.csv_parsers import normalize_iban

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

# Extra categorieën per context, bovenop de gedeelde startlijst.
# "Loon" (afspraak 06/07/2026): loon komt binnen op de persoonlijke rekeningen,
# niet op de gemeenschappelijke — de LOON-seedregel wijst hiernaar.
EXTRA_CATEGORIES: dict[str, dict[CategoryType, list[str]]] = {
    "Simon": {CategoryType.INKOMEN: ["Loon"]},
    "Jozefien": {CategoryType.INKOMEN: ["Loon"]},
}

# Seed-regels (spec §5.3), allemaal contains + case-insensitive. Merchants bij
# kaartbetalingen/domiciliëringen zitten in de omschrijvingstekst (description);
# de maaltijdcheque-uitgevers zijn echte SEPA-tegenpartijen (counterparty_name).
# Regels met een categorie die in een context ontbreekt (bv. "Loon" in
# Gemeenschappelijk) worden daar overgeslagen.
SEED_RULES: list[tuple[MatchField, str, CategoryType, str]] = [
    (MatchField.DESCRIPTION, "COLRUYT", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "ALDI", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "DELHAIZE", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "LIDL", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "CARREFOUR", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "BON'AP", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "OKAY", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "MUHSIN MARKET", CategoryType.UITGAVEN, "Boodschappen"),
    (MatchField.DESCRIPTION, "GAMMA", CategoryType.UITGAVEN, "Huis & Wonen"),
    (MatchField.DESCRIPTION, "ACTION", CategoryType.UITGAVEN, "Huis & Wonen"),
    (MatchField.DESCRIPTION, "IKEA", CategoryType.UITGAVEN, "Huis & Wonen"),
    (MatchField.DESCRIPTION, "BRICO", CategoryType.UITGAVEN, "Huis & Wonen"),
    (MatchField.DESCRIPTION, "LUMINUS", CategoryType.UITGAVEN, "Energie en Water"),
    (MatchField.DESCRIPTION, "MOBILE VIKINGS", CategoryType.UITGAVEN, "Internet"),
    (MatchField.DESCRIPTION, "TELENET", CategoryType.UITGAVEN, "Internet"),
    (MatchField.DESCRIPTION, "PROXIMUS", CategoryType.UITGAVEN, "Internet"),
    (
        MatchField.DESCRIPTION,
        "KBC VERZEKERINGEN",
        CategoryType.UITGAVEN,
        "Verzekeringen / Belastingen",
    ),
    (MatchField.DESCRIPTION, "WONINGPOLIS", CategoryType.UITGAVEN, "Verzekeringen / Belastingen"),
    (MatchField.DESCRIPTION, "GEZINSPOLIS", CategoryType.UITGAVEN, "Verzekeringen / Belastingen"),
    (MatchField.DESCRIPTION, "WONINGKREDIET", CategoryType.UITGAVEN, "Lening"),
    (MatchField.DESCRIPTION, "JUST RUSSEL", CategoryType.UITGAVEN, "Katten"),
    (MatchField.DESCRIPTION, "CINAIR", CategoryType.UITGAVEN, "Ontspanning/Sport/Boeken"),
    (MatchField.DESCRIPTION, "KANGOEROE", CategoryType.UITGAVEN, "Ontspanning/Sport/Boeken"),
    (MatchField.DESCRIPTION, "TANDARTS", CategoryType.UITGAVEN, "Verzorging"),
    (MatchField.DESCRIPTION, "APOTHEEK", CategoryType.UITGAVEN, "Verzorging"),
    (MatchField.DESCRIPTION, "A.S.Z.", CategoryType.UITGAVEN, "Verzorging"),
    (MatchField.DESCRIPTION, "LOON", CategoryType.INKOMEN, "Loon"),
    (MatchField.COUNTERPARTY_NAME, "MONIZZE", CategoryType.INKOMEN, "Maaltijdcheques"),
    (MatchField.COUNTERPARTY_NAME, "EDENRED", CategoryType.INKOMEN, "Maaltijdcheques"),
    (MatchField.COUNTERPARTY_NAME, "PLUXEE", CategoryType.INKOMEN, "Maaltijdcheques"),
    (MatchField.DESCRIPTION, "MAALTIJDCHEQUES", CategoryType.INKOMEN, "Maaltijdcheques"),
    (MatchField.DESCRIPTION, "AUTOMATISCH SPAREN", CategoryType.SPAREN, "Spaarrekening"),
]

# (context, naam, bank, type, Settings-veld met het IBAN uit .env)
ACCOUNTS = [
    ("Gemeenschappelijk", "KBC Zichtrekening", Bank.KBC, AccountType.ZICHT, "kbc_zicht"),
    ("Gemeenschappelijk", "KBC Spaarrekening", Bank.KBC, AccountType.SPAAR, "kbc_spaar"),
    ("Simon", "Fortis Zichtrekening", Bank.FORTIS, AccountType.ZICHT, "fortis_zicht"),
    ("Simon", "Fortis Spaarrekening", Bank.FORTIS, AccountType.SPAAR, "fortis_spaar"),
    ("Jozefien", "KBC Zichtrekening", Bank.KBC, AccountType.ZICHT, "jozefien_zicht"),
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
        extra = EXTRA_CATEGORIES.get(ctx.name, {})
        for cat_type, names in CATEGORIES.items():
            for name in [*names, *extra.get(cat_type, [])]:
                exists = db.scalars(
                    select(Category).where(
                        Category.context_id == ctx.id,
                        Category.type == cat_type,
                        Category.name == name,
                    )
                ).one_or_none()
                if exists is None:
                    db.add(
                        Category(context_id=ctx.id, name=name, type=cat_type, sort_order=sort_order)
                    )
                sort_order += 1


def seed_accounts(db: Session, contexts: dict[str, Context], settings: Settings) -> None:
    """Rekeningen aanmaken en IBAN's bijwerken vanuit .env (zoals seed_users)."""
    for context_name, name, bank, acc_type, iban_setting in ACCOUNTS:
        ctx = contexts[context_name]
        iban = normalize_iban(getattr(settings, f"account_iban_{iban_setting}")) or None
        account = db.scalars(
            select(Account).where(Account.context_id == ctx.id, Account.name == name)
        ).one_or_none()
        if account is None:
            db.add(Account(context_id=ctx.id, name=name, bank=bank, type=acc_type, iban=iban))
        elif iban and account.iban != iban:
            account.iban = iban


def seed_rules(db: Session, contexts: dict[str, Context]) -> None:
    """Startregels voor de regelengine (idempotent op context+veld+type+waarde)."""
    for ctx in contexts.values():
        categories = {
            (c.type, c.name): c
            for c in db.scalars(select(Category).where(Category.context_id == ctx.id))
        }
        for index, (field, value, cat_type, cat_name) in enumerate(SEED_RULES):
            category = categories.get((cat_type, cat_name))
            if category is None:
                logger.warning(
                    "Seed-regel '%s' overgeslagen voor %s: categorie '%s' ontbreekt",
                    value,
                    ctx.name,
                    cat_name,
                )
                continue
            # .first() i.p.v. .one_or_none(): er mogen meerdere regels met dezelfde
            # match bestaan (bv. een Eten-regel plus een gedupliceerde Boodschappen-
            # variant). De seed wil enkel weten óf de match al voorkomt.
            exists = db.scalars(
                select(CategorizationRule).where(
                    CategorizationRule.context_id == ctx.id,
                    CategorizationRule.match_field == field,
                    CategorizationRule.match_type == MatchType.CONTAINS,
                    CategorizationRule.match_value == value,
                )
            ).first()
            if exists is None:
                db.add(
                    CategorizationRule(
                        context_id=ctx.id,
                        priority=100 + 10 * index,
                        match_field=field,
                        match_type=MatchType.CONTAINS,
                        match_value=value,
                        category_id=category.id,
                    )
                )


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
    seed_accounts(db, contexts, settings)
    seed_rules(db, contexts)
    seed_users(db, settings)
    db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        seed_all(db, get_settings())
    logger.info("Seed voltooid")


if __name__ == "__main__":
    main()
