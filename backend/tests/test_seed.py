"""Tests voor de idempotente seed (contexten, categorieën, rekeningen, users)."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Account, Base, Category, Context, User
from app.models.enums import AccountType, Bank, CategoryType
from app.seed import seed_all


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        simon_email="simon@example.test",
        simon_password_hash="$argon2id$fake-hash-simon",
        jozefien_email="jozefien@example.test",
        jozefien_password_hash="$argon2id$fake-hash-jozefien",
    )


def counts(session: Session) -> dict[str, int]:
    return {
        "contexts": session.scalar(select(func.count(Context.id))) or 0,
        "categories": session.scalar(select(func.count(Category.id))) or 0,
        "accounts": session.scalar(select(func.count(Account.id))) or 0,
        "users": session.scalar(select(func.count(User.id))) or 0,
    }


def test_seed_creates_expected_rows(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    assert counts(session) == {
        "contexts": 3,
        "categories": 65,  # 21 categorieën × 3 contexten + "Loon" (Simon, Jozefien)
        "accounts": 5,
        "users": 2,
    }


def test_seed_is_idempotent(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    first = counts(session)
    seed_all(session, settings)
    assert counts(session) == first


def test_contexts(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    names = set(session.scalars(select(Context.name)))
    assert names == {"Gemeenschappelijk", "Simon", "Jozefien"}


def test_categories_per_context(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    for context_name in ("Gemeenschappelijk", "Simon", "Jozefien"):
        ctx = session.scalars(select(Context).where(Context.name == context_name)).one()
        cats = session.scalars(select(Category).where(Category.context_id == ctx.id)).all()
        by_type = {t: [c for c in cats if c.type == t] for t in CategoryType}
        # Simon en Jozefien hebben bovenop de startlijst de categorie "Loon"
        verwacht_inkomen = 5 if context_name == "Gemeenschappelijk" else 6
        assert len(by_type[CategoryType.INKOMEN]) == verwacht_inkomen
        assert len(by_type[CategoryType.UITGAVEN]) == 14
        assert len(by_type[CategoryType.SPAREN]) == 2
        # Spec-volgorde bewaard via sort_order
        uitgaven = sorted(by_type[CategoryType.UITGAVEN], key=lambda c: c.sort_order)
        assert uitgaven[0].name == "Lening"
        assert uitgaven[-1].name == "Katten"


def test_accounts(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    accounts = {
        (a.context.name, a.name): (a.bank, a.type) for a in session.scalars(select(Account)).all()
    }
    assert accounts == {
        ("Gemeenschappelijk", "KBC Zichtrekening"): (Bank.KBC, AccountType.ZICHT),
        ("Gemeenschappelijk", "KBC Spaarrekening"): (Bank.KBC, AccountType.SPAAR),
        ("Simon", "Fortis Zichtrekening"): (Bank.FORTIS, AccountType.ZICHT),
        ("Simon", "Fortis Spaarrekening"): (Bank.FORTIS, AccountType.SPAAR),
        ("Jozefien", "KBC Zichtrekening"): (Bank.KBC, AccountType.ZICHT),
    }


def test_account_ibans_from_settings(session: Session, settings: Settings) -> None:
    """IBAN's komen genormaliseerd uit .env; leeg = geen IBAN."""
    settings.account_iban_kbc_zicht = "be71 0961 2345 6769"
    seed_all(session, settings)
    kbc_zicht = session.scalars(
        select(Account).where(Account.name == "KBC Zichtrekening", Account.iban.is_not(None))
    ).one()
    assert kbc_zicht.iban == "BE71096123456769"
    assert kbc_zicht.context.name == "Gemeenschappelijk"
    zonder_iban = session.scalars(select(Account).where(Account.iban.is_(None))).all()
    assert len(zonder_iban) == 4


def test_account_iban_updated_on_change(session: Session, settings: Settings) -> None:
    """IBAN later invullen of corrigeren in .env werkt op een bestaande rekening."""
    seed_all(session, settings)
    settings.account_iban_fortis_zicht = "BE68539007547034"
    seed_all(session, settings)
    fortis = session.scalars(select(Account).where(Account.name == "Fortis Zichtrekening")).one()
    assert fortis.iban == "BE68539007547034"
    assert counts(session)["accounts"] == 5


def test_users_from_settings(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    simon = session.scalars(select(User).where(User.name == "Simon")).one()
    assert simon.email == "simon@example.test"
    assert simon.password_hash == "$argon2id$fake-hash-simon"


def test_user_hash_updated_on_change(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    settings.simon_password_hash = "$argon2id$nieuwe-hash"
    seed_all(session, settings)
    simon = session.scalars(select(User).where(User.name == "Simon")).one()
    assert simon.password_hash == "$argon2id$nieuwe-hash"
    assert counts(session)["users"] == 2


def test_users_skipped_when_env_empty(session: Session) -> None:
    empty = Settings(_env_file=None)
    seed_all(session, empty)
    assert counts(session)["users"] == 0
    # Contexten/categorieën/rekeningen worden wél geseed
    assert counts(session)["contexts"] == 3
